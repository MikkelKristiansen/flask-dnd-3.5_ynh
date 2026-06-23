"""Fil-persistens for D&D 3.5 karakterark — indlæsning, gem og versionering.

Ét klart ansvar: oversæt mellem karakterfilernes YAML på disken og Character-
dataklassen, og beskyt live-data ved skrivning (atomar skrivning + roterende
snapshots). Beregninger og referencedata bor andre steder; her er kun I/O.

character.py re-eksporterer disse navne (façade), så de mange
char_module.load_character / save_character-kald i app.py virker uændret.
"""
from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

# Antal versioner der beholdes pr. karakter i backups/<navn>/ (roteres ved gem)
SNAPSHOT_KEEP = 50


def load_character(path: str) -> Character:
    yaml = YAML()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.load(f)

    validate_character_data(data)

    ab_raw = data.get("ability_scores") or {}
    scores = AbilityScores(
        **{attr: int(ab_raw.get(attr, 10))
           for attr in ("str", "dex", "con", "int", "wis", "cha")}
    )

    skills = []
    for s in data.get("skills") or []:
        skills.append(Skill(
            id=str(s["id"]).lower(),
            ranks=float(s.get("ranks", 0)),
            misc=int(s.get("misc", 0)),
        ))

    attacks = []
    for a in data.get("attacks") or []:
        attacks.append(Attack(
            name=str(a["name"]),
            kind=str(a.get("kind", "melee")).lower(),
            base_damage=str(a.get("base_damage", "1d4")),
            str_damage_mult=float(a.get("str_damage_mult", 1.0)),
            bonus=int(a.get("bonus", 0)),
            fixed_damage=str(a.get("fixed_damage", "")),
            crit=str(a.get("crit", "x2")),
            type=str(a.get("type", "")),
            range=str(a.get("range", "")),
            source=str(a.get("source", "weapon")).lower(),
            requires=str(a.get("requires", "")).strip(),
        ))

    inventory = []
    for item in data.get("inventory") or []:
        if isinstance(item, dict):
            state = str(item.get("state", "backpack")).lower()
            if state not in INVENTORY_STATES:
                state = "backpack"
            inventory.append(InventoryItem(
                name=str(item.get("name", "")),
                weight=float(item.get("weight", 0) or 0),
                qty=int(item.get("qty", 1)),
                notes=str(item.get("notes", "")),
                ref=str(item.get("ref", "")),
                state=state,
                bonus=int(item.get("bonus", 0)),
                str_mult=(None if item.get("str_mult") is None else float(item["str_mult"])),
                two_handed=bool(item.get("two_handed", False)),
                masterwork=bool(item.get("masterwork", False)),
                enhancement=int(item.get("enhancement", 0) or 0),
            ))
        else:
            # Backwards-compat: plain string
            inventory.append(InventoryItem(name=str(item)))

    hp = data.get("hp") or {}

    spells_prepared: dict[int, list[str]] = {}
    for k, v in (data.get("spells_prepared") or {}).items():
        spells_prepared[int(k)] = list(v) if v else []

    def _index_map(raw) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for k, v in (raw or {}).items():
            if v:
                indices = []
                for item in v:
                    try:
                        indices.append(int(item))
                    except (ValueError, TypeError):
                        pass
                if indices:
                    out[int(k)] = indices
        return out

    spells_used = _index_map(data.get("spells_used"))
    spells_active = _index_map(data.get("spells_active"))

    spell_charges: dict[str, int] = {}
    for k, v in (data.get("spell_charges") or {}).items():
        try:
            spell_charges[str(k)] = int(v)
        except (ValueError, TypeError):
            pass

    conditions = list(data.get("conditions") or [])
    buffs = list(data.get("buffs") or [])

    domains = [str(d).lower() for d in (data.get("domains") or [])]

    domain_spells_prepared: dict[int, str] = {}
    for k, v in (data.get("domain_spells_prepared") or {}).items():
        if v:
            domain_spells_prepared[int(k)] = str(v)

    domain_spells_used: dict[int, bool] = {}
    for k, v in (data.get("domain_spells_used") or {}).items():
        domain_spells_used[int(k)] = bool(v)

    return Character(
        name=str(data.get("name", "Unknown")),
        race=str(data.get("race", "")),
        cls=str(data.get("class", "")),
        level=int(data.get("level", 1)),
        hp_current=int(hp.get("current", 0)),
        hp_max=int(hp.get("max", 0)),
        ability_scores=scores,
        experience_points=int(data.get("experience_points", 0)),
        saves=dict(data.get("saves") or {}),
        combat=dict(data.get("combat") or {}),
        skills=skills,
        feats=list(data.get("feats") or []),
        attacks=attacks,
        spells_prepared=spells_prepared,
        spells_used=spells_used,
        spells_active=spells_active,
        spell_charges=spell_charges,
        conditions=conditions,
        buffs=buffs,
        languages=[str(x) for x in (data.get("languages") or [])],
        inventory=inventory,
        gold=dict(data.get("gold") or {}),
        notes=str(data.get("notes") or ""),
        size=str(data.get("size", "medium")).lower(),
        armor=str(data.get("combat", {}).get("armor") or ""),
        shield=str(data.get("combat", {}).get("shield") or ""),
        companion=dict(data.get("companion") or {}),
        summons=list(data.get("summons") or []),
        class_features=dict(data.get("class_features") or {}),
        deity=str(data.get("deity") or ""),
        alignment=str(data.get("alignment") or ""),
        gender=str(data.get("gender") or ""),
        age=str(data.get("age") or ""),
        height=str(data.get("height") or ""),
        weight=str(data.get("weight") or ""),
        racial_traits=dict(data.get("racial_traits") or {}),
        domains=domains,
        domain_spells_prepared=domain_spells_prepared,
        domain_spells_used=domain_spells_used,
    )


