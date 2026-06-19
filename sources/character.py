"""Dataklasser og beregningslogik for D&D 3.5 karakterark."""
import io
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

# Antal versioner der beholdes pr. karakter i backups/<navn>/ (roteres ved gem)
SNAPSHOT_KEEP = 50

# D&D 3.5 XP thresholds: index = target level (XP_THRESHOLDS[2] = XP needed for level 2)
XP_THRESHOLDS = [
    0,       # level 0 (unused)
    0,       # level 1
    1000,    # level 2
    3000,    # level 3
    6000,    # level 4
    10000,   # level 5
    15000,   # level 6
    21000,   # level 7
    28000,   # level 8
    36000,   # level 9
    45000,   # level 10
    55000,   # level 11
    66000,   # level 12
    78000,   # level 13
    91000,   # level 14
    105000,  # level 15
    120000,  # level 16
    136000,  # level 17
    153000,  # level 18
    171000,  # level 19
    190000,  # level 20
]

# Light load limits (lbs) for Medium creatures, indexed by STR score 1–20
_LIGHT_LOAD_MEDIUM = {
    1: 3,   2: 6,   3: 10,  4: 13,  5: 16,
    6: 20,  7: 23,  8: 26,  9: 30,  10: 33,
    11: 38, 12: 43, 13: 50, 14: 58, 15: 66,
    16: 76, 17: 86, 18: 100, 19: 116, 20: 133,
}

_SIZE_CARRY_MULTIPLIER = {
    "fine": 0.125, "diminutive": 0.25, "tiny": 0.5,
    "small": 0.75, "medium": 1.0,
    "large_tall": 2.0, "large_long": 1.5,
    "huge_tall": 4.0, "huge_long": 3.0,
    "gargantuan": 8.0, "colossal": 16.0,
}


@dataclass
class AbilityScores:
    str: int = 10
    dex: int = 10
    con: int = 10
    int: int = 10
    wis: int = 10
    cha: int = 10

    def modifier(self, ability: str) -> int:
        return (getattr(self, ability) - 10) // 2


@dataclass
class Skill:
    id: str
    ranks: float        # float: cross-class giver halve ranks
    misc: int = 0


@dataclass
class Attack:
    name: str
    kind: str = "melee"            # melee | ranged | melee_touch | ranged_touch
    base_damage: str = "1d4"       # KUN terningen; Str lægges på i koden
    str_damage_mult: float = 1.0   # 1 normal · 1.5 tohånds · 0.5 off-hand · 0 ingen Str
    bonus: int = 0                 # situations-uafhængig til-hit (Weapon Focus, masterwork, magi)
    fixed_damage: str = ""         # skade sat af kilden (spell/touch); tilsidesætter base+Str
    crit: str = "x2"
    type: str = ""
    range: str = ""


@dataclass
class InventoryItem:
    name: str
    weight: float = 0.0
    qty: int = 1
    notes: str = ""


@dataclass
class Character:
    name: str
    race: str
    cls: str            # 'class' er reserveret i Python
    level: int
    hp_current: int
    hp_max: int
    ability_scores: AbilityScores
    experience_points: int = 0
    saves: dict = field(default_factory=dict)
    combat: dict = field(default_factory=dict)
    skills: list = field(default_factory=list)
    feats: list = field(default_factory=list)
    attacks: list = field(default_factory=list)
    spells_prepared: dict = field(default_factory=dict)
    spells_used: dict = field(default_factory=dict)
    conditions: list = field(default_factory=list)
    inventory: list = field(default_factory=list)
    gold: dict = field(default_factory=dict)
    notes: str = ""
    size: str = "medium"
    armor: str = ""             # equipped rustnings-id (slås op i armor-tabellen)
    shield: str = ""            # equipped skjold-id
    companion: dict = field(default_factory=dict)
    class_features: dict = field(default_factory=dict)
    deity: str = ""
    racial_traits: dict = field(default_factory=dict)
    domains: list = field(default_factory=list)
    domain_spells_prepared: dict = field(default_factory=dict)  # {level: spell_id}
    domain_spells_used: dict = field(default_factory=dict)      # {level: bool}


