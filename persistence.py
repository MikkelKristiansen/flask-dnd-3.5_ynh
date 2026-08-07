"""Fil-persistens for D&D 3.5 karakterark — indlæsning og gem.

Ét klart ansvar: oversæt mellem karakterfilernes YAML på disken og Character-
dataklassen. Beregninger og referencedata bor andre steder; her er kun I/O.

Selve beskyttelsen af live-data — atomar skrivning og roterende snapshots —
ligger i versions.py. Navnene derfra re-eksporteres her, og character.py
re-eksporterer igen (façade), så de mange char_module.load_character /
save_character / list_snapshots-kald i app-laget virker uændret.
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

from ruamel.yaml import YAML

from versions import (  # noqa: F401  (re-eksporteres via character.py-façaden)
    SNAPSHOT_KEEP, atomic_write_bytes, list_snapshots, restore_snapshot,
    snapshot_dir, write_snapshot)


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
            misc_note=str(s.get("misc_note", "")),
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
                off_hand=bool(item.get("off_hand", False)),
                thrown=(None if item.get("thrown") is None else bool(item["thrown"])),
                mighty=(None if item.get("mighty") is None else int(item["mighty"])),
                double=bool(item.get("double", False)),
                masterwork=bool(item.get("masterwork", False)),
                material=str(item.get("material", "") or ""),
                enhancement=int(item.get("enhancement", 0) or 0),
                abilities=[str(a) for a in (item.get("abilities") or [])],
                charges=(None if item.get("charges") is None else int(item["charges"])),
                house_rule=bool(item.get("house_rule", False)),
            ))
        else:
            # Backwards-compat: plain string
            inventory.append(InventoryItem(name=str(item)))

    hp = data.get("hp") or {}

    spells_prepared: dict[int, list[str]] = {}
    for k, v in (data.get("spells_prepared") or {}).items():
        spells_prepared[int(k)] = list(v) if v else []

    spells_known: dict[int, list[str]] = {}
    for k, v in (data.get("spells_known") or {}).items():
        spells_known[int(k)] = list(v) if v else []

    spells_known_used: dict[int, int] = {}
    for k, v in (data.get("spells_known_used") or {}).items():
        try:
            spells_known_used[int(k)] = int(v)
        except (ValueError, TypeError):
            pass

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

    spell_modes: dict[str, int] = {}
    for k, v in (data.get("spell_modes") or {}).items():
        try:
            spell_modes[str(k)] = int(v)
        except (ValueError, TypeError):
            pass

    spell_durations: dict[str, dict] = {}
    for k, v in (data.get("spell_durations") or {}).items():
        try:
            spell_durations[str(k)] = {
                "left": int(v["left"]), "max": int(v["max"]), "unit": str(v["unit"])}
        except (ValueError, TypeError, KeyError):
            pass

    spells_known_active: list[dict] = []
    for inst in (data.get("spells_known_active") or []):
        try:
            row = {
                "uid": str(inst["uid"]),
                "level": int(inst["level"]),
                "spell_id": str(inst["spell_id"]),
                "kind": str(inst.get("kind") or "duration"),
            }
        except (KeyError, ValueError, TypeError):
            continue
        dur = inst.get("duration")
        if isinstance(dur, dict):
            try:
                row["duration"] = {
                    "left": int(dur["left"]), "max": int(dur["max"]),
                    "unit": str(dur["unit"])}
            except (KeyError, ValueError, TypeError):
                pass
        if "mode" in inst:
            try:
                row["mode"] = int(inst["mode"])
            except (ValueError, TypeError):
                pass
        if "charges" in inst:
            try:
                row["charges"] = int(inst["charges"])
            except (ValueError, TypeError):
                pass
        spells_known_active.append(row)

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
        spells_known=spells_known,
        spells_known_used=spells_known_used,
        spells_used=spells_used,
        spells_active=spells_active,
        spell_charges=spell_charges,
        spell_modes=spell_modes,
        spell_durations=spell_durations,
        spells_known_active=spells_known_active,
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
        familiar_lost=dict(data.get("familiar_lost") or {}),
        wild_shape=dict(data.get("wild_shape") or {}),
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
        lay_on_hands_used=int(data.get("lay_on_hands_used", 0)),
        smite_used=int(data.get("smite_used", 0)),
        # Værdier er enten bool (simple toggles/under-toggles, Lag A) eller
        # heltal N (editable options som Power Attack/Combat Expertise, Lag B)
        # — bevar typen som den er; kun uventede typer (fx en tekststreng fra
        # en håndredigeret YAML) tvinges til bool som sikkerhedsnet.
        combat_options={str(k): (v if isinstance(v, (bool, int)) else bool(v))
                         for k, v in (data.get("combat_options") or {}).items()},
    )


# ---------------------------------------------------------------------------
# Skrivning af karakterfiler
#
# Selve beskyttelsen af live-data (atomar skrivning + roterende snapshots) bor
# i versions.py; her er kun de operationer der arbejder på en karakterfil som
# helhed. Navnene re-eksporteres nederst, så character.py-façaden er uændret.
# ---------------------------------------------------------------------------

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
        write_snapshot(p)
    atomic_write_bytes(p, content)
    write_snapshot(p)
    return existed


def delete_character(char_path: str) -> None:
    """Slet en karakterfil og hele dens snapshot-historik permanent.

    Fjerner $data_dir/characters/<navn>.yaml samt $data_dir/backups/<navn>/.
    Portrættet ligger i en søstermappe (portraits/) som app-laget ejer — det
    ryddes der, ikke her, så dette modul kun rører karakterens egne filer.
    Best-effort på snapshots: at den levende fil forsvinder er det vigtige.
    """
    p = Path(char_path)
    p.unlink(missing_ok=True)
    snaps = snapshot_dir(p)
    if snaps.is_dir():
        shutil.rmtree(snaps, ignore_errors=True)


def _serialize_inventory_item(item: InventoryItem) -> dict:
    """Inventory-post → minimal YAML-dict. Udelad tomme/default-felter.

    Ref-poster gemmer ikke navn/vægt (slås op i kataloget). Custom-poster gemmer
    navn + vægt. Kun afvigelser fra default skrives, så filerne forbliver rene.
    """
    out: dict = {}
    if item.ref:
        out["ref"] = item.ref
        # Ref-poster slår normalt navnet op i kataloget; gem kun et navn hvis det
        # er sat eksplicit (fx materiale-mærkat "Masterwork Cold Iron Longsword").
        if item.name:
            out["name"] = item.name
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
    if item.off_hand:
        out["off_hand"] = item.off_hand
    if item.thrown is not None:
        out["thrown"] = item.thrown
    if item.mighty is not None:
        out["mighty"] = item.mighty
    if item.double:
        out["double"] = item.double
    if item.masterwork:
        out["masterwork"] = item.masterwork
    if item.material:
        out["material"] = item.material
    if item.enhancement:
        out["enhancement"] = item.enhancement
    if item.abilities:
        out["abilities"] = list(item.abilities)
    if item.charges is not None:
        out["charges"] = item.charges
    if item.house_rule:
        out["house_rule"] = item.house_rule
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
    if s.get("rounds_max") is not None:        # varighed (runder) — snapshot af casterniveau ved kast
        out["rounds_max"] = int(s["rounds_max"])
    if s.get("rounds_left") is not None:
        out["rounds_left"] = int(s["rounds_left"])
    if s.get("template"):          # Summon Monster: celestial/fiendish — SNA har ingen
        out["template"] = str(s["template"])
    if s.get("augment"):
        out["augment"] = True
    if s.get("spontaneous"):       # spontant summonet (sorcerer/bard) → afsked-knap
        out["spontaneous"] = True
    if s.get("name"):
        out["name"] = str(s["name"])
    if s.get("buffs"):
        out["buffs"] = list(s["buffs"])
    if s.get("conditions"):
        out["conditions"] = list(s["conditions"])
    return out


def _add_feat(feats: list, nf) -> None:
    """Normaliser ét feat-valg og tilføj det til feats-listen (mutation), medmindre
    det allerede findes (dedup på id+weapon+school). Bruges til at loope over
    flere feat-valg på samme level-up (generel + fighter-bonus)."""
    # nf kan være en ren id-streng, {id, weapon} for våben-feats eller
    # {id, school} for skole-feats (Spell Focus m.fl.).
    if isinstance(nf, dict) and nf.get("weapon"):
        entry: object = {"id": str(nf["id"]), "weapon": str(nf["weapon"])}
    elif isinstance(nf, dict) and nf.get("school"):
        entry = {"id": str(nf["id"]), "school": str(nf["school"])}
    else:
        entry = feat_id(nf)
    new_key = (feat_id(entry), feat_weapon(entry), feat_school(entry))
    existing = {(feat_id(e), feat_weapon(e), feat_school(e)) for e in feats}
    if new_key not in existing:
        feats.append(entry)


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

    if "spells_known" in updates:
        data["spells_known"] = {
            int(k): list(v) for k, v in updates["spells_known"].items() if v
        }

    if "spells_known_used" in updates:
        data["spells_known_used"] = {
            int(k): int(v) for k, v in updates["spells_known_used"].items() if v
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

    if "spell_modes" in updates:
        data["spell_modes"] = {
            str(k): int(v) for k, v in updates["spell_modes"].items()
        }

    if "spell_durations" in updates:
        data["spell_durations"] = {
            str(k): {"left": int(v["left"]), "max": int(v["max"]),
                     "unit": str(v["unit"])}
            for k, v in updates["spell_durations"].items()
        }

    if "spells_known_active" in updates:
        # Spontane aktive instanser — gemmes som råt (allerede saniteret i
        # routes_spells før kaldet). Tomme felter droppes for at holde JSON'en ren.
        out = []
        for inst in updates["spells_known_active"]:
            row = {"uid": str(inst["uid"]), "level": int(inst["level"]),
                   "spell_id": str(inst["spell_id"]),
                   "kind": str(inst.get("kind") or "duration")}
            dur = inst.get("duration")
            if isinstance(dur, dict):
                row["duration"] = {"left": int(dur["left"]), "max": int(dur["max"]),
                                   "unit": str(dur["unit"])}
            if "mode" in inst:
                row["mode"] = int(inst["mode"])
            if "charges" in inst:
                row["charges"] = int(inst["charges"])
            out.append(row)
        data["spells_known_active"] = out

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

    if "combat_options" in updates:
        data["combat_options"] = dict(updates["combat_options"])

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

    if "lay_on_hands_used" in updates:
        data["lay_on_hands_used"] = int(updates["lay_on_hands_used"])

    if "smite_used" in updates:
        data["smite_used"] = int(updates["smite_used"])

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

    if "companion_inventory" in updates:
        comp = data.get("companion")
        if isinstance(comp, dict):
            # Samme serialisering som karakterens eget inventar — kun afvigelser
            # fra default skrives, så YAML'en forbliver læsbar i hånden.
            rows = [i if isinstance(i, InventoryItem) else InventoryItem(**i)
                    for i in updates["companion_inventory"]]
            comp["inventory"] = [_serialize_inventory_item(i) for i in rows]
            if not comp["inventory"]:
                comp.pop("inventory")

    # Hele companion-referencen sættes (tilkald) eller ryddes (afsked). Tom dict
    # fjerner feltet helt → build_companion giver None, og fanen forsvinder.
    if "familiar_lost" in updates:
        fl = updates["familiar_lost"] or {}
        if fl:
            data["familiar_lost"] = {"cooldown": int(fl.get("cooldown", 0))}
        else:
            data.pop("familiar_lost", None)

    if "companion" in updates:
        comp = updates["companion"] or {}
        if comp:
            data["companion"] = dict(comp)
        else:
            data.pop("companion", None)

    # Wild shape-tilstand: {animal_used, elemental_used, current_form}. Tom dict
    # (fx ved "Ny dag") fjerner feltet helt → ingen aktiv form, alle uses tilbage.
    if "wild_shape" in updates:
        wsd = updates["wild_shape"] or {}
        if wsd:
            data["wild_shape"] = dict(wsd)
        else:
            data.pop("wild_shape", None)

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
        flat = {}
        for s in (data.get("skills") or []):
            entry = {"id": str(s["id"]), "ranks": float(s.get("ranks", 0)),
                     "misc": int(s.get("misc", 0))}
            if s.get("misc_note"):   # bevar kilde-label gennem level-up
                entry["misc_note"] = str(s["misc_note"])
            flat[str(s["id"])] = entry
        for sid, delta in updates["skill_deltas"].items():
            delta = round(float(delta), 1)
            if delta == 0:
                continue
            if sid in flat:
                flat[sid]["ranks"] = round(flat[sid]["ranks"] + delta, 1)
            else:
                flat[sid] = {"id": sid, "ranks": delta, "misc": 0}
        data["skills"] = list(flat.values())

    # new_feats (liste, fx generel + fighter-bonus på samme niveau) + new_feat
    # (enkelt, bagudkompatibel) — begge kan gemmes på samme kald. Dedup gælder
    # på tværs af hele listen via _add_feat, der tjekker mod feats som den bygger.
    _new_feats = list(updates.get("new_feats") or [])
    if updates.get("new_feat"):
        _new_feats.append(updates["new_feat"])
    if _new_feats:
        feats = list(data.get("feats") or [])
        for nf in _new_feats:
            _add_feat(feats, nf)
        data["feats"] = feats

    if "ability_boost" in updates and updates["ability_boost"]:
        key = str(updates["ability_boost"]).lower()
        data["ability_scores"][key] = int(data["ability_scores"].get(key, 10)) + 1

    # Atomar skrivning: dump til en buffer, skriv den atomart ind, snapshot bagefter.
    buf = io.StringIO()
    yaml.dump(data, buf)
    atomic_write_bytes(p, buf.getvalue().encode("utf-8"))
    write_snapshot(p)


# Importér dataklasser + felt-/feat-hjælpere SIDST: character.py re-eksporterer
# denne fils navne (façade), så modulerne er gensidigt afhængige. Ved at vente til
# alle funktioner her er defineret undgår vi at ramme et halv-initialiseret modul,
# uanset importrækkefølge.
from character import (  # noqa: E402,F401
    AbilityScores, Skill, Attack, InventoryItem, Character,
    validate_character_data, INVENTORY_STATES, feat_id, feat_weapon, feat_school)