# ---------------------------------------------------------------------------
# Versionering / backup af karakterfiler
#
# To lag beskytter live-data (YAML i $data_dir/characters/):
#   1. Atomar skrivning — der skrives til en temp-fil i samme mappe og
#      byttes ind med os.replace(). Den eksisterende fil er urørt indtil
#      byttet lykkes, så en afbrudt/fejlet skrivning kan aldrig efterlade
#      en halvskrevet eller tom karakterfil.
#   2. Roterende snapshots — efter hvert gem kopieres tilstanden til
#      $data_dir/backups/<navn>/<tidsstempel>.yaml; de seneste SNAPSHOT_KEEP
#      beholdes. Giver historik og mulighed for at rulle tilbage.
# ---------------------------------------------------------------------------

def snapshot_dir(char_path: Path) -> Path:
    """backups-mappen for en given karakterfil.

    $data_dir/characters/tjorn.yaml → $data_dir/backups/tjorn/
    (søstermappe til characters/, så den følger med i YunoHost-backup af data_dir).
    """
    return char_path.parent.parent / "backups" / char_path.stem


def list_snapshots(char_path: Path) -> list[Path]:
    """Snapshots for en karakter, ældste først (tidsstempel-navne sorterer kronologisk)."""
    return sorted(snapshot_dir(Path(char_path)).glob("*.yaml"))


def _write_snapshot(char_path: Path) -> None:
    """Kopiér den netop-gemte tilstand til et tidsstemplet snapshot og roter.

    Best-effort: en fejl her må ALDRIG forplante sig — et gem skal altid lykkes,
    også selvom backup-mappen er utilgængelig.
    """
    try:
        if not char_path.exists():
            return
        snap_dir = snapshot_dir(char_path)
        snap_dir.mkdir(parents=True, exist_ok=True)
        current = char_path.read_bytes()
        existing = sorted(snap_dir.glob("*.yaml"))
        # Spring over hvis intet er ændret siden nyeste snapshot (undgå spam ved
        # idempotente gem, fx "ny dag" hvor intet var brugt).
        if existing and existing[-1].read_bytes() == current:
            return
        # Mikrosekunder i navnet → ingen kollision og korrekt kronologisk sortering.
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (snap_dir / f"{ts}.yaml").write_bytes(current)
        # Roter: behold kun de seneste SNAPSHOT_KEEP.
        snaps = sorted(snap_dir.glob("*.yaml"))
        for old in snaps[:-SNAPSHOT_KEEP]:
            old.unlink()
    except Exception:
        pass


def write_character_file(char_path: str, content: bytes) -> bool:
    """Skriv en hel karakterfil (import) atomart. Returnerer True hvis en
    eksisterende fil blev overskrevet.

    Findes filen i forvejen, tages et snapshot af den nuværende tilstand FØRST,
    så en import der overskriver kan fortrydes via Versioner. Den importerede
    tilstand snapshottes også bagefter.
    """
    p = Path(char_path)
    existed = p.exists()
    if existed:
        _write_snapshot(p)
    _atomic_write_bytes(p, content)
    _write_snapshot(p)
    return existed