def validate_character_data(data: object) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"Forventet YAML-dict, fik {type(data).__name__}")

    missing = [k for k in ("name", "hp", "ability_scores") if k not in data]
    if missing:
        raise ValueError(f"Manglende påkrævede felter: {', '.join(sorted(missing))}")

    hp = data.get("hp") or {}
    if not isinstance(hp, dict):
        raise ValueError(f"hp skal være et dict, fik {type(hp).__name__}")
    for sub in ("current", "max"):
        if sub not in hp:
            raise ValueError(f"hp.{sub} mangler i YAML-filen")

    ab = data.get("ability_scores") or {}
    if not isinstance(ab, dict):
        raise ValueError(f"ability_scores skal være et dict, fik {type(ab).__name__}")
    missing_ab = [a for a in ("str", "dex", "con", "int", "wis", "cha") if a not in ab]
    if missing_ab:
        raise ValueError(f"ability_scores mangler: {', '.join(missing_ab)}")


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
        ))

    inventory = []
    for item in data.get("inventory") or []:
        if isinstance(item, dict):
            inventory.append(InventoryItem(
                name=str(item.get("name", "")),
                weight=float(item.get("weight", 0)),
                qty=int(item.get("qty", 1)),
                notes=str(item.get("notes", "")),
            ))
        else:
            # Backwards-compat: plain string
            inventory.append(InventoryItem(name=str(item)))

    hp = data.get("hp") or {}

    spells_prepared: dict[int, list[str]] = {}
    for k, v in (data.get("spells_prepared") or {}).items():
        spells_prepared[int(k)] = list(v) if v else []

    spells_used: dict[int, list[int]] = {}
    for k, v in (data.get("spells_used") or {}).items():
        if v:
            indices = []
            for item in v:
                try:
                    indices.append(int(item))
                except (ValueError, TypeError):
                    pass
            if indices:
                spells_used[int(k)] = indices

    conditions = list(data.get("conditions") or [])

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
        conditions=conditions,
        inventory=inventory,
        gold=dict(data.get("gold") or {}),
        notes=str(data.get("notes") or ""),
        size=str(data.get("size", "medium")).lower(),
        armor=str(data.get("combat", {}).get("armor") or ""),
        shield=str(data.get("combat", {}).get("shield") or ""),
        companion=dict(data.get("companion") or {}),
        class_features=dict(data.get("class_features") or {}),
        deity=str(data.get("deity") or ""),
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