def restore_snapshot(char_path: str, snapshot_name: str) -> None:
    """Gendan en karakterfil fra et navngivet snapshot (atomart).

    snapshot_name er filnavnet i backups/<navn>/, fx "20260619-204500-123456.yaml".
    Tager selv et snapshot af nuværende tilstand først, så gendannelsen kan fortrydes.
    """
    p = Path(char_path)
    snap = snapshot_dir(p) / snapshot_name
    if not snap.is_file():
        raise FileNotFoundError(f"Snapshot findes ikke: {snap}")
    _write_snapshot(p)  # bevar nuværende tilstand inden overskrivning
    _atomic_write_bytes(p, snap.read_bytes())


def _atomic_write_bytes(p: Path, content: bytes) -> None:
    """Skriv bytes til p atomart: temp-fil i samme mappe → os.replace()."""
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _serialize_inventory_item(item: InventoryItem) -> dict:
    """Inventory-post → minimal YAML-dict. Udelad tomme/default-felter.

    Ref-poster gemmer ikke navn/vægt (slås op i kataloget). Custom-poster gemmer
    navn + vægt. Kun afvigelser fra default skrives, så filerne forbliver rene.
    """
    out: dict = {}
    if item.ref:
        out["ref"] = item.ref
    else:
        out["name"] = item.name
        if item.weight:
            out["weight"] = item.weight
    if item.qty != 1:
        out["qty"] = item.qty
    if item.state != "backpack":
        out["state"] = item.state
    if item.bonus:
        out["bonus"] = item.bonus
    if item.str_mult is not None:
        out["str_mult"] = item.str_mult
    if item.two_handed:
        out["two_handed"] = item.two_handed
    if item.masterwork:
        out["masterwork"] = item.masterwork
    if item.enhancement:
        out["enhancement"] = item.enhancement
    if item.notes:
        out["notes"] = item.notes
    return out


def _serialize_attack(a: Attack) -> dict:
    """Manuelt angreb → minimal YAML-dict. Kun afvigelser fra default skrives.

    Skade gemmes som ENTEN fixed_damage (spell: Str tælles ikke med) ELLER
    base_damage + str_damage_mult (våben). Navn først, så filen er læsbar.
    """
    out: dict = {"name": a.name}
    if a.kind != "melee":
        out["kind"] = a.kind
    if a.fixed_damage:
        out["fixed_damage"] = a.fixed_damage
    elif a.base_damage != "1d4":
        out["base_damage"] = a.base_damage
    if a.str_damage_mult != 1.0:
        out["str_damage_mult"] = a.str_damage_mult
    if a.bonus:
        out["bonus"] = a.bonus
    if a.crit != "x2":
        out["crit"] = a.crit
    if a.type:
        out["type"] = a.type
    if a.range:
        out["range"] = a.range
    if a.source != "weapon":
        out["source"] = a.source
    if a.requires:
        out["requires"] = a.requires
    return out


def _serialize_summon(s: dict) -> dict:
    """Tynd summon-ref → ren YAML-dict (kun rå data, aldrig beregnede totaler).

    Valgfrie felter skrives kun når de afviger fra default, så filen forbliver
    læsbar. hp_current er en liste med ét tal pr. væsen (count).
    """
    out: dict = {
        "creature": str(s.get("creature") or ""),
        "spell_level": int(s.get("spell_level") or 0),
        "spell_index": int(s.get("spell_index") or 0),
        "count": int(s.get("count") or 1),
    }
    hp = s.get("hp_current")
    if hp is not None:
        out["hp_current"] = [int(x) for x in hp]
    if s.get("augment"):
        out["augment"] = True
    if s.get("name"):
        out["name"] = str(s["name"])
    if s.get("buffs"):
        out["buffs"] = list(s["buffs"])
    if s.get("conditions"):
        out["conditions"] = list(s["conditions"])
    return out


def save_character(path: str, updates: dict) -> None:
    """Gem kun angivne felter — overskriv aldrig hele filen.

    updates kan indeholde: hp_current, spells_prepared, spells_used,
    conditions, inventory, experience_points, summons.

    Skrivningen er atomar, og der tages et roterende snapshot efter hvert gem
    (se afsnittet om versionering ovenfor).
    """
    yaml = YAML()
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.load(f)

    if "hp_current" in updates:
        data["hp"]["current"] = updates["hp_current"]

    if "spells_prepared" in updates:
        data["spells_prepared"] = {
            int(k): list(v) for k, v in updates["spells_prepared"].items()
        }

    if "spells_used" in updates:
        data["spells_used"] = {
            int(k): list(v) for k, v in updates["spells_used"].items()
        }

    if "spells_active" in updates:
        data["spells_active"] = {
            int(k): list(v) for k, v in updates["spells_active"].items() if v
        }

    if "spell_charges" in updates:
        data["spell_charges"] = {
            str(k): int(v) for k, v in updates["spell_charges"].items()
        }

    if "domain_spells_prepared" in updates:
        data["domain_spells_prepared"] = {
            int(k): str(v) for k, v in updates["domain_spells_prepared"].items() if v
        }

    if "domain_spells_used" in updates:
        data["domain_spells_used"] = {
            int(k): bool(v) for k, v in updates["domain_spells_used"].items()
        }

    if "conditions" in updates:
        data["conditions"] = list(updates["conditions"])

    if "buffs" in updates:
        data["buffs"] = list(updates["buffs"])

    if "companion_conditions" in updates:
        comp = data.get("companion")
        if isinstance(comp, dict):
            comp["conditions"] = list(updates["companion_conditions"])

    if "companion_buffs" in updates:
        comp = data.get("companion")
        if isinstance(comp, dict):
            comp["buffs"] = list(updates["companion_buffs"])

    if "inventory" in updates:
        data["inventory"] = [_serialize_inventory_item(i) for i in updates["inventory"]]

    if "attacks" in updates:
        data["attacks"] = [_serialize_attack(a) for a in updates["attacks"]]

    if "experience_points" in updates:
        data["experience_points"] = int(updates["experience_points"])

    if "notes" in updates:
        data["notes"] = str(updates["notes"])

    if "companion_hp_current" in updates:
        comp = data.get("companion")
        if isinstance(comp, dict):
            comp["hp_current"] = int(updates["companion_hp_current"])

    if "companion_tricks" in updates:
        comp = data.get("companion")
        if isinstance(comp, dict):
            comp["tricks"] = [str(t) for t in updates["companion_tricks"]]

    # Summon Nature's Ally-væsner: hele listen gemmes på én gang (som inventory/
    # buffs). App-endpoints bygger den nye liste (tilføj ved kast, fjern ved
    # "Brugt", opdatér HP/effekter). Tom liste rydder feltet.
    if "summons" in updates:
        data["summons"] = [_serialize_summon(s) for s in updates["summons"]]

    if "gold" in updates:
        data["gold"] = dict(updates["gold"])

    if "level" in updates:
        data["level"] = int(updates["level"])

    if "hp_max" in updates:
        data["hp"]["max"] = int(updates["hp_max"])

    if "skill_deltas" in updates and updates["skill_deltas"]:
        flat = {str(s["id"]): {"id": str(s["id"]), "ranks": float(s.get("ranks", 0)),
                                "misc": int(s.get("misc", 0))}
                for s in (data.get("skills") or [])}
        for sid, delta in updates["skill_deltas"].items():
            delta = round(float(delta), 1)
            if delta == 0:
                continue
            if sid in flat:
                flat[sid]["ranks"] = round(flat[sid]["ranks"] + delta, 1)
            else:
                flat[sid] = {"id": sid, "ranks": delta, "misc": 0}
        data["skills"] = list(flat.values())

    if "new_feat" in updates and updates["new_feat"]:
        feats = list(data.get("feats") or [])
        nf = updates["new_feat"]
        # new_feat kan være en ren id-streng eller {id, weapon} for våben-feats.
        if isinstance(nf, dict) and nf.get("weapon"):
            entry: object = {"id": str(nf["id"]), "weapon": str(nf["weapon"])}
        else:
            entry = feat_id(nf)
        new_key = (feat_id(entry), feat_weapon(entry))
        existing = {(feat_id(e), feat_weapon(e)) for e in feats}
        if new_key not in existing:
            feats.append(entry)
        data["feats"] = feats

    if "ability_boost" in updates and updates["ability_boost"]:
        key = str(updates["ability_boost"]).lower()
        data["ability_scores"][key] = int(data["ability_scores"].get(key, 10)) + 1

    # Atomar skrivning: dump til en buffer, skriv den atomart ind, snapshot bagefter.
    buf = io.StringIO()
    yaml.dump(data, buf)
    _atomic_write_bytes(p, buf.getvalue().encode("utf-8"))
    _write_snapshot(p)


# Importér dataklasser + felt-/feat-hjælpere SIDST: character.py re-eksporterer
# denne fils navne (façade), så modulerne er gensidigt afhængige. Ved at vente til
# alle funktioner her er defineret undgår vi at ramme et halv-initialiseret modul,
# uanset importrækkefølge.
from character import (  # noqa: E402,F401
    AbilityScores, Skill, Attack, InventoryItem, Character,
    validate_character_data, INVENTORY_STATES, feat_id, feat_weapon)