def save_character(path: str, updates: dict) -> None:
    """Gem kun angivne felter — overskriv aldrig hele filen.

    updates kan indeholde: hp_current, spells_prepared, spells_used,
    conditions, inventory, experience_points.

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

    if "inventory" in updates:
        data["inventory"] = [
            {
                "name": item.name,
                "weight": item.weight,
                "qty": item.qty,
                "notes": item.notes,
            }
            for item in updates["inventory"]
        ]

    if "experience_points" in updates:
        data["experience_points"] = int(updates["experience_points"])

    if "notes" in updates:
        data["notes"] = str(updates["notes"])

    if "companion_hp_current" in updates:
        comp = data.get("companion")
        if isinstance(comp, dict) and isinstance(comp.get("hp"), dict):
            comp["hp"]["current"] = int(updates["companion_hp_current"])

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
        fid = str(updates["new_feat"])
        if fid not in feats:
            feats.append(fid)
        data["feats"] = feats

    if "ability_boost" in updates and updates["ability_boost"]:
        key = str(updates["ability_boost"]).lower()
        data["ability_scores"][key] = int(data["ability_scores"].get(key, 10)) + 1

    # Atomar skrivning: dump til en buffer, skriv den atomart ind, snapshot bagefter.
    buf = io.StringIO()
    yaml.dump(data, buf)
    _atomic_write_bytes(p, buf.getvalue().encode("utf-8"))
    _write_snapshot(p)


# ---------------------------------------------------------------------------
# Beregninger
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# D&D 3.5 SRD skill synergies — aktiveres ved ≥5 ranks i kildefærdighed
# ---------------------------------------------------------------------------
SKILL_SYNERGIES: dict[str, list[tuple[str, int]]] = {
    "bluff":                   [("diplomacy", 2), ("intimidate", 2), ("sleight_of_hand", 2)],
    "decipher_script":         [("use_magic_device", 2)],
    "escape_artist":           [("use_rope", 2)],
    "handle_animal":           [("ride", 2)],
    "jump":                    [("tumble", 2)],
    "knowledge_arcana":        [("spellcraft", 2)],
    "knowledge_dungeoneering": [("survival", 2)],
    "knowledge_geography":     [("survival", 2)],
    "knowledge_local":         [("gather_information", 2)],
    "knowledge_nature":        [("survival", 2), ("handle_animal", 2)],
    "knowledge_nobility":      [("diplomacy", 2)],
    "knowledge_planes":        [("survival", 2)],
    "sense_motive":            [("diplomacy", 2)],
    "spellcraft":              [("use_magic_device", 2)],
    "survival":                [("knowledge_nature", 2)],
    "tumble":                  [("balance", 2), ("jump", 2)],
    "use_magic_device":        [("spellcraft", 2)],
    "use_rope":                [("climb", 2), ("escape_artist", 2)],
}
SYNERGY_THRESHOLD = 5


def compute_synergy_bonuses(skills: list[Skill]) -> dict[str, int]:
    """Beregn synergi-bonusser fra skills med ≥5 ranks (SRD 3.5 s. 65).

    Returnerer {skill_id: samlet_synergibonus} for alle skills der modtager bonus.
    """
    rank_map = {s.id: int(s.ranks) for s in skills}
    bonuses: dict[str, int] = {}
    for source_id, targets in SKILL_SYNERGIES.items():
        if rank_map.get(source_id, 0) >= SYNERGY_THRESHOLD:
            for target_id, bonus in targets:
                bonuses[target_id] = bonuses.get(target_id, 0) + bonus
    return bonuses


def armor_check_penalty(armor: dict | None = None, shield: dict | None = None) -> int:
    """Samlet rustnings-tjekstraf (ACP): rustning + skjold (begge ≤ 0)."""
    return (int(armor.get("armor_check", 0)) if armor else 0) \
        + (int(shield.get("armor_check", 0)) if shield else 0)


def druid_armor_violations(cls: str, armor: dict | None = None,
                           shield: dict | None = None) -> list:
    """Navne på equipped rustning/skjold der er forbudt for en druide (metal).

    Tom liste hvis ikke druide, eller intet forbudt. En druide i forbudt rustning
    kan ikke caste druidespells eller bruge su/sp-evner — mens den bæres + 24t efter.
    """
    if cls.lower() != "druid":
        return []
    return [item["name"] for item in (armor, shield)
            if item and not int(item.get("druid_ok", 1))]


def skill_total(skill: Skill, ability_scores: AbilityScores, db,
                synergy_bonus: int = 0, acp: int = 0) -> int:
    skill_def = db.get_skill(skill.id)
    if skill_def is None:
        return int(skill.ranks) + skill.misc + synergy_bonus
    # ACP rammer kun Str/Dex-skills markeret i db'en; Swim tæller dobbelt (=2).
    acp_applied = acp * int(skill_def.get("armor_check", 0) or 0)
    ability = skill_def["ability"]
    if ability == "none":
        return int(skill.ranks) + skill.misc + synergy_bonus + acp_applied
    return (int(skill.ranks) + ability_scores.modifier(ability)
            + skill.misc + synergy_bonus + acp_applied)


def save_total(base: int, ability_score: int) -> int:
    return base + (ability_score - 10) // 2


# ---------------------------------------------------------------------------
# Angreb, skade og grapple (3.5 SRD) — beregnes, gemmes aldrig i YAML
# ---------------------------------------------------------------------------

SIZE_MOD_ATTACK = {   # normal størrelses-modifier: til AC og angrebsrul
    "fine": 8, "diminutive": 4, "tiny": 2, "small": 1,
    "medium": 0, "large": -1, "huge": -2, "gargantuan": -4, "colossal": -8,
}
SIZE_MOD_GRAPPLE = {  # særlig størrelses-modifier: grapple/bull rush/trip (IKKE samme som ovenfor)
    "fine": -16, "diminutive": -12, "tiny": -8, "small": -4,
    "medium": 0, "large": 4, "huge": 8, "gargantuan": 12, "colossal": 16,
}


def size_mod_attack(size: str) -> int:
    return SIZE_MOD_ATTACK.get(size.lower(), 0)


def size_mod_grapple(size: str) -> int:
    return SIZE_MOD_GRAPPLE.get(size.lower(), 0)


def attack_total(attack: Attack, ability_scores: AbilityScores,
                 bab: int, size: str) -> dict:
    """Beregn til-hit og skade-streng for ét angreb.

    Til-hit: bab + ability-mod (Str for melee, Dex for ranged) + størrelse + bonus.
    Skade: fixed_damage hvis sat (spell/touch), ellers base_damage + floor(Str-mod ·
    str_damage_mult). Str-delen skjules helt når den er 0.
    """
    hit_ability = "dex" if attack.kind in ("ranged", "ranged_touch") else "str"
    to_hit = (bab + ability_scores.modifier(hit_ability)
              + size_mod_attack(size) + attack.bonus)

    if attack.fixed_damage:
        damage = attack.fixed_damage
    else:
        str_bonus = math.floor(ability_scores.modifier("str") * attack.str_damage_mult)
        if attack.str_damage_mult == 0 or str_bonus == 0:
            damage = attack.base_damage
        else:
            damage = f"{attack.base_damage}{str_bonus:+d}"

    return {"to_hit": to_hit, "damage": damage}


def grapple_total(bab: int, str_score: int, size: str) -> int:
    """Grapple-modifier: bab + Str-mod + den SÆRLIGE grapple-størrelses-modifier."""
    return bab + (str_score - 10) // 2 + size_mod_grapple(size)


def initiative_total(ability_scores: AbilityScores, feats: list, misc: int = 0) -> int:
    """Initiativ: Dex-mod + Improved Initiative (+4 hvis feat'en haves) + misc."""
    feat_bonus = 4 if "improved_initiative" in {str(f).lower() for f in feats} else 0
    return ability_scores.modifier("dex") + feat_bonus + misc


def armor_class(ability_scores: AbilityScores, size: str, *,
                armor: dict | None = None, shield: dict | None = None,
                enc_max_dex: int | None = None,
                natural: int = 0, deflection: int = 0,
                dodge: int = 0, misc: int = 0) -> dict:
    """Beregn AC, touch-AC og flat-footed-AC (3.5 SRD).

    armor/shield er rækker fra armor-tabellen (dict) eller None. Dex-bonus til AC
    cappes af det laveste af rustningens/skjoldets max_dex og encumbrance-max_dex
    (en Dex-straf rammer altid fuldt). Touch ignorerer rustning/skjold/naturlig
    armor; flat-footed mister Dex-bonus og dodge (men beholder en Dex-straf).
    """
    armor_bonus = (armor["armor_bonus"] if armor else 0) \
        + (shield["armor_bonus"] if shield else 0)
    size_mod = size_mod_attack(size)
    dex = ability_scores.modifier("dex")

    caps = [c for c in (
        armor.get("max_dex") if armor else None,
        shield.get("max_dex") if shield else None,
        enc_max_dex,
    ) if c is not None]
    dex_to_ac = min([dex, *caps]) if caps else dex
    dex_penalty = min(dex_to_ac, 0)   # bevares når flat-footed

    full = 10 + armor_bonus + dex_to_ac + size_mod + natural + deflection + dodge + misc
    touch = 10 + dex_to_ac + size_mod + deflection + dodge + misc
    flat = 10 + armor_bonus + size_mod + natural + deflection + misc + dex_penalty
    return {"ac": full, "touch": touch, "flat_footed": flat}


def xp_to_next_level(current_level: int) -> int | None:
    """XP required to reach current_level + 1. Returns None at max level."""
    next_level = current_level + 1
    if next_level >= len(XP_THRESHOLDS):
        return None
    return XP_THRESHOLDS[next_level]


def xp_progress(xp: int, level: int) -> dict:
    """Returns XP progress info for display."""
    current_threshold = XP_THRESHOLDS[level] if level < len(XP_THRESHOLDS) else 0
    next_threshold = xp_to_next_level(level)
    if next_threshold is None:
        return {"xp": xp, "level": level, "next": None, "pct": 100, "ready": False}
    span = next_threshold - current_threshold
    earned = xp - current_threshold
    pct = max(0, min(100, int(earned * 100 / span))) if span > 0 else 100
    return {
        "xp": xp,
        "level": level,
        "current_threshold": current_threshold,
        "next": next_threshold,
        "pct": pct,
        "ready": xp >= next_threshold,
    }


def carry_limits(str_score: int, size: str = "medium") -> dict:
    """Returns light/medium/heavy load limits in lbs for a creature."""
    clamped_str = max(1, min(str_score, 20))
    base_light = _LIGHT_LOAD_MEDIUM[clamped_str]
    multiplier = _SIZE_CARRY_MULTIPLIER.get(size, 1.0)
    light = base_light * multiplier
    medium = light * 2
    heavy = light * 3
    return {"light": light, "medium": medium, "heavy": heavy}


def encumbrance_level(str_score: int, total_weight: float, size: str = "medium") -> str:
    """Returns 'Light', 'Medium', 'Heavy', or 'Overloaded'."""
    limits = carry_limits(str_score, size)
    if total_weight <= limits["light"]:
        return "Light"
    if total_weight <= limits["medium"]:
        return "Medium"
    if total_weight <= limits["heavy"]:
        return "Heavy"
    return "Overloaded"


def total_weight(inventory: list[InventoryItem]) -> float:
    return sum(item.weight * item.qty for item in inventory)


_HIT_DIE = {
    "barbarian": 12, "fighter": 10, "paladin": 10,
    "ranger": 8, "cleric": 8, "druid": 8, "monk": 8,
    "bard": 6, "rogue": 6, "sorcerer": 4, "wizard": 4,
}
_SKILL_POINTS = {
    "rogue": 8, "ranger": 6, "bard": 6,
    "druid": 4, "barbarian": 4, "monk": 4,
    "fighter": 2, "paladin": 2, "cleric": 2, "sorcerer": 2, "wizard": 2,
}
_CLASS_SKILLS: dict[str, set[str]] = {
    "druid": {
        "concentration", "craft", "diplomacy", "handle_animal", "heal",
        "knowledge_nature", "knowledge_geography", "listen",
        "profession", "profession_herbalist", "ride",
        "spellcraft", "spot", "survival", "swim",
    },
    "cleric": {
        "concentration", "craft", "diplomacy", "heal",
        "knowledge_arcana", "knowledge_history", "knowledge_planes",
        "knowledge_religion", "profession", "spellcraft",
    },
    "ranger": {
        "climb", "concentration", "craft", "handle_animal", "heal",
        "hide", "jump", "knowledge_dungeoneering", "knowledge_geography",
        "knowledge_nature", "listen", "move_silently", "profession",
        "ride", "search", "spot", "survival", "swim", "use_rope",
    },
}


def hit_die(cls: str) -> int:
    return _HIT_DIE.get(cls.lower(), 8)


def skill_points_per_level(cls: str, int_modifier: int, race: str = "") -> int:
    race_bonus = 1 if race.lower() == "human" else 0
    return max(1, _SKILL_POINTS.get(cls.lower(), 2) + int_modifier + race_bonus)


def is_feat_level(level: int) -> bool:
    return level == 1 or level % 3 == 0


def is_ability_level(level: int) -> bool:
    return level % 4 == 0


def class_skills(cls: str) -> set[str]:
    return _CLASS_SKILLS.get(cls.lower(), set())


# ---------------------------------------------------------------------------
# Race-data — bruges KUN af karaktergeneratoren ved oprettelse. Motoren har
# ingen mekanisk race-logik (scores gemmes som endelige tal, racial_traits er
# fri tekst); disse data lader generatoren lægge ability-justeringer på, sætte
# size/speed, lægge racial skill-bonusser i skills' misc, og pre-udfylde
# racial_traits i samme format som de håndskrevne karakterer bruger.
# ---------------------------------------------------------------------------
_RACES: dict[str, dict] = {
    "human": {
        "size": "medium", "speed": 30,
        "ability_adjust": {},
        "skill_bonuses": {},
        "bonus_feats": 1,                 # ekstra feat ved level 1 (skill point håndteres i skill_points_per_level)
        "traits": {
            "bonus_feat": "1 ekstra feat ved level 1",
            "skill_points": "+1 skill point pr. level (medregnet automatisk)",
            "size": "Medium",
            "speed": "30 ft.",
        },
    },
    "elf": {
        "size": "medium", "speed": 30,
        "ability_adjust": {"dex": 2, "con": -2},
        "skill_bonuses": {"listen": 2, "spot": 2, "search": 2},
        "bonus_feats": 0,
        "traits": {
            "stat_mods": "+2 DEX, -2 CON",
            "immunities": "Immun over for magisk sleep; +2 på saves mod enchantment",
            "low_light_vision": True,
            "keen_senses": "+2 på Listen, Spot og Search; automatisk Search-tjek for hemmelige døre inden for 5 ft.",
            "weapon_proficiency": "Longsword, rapier, longbow, shortbow",
            "size": "Medium", "speed": "30 ft.",
        },
    },
    "gnome": {
        "size": "small", "speed": 20,
        "ability_adjust": {"con": 2, "str": -2},
        "skill_bonuses": {"listen": 2},
        "bonus_feats": 0,
        "traits": {
            "stat_mods": "+2 CON, -2 STR",
            "size": "Small",
            "size_bonuses": "+1 AC, +1 angreb, +4 Hide",
            "low_light_vision": True,
            "illusion_save_bonus": 2,
            "illusion_dc_bonus": 1,
            "attack_bonus_vs": "Kobolder og goblinoids +1",
            "dodge_ac_vs": "Giant-type monstre +4",
            "listen_bonus": 2,
            "spell_like_abilities": [
                {"id": "speak_with_animals", "note": "gravende dyr", "freq": "1/dag"},
                {"id": "dancing_lights", "freq": "1/dag"},
                {"id": "ghost_sound", "freq": "1/dag"},
                {"id": "prestidigitation", "freq": "1/dag"},
            ],
        },
    },
}


def race_data(race: str) -> dict:
    """Race-data (size, speed, ability-justeringer, skill-bonusser, traits) eller {}."""
    return _RACES.get(race.lower(), {})


def apply_racial_adjustments(base_scores: dict, race: str) -> dict:
    """Læg racens ability-justeringer på basis-scores → endelige scores."""
    adj = race_data(race).get("ability_adjust", {})
    return {k: int(base_scores.get(k, 10)) + adj.get(k, 0)
            for k in ("str", "dex", "con", "int", "wis", "cha")}


def level1_feat_count(race: str) -> int:
    """Antal feats spilleren selv vælger ved level 1 (1 + evt. race-bonus-feat)."""
    return 1 + race_data(race).get("bonus_feats", 0)


def class_bonus_feats(cls: str) -> list[str]:
    """Feats klassen giver gratis ved level 1 (tæller ikke mod de valgte)."""
    return ["track"] if cls.lower() == "ranger" else []


def class_needs_domains(cls: str) -> bool:
    return cls.lower() == "cleric"


def base_skill_points(cls: str) -> int:
    """Klassens skill points pr. level før INT/race (til generatorens budget-preview)."""
    return _SKILL_POINTS.get(cls.lower(), 2)


def spell_like_dc(spell_level: int, cha_modifier: int, extra: int = 0) -> int:
    """Save-DC for en spell-like ability: 10 + spell level + Cha-modifier.

    Gnomens SLA'er er Cha-baserede (SRD). `extra` rummer fx gnomens +1 til
    DC for illusionsskoler.
    """
    return 10 + spell_level + cha_modifier + extra


def encumbrance_consequences(enc_level: str, base_speed: int) -> dict:
    """Returns encumbrance penalties per D&D 3.5 PHB p.162."""
    if enc_level == "Light":
        return {"max_dex": None, "check_penalty": 0, "speed": base_speed, "run": 4}
    sq = base_speed // 5
    enc_speed = max(5, (sq - sq // 3) * 5)
    if enc_level == "Medium":
        return {"max_dex": 3, "check_penalty": -3, "speed": enc_speed, "run": 4}
    if enc_level == "Heavy":
        return {"max_dex": 1, "check_penalty": -6, "speed": enc_speed, "run": 3}
    return {"max_dex": 0, "check_penalty": -6, "speed": 5, "run": 3}


def wis_bonus_spells(wis_score: int) -> dict[int, int]:
    """Returns extra spell slots per spell level from high Wisdom (D&D 3.5 table).

    For WIS modifier m, spell level L gets (m - L) // 4 + 1 bonus slots when m >= L.
    """
    mod = (wis_score - 10) // 2
    if mod <= 0:
        return {}
    bonus: dict[int, int] = {}
    for slot_level in range(1, 10):
        if mod >= slot_level:
            bonus[slot_level] = (mod - slot_level) // 4 + 1
    return bonus


def spell_slots_total(
    class_level_data: dict, wis_score: int
) -> dict[int, int]:
    """Returns total spell slots per level including Wisdom bonus.

    WIS bonus only applies to levels where the class already has ≥1 base slot,
    and never to level-0 cantrips (per D&D 3.5 rules).
    """
    base = {i: class_level_data[f"spells_{i}"] for i in range(10)}
    bonus = wis_bonus_spells(wis_score)
    return {
        lvl: base[lvl] + (bonus.get(lvl, 0) if lvl > 0 else 0)
        for lvl in range(10)
        if base[lvl] > 0
    }
