"""Dataklasser og beregningslogik for D&D 3.5 karakterark."""
import io
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

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
    source: str = "weapon"         # weapon | spell — spell-angreb er betingede (kræver aktiv spell)
    requires: str = ""             # navn på buff der skal være aktiv før angrebet vises (tom = altid)


@dataclass
class InventoryItem:
    name: str = ""              # tom => navn slås op fra katalog via ref
    weight: float = 0.0         # kun for custom genstande; katalog-vægt slås op via ref
    qty: int = 1
    notes: str = ""
    ref: str = ""               # "tabel/id" i kataloget (weapons|armor|items); tom = custom
    state: str = "backpack"     # wielded | worn | backpack | stored | dropped
    bonus: int = 0              # til-hit-bonus på afledte angreb (masterwork/feat/TWF)
    str_mult: float | None = None  # override af Str-til-skade (None = default fra våbentype)
    two_handed: bool = False    # enhåndsvåben brugt tohånds → ×1,5 Str (hvis str_mult ikke sat)
    masterwork: bool = False    # rustning/skjold: mesterværk → ACP forbedres med +1 (mod 0)
    enhancement: int = 0        # rustning/skjold: magisk +N til AC (≥1 medfører masterwork)


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
    spells_active: dict = field(default_factory=dict)  # spells "I brug" (varighed kører) — {level: [index]}
    spell_charges: dict = field(default_factory=dict)  # ladninger tilbage pr. aktiv spell — {"level-index": antal}
    conditions: list = field(default_factory=list)
    buffs: list = field(default_factory=list)  # aktive positive effekter: {name, note, affects, spell_id?}
    languages: list = field(default_factory=list)  # kendte sprog (automatiske + valgte bonussprog)
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



# ---------------------------------------------------------------------------
# Beregninger
# ---------------------------------------------------------------------------

# Effekt-motoren bor nu i effects.py; character.py re-eksporterer dens offentlige
# navne (façade), så de mange char_module.resolve_modifiers / effective_ability_scores-
# kald rundt om i app/companion/tests fortsat virker uændret. Migrering til direkte
# imports er en separat, senere oprydning.
from effects import (ABILITIES, SAVE_TARGETS, resolve_modifiers,  # noqa: F401
                     resolve_ac_bonuses, resolve_target, save_effect_bonus,
                     skill_effect_bonus, conditional_modifiers, con_temp_hp,
                     effective_ability_scores)


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
                synergy_bonus: int = 0, acp: int = 0, effect_bonus: int = 0) -> int:
    skill_def = db.get_skill(skill.id)
    if skill_def is None:
        return int(skill.ranks) + skill.misc + synergy_bonus + effect_bonus
    # ACP rammer kun Str/Dex-skills markeret i db'en; Swim tæller dobbelt (=2).
    acp_applied = acp * int(skill_def.get("armor_check", 0) or 0)
    ability = skill_def["ability"]
    if ability == "none":
        return int(skill.ranks) + skill.misc + synergy_bonus + acp_applied + effect_bonus
    return (int(skill.ranks) + ability_scores.modifier(ability)
            + skill.misc + synergy_bonus + acp_applied + effect_bonus)


def save_total(base: int, ability_score: int, racial: int = 0,
               effect_bonus: int = 0) -> int:
    """Save = klasse-base + ability-mod + evt. racial bonus + effekt-bonus.

    racial holdes som rå race-data (race_data()['save_bonus']) og lægges på her —
    aldrig gemt sammen med klasse-basen i YAML. effect_bonus er nettobonus fra
    aktive effekter (Resistance, shaken/sickened …); kun-mod-X-bonusser hører
    IKKE med her (de vises som betinget note).
    """
    return base + (ability_score - 10) // 2 + racial + effect_bonus


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
                 bab: int, size: str, extra_bonus: int = 0,
                 extra_damage: int = 0) -> dict:
    """Beregn til-hit og skade-streng for ét angreb.

    Til-hit: bab + ability-mod (Str for melee, Dex for ranged) + størrelse + bonus
    + extra_bonus (Bless, Magic Fang, Divine Favor, shaken/sickened-straffe).
    Skade: fixed_damage hvis sat (spell/touch — extra_damage tæller ikke, det er
    ikke våbenskade), ellers base_damage + floor(Str-mod · str_damage_mult)
    + extra_damage. Skade-tillægget skjules når totalbonus er 0.
    """
    hit_ability = "dex" if attack.kind in ("ranged", "ranged_touch") else "str"
    to_hit = (bab + ability_scores.modifier(hit_ability)
              + size_mod_attack(size) + attack.bonus + extra_bonus)

    if attack.fixed_damage:
        damage = attack.fixed_damage
    else:
        str_bonus = math.floor(ability_scores.modifier("str") * attack.str_damage_mult)
        total_bonus = str_bonus + extra_damage
        if total_bonus == 0:
            damage = attack.base_damage
        else:
            damage = f"{attack.base_damage}{total_bonus:+d}"

    return {"to_hit": to_hit, "damage": damage}


def grapple_total(bab: int, str_score: int, size: str) -> int:
    """Grapple-modifier: bab + Str-mod + den SÆRLIGE grapple-størrelses-modifier."""
    return bab + (str_score - 10) // 2 + size_mod_grapple(size)


def initiative_total(ability_scores: AbilityScores, feats: list, misc: int = 0,
                     effect_bonus: int = 0) -> int:
    """Initiativ: Dex-mod + Improved Initiative (+4 hvis feat'en haves) + misc
    + effekt-bonus (fx deafened −4)."""
    feat_bonus = 4 if "improved_initiative" in {feat_id(f).lower() for f in feats} else 0
    return ability_scores.modifier("dex") + feat_bonus + misc + effect_bonus


def armor_class(ability_scores: AbilityScores, size: str, *,
                armor: dict | None = None, shield: dict | None = None,
                enc_max_dex: int | None = None,
                natural: int = 0, deflection: int = 0,
                dodge: int = 0, misc: int = 0, lose_dex: bool = False) -> dict:
    """Beregn AC, touch-AC og flat-footed-AC (3.5 SRD).

    armor/shield er rækker fra armor-tabellen (dict) eller None. Dex-bonus til AC
    cappes af det laveste af rustningens/skjoldets max_dex og encumbrance-max_dex
    (en Dex-straf rammer altid fuldt). Touch ignorerer rustning/skjold/naturlig
    armor; flat-footed mister Dex-bonus og dodge (men beholder en Dex-straf).

    lose_dex (blinded/cowering/stunned/flat-footed-tilstand): den normale AC og
    touch mister også Dex-bonus og dodge — som flat-footed — men beholder en
    Dex-STRAF. Flat-footed-tallet er uændret.
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

    # Mister man Dex-til-AC (blinded m.fl.), behandles normal-AC/touch som
    # flat-footed: ingen Dex-bonus, ingen dodge — kun en evt. Dex-straf.
    ac_dex = dex_penalty if lose_dex else dex_to_ac
    ac_dodge = 0 if lose_dex else dodge

    full = 10 + armor_bonus + ac_dex + size_mod + natural + deflection + ac_dodge + misc
    touch = 10 + ac_dex + size_mod + deflection + ac_dodge + misc
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


# Tilstande en genstand kan have. CARRIED_STATES tæller med i båret vægt.
INVENTORY_STATES = {"wielded", "worn", "backpack", "stored", "dropped"}
CARRIED_STATES = {"wielded", "worn", "backpack"}

# Hvilken tabel-præfiks i ref => skaleringsklasse for weight_for_size
_REF_LOOKUP = {"weapons": "get_weapon", "armor": "get_armor", "items": "get_item"}


def weight_for_size(base_weight: float, kind: str, size: str = "medium") -> float:
    """Udregn faktisk vægt for en skabnings størrelse fra Medium-basisvægt.

    kind: 'half'    -> våben/rustning (Small ×½, Large ×2)
          'quarter' -> gear m. SRD-fodnote 1 (Small ×¼)
          'none'    -> uændret med størrelse (fakkel, reb, custom genstande)
    """
    size = (size or "medium").lower()
    if size == "small":
        factor = {"half": 0.5, "quarter": 0.25}.get(kind, 1.0)
    elif size == "large":
        factor = {"half": 2.0}.get(kind, 1.0)
    else:  # medium (og uhåndterede størrelser) — ingen skalering
        factor = 1.0
    return round(base_weight * factor, 3)


def resolve_item(item: InventoryItem, db, size: str = "medium") -> dict:
    """Slå en inventory-post op mod kataloget og udregn dens faktiske vægt.

    Returnerer navn, enheds- og totalvægt (størrelses-justeret), om den tæller
    som båret, samt katalog-posten (record) hvis ref peger på noget gyldigt.
    """
    name = item.name
    base_weight = item.weight
    kind = "none"
    source = None
    record = None
    if item.ref:
        table, _, oid = item.ref.partition("/")
        getter = getattr(db, _REF_LOOKUP[table], None) if table in _REF_LOOKUP else None
        record = getter(oid) if getter else None
        if record:
            source = table
            name = item.name or record["name"]
            base_weight = record.get("weight") or 0.0
            if table in ("weapons", "armor"):
                kind = "half"
            elif table == "items":
                kind = "quarter" if record.get("small_quarter") else "none"
                # Bundter (ammo) opgives per bundt i kataloget; qty = enkelte
                # enheder, så vægten regnes per styk.
                bundle = record.get("bundle") or 1
                if bundle > 1:
                    base_weight = base_weight / bundle
    unit = weight_for_size(base_weight, kind, size)
    return {
        "name": name,
        "unit_weight": unit,
        "weight": round(unit * item.qty, 3),
        "kind": kind,
        "carried": item.state in CARRIED_STATES,
        "state": item.state,
        "source": source,
        "record": record,
    }


def carried_weight(inventory: list[InventoryItem], db, size: str = "medium") -> float:
    """Samlet båret vægt — kun poster i wielded/worn/backpack, størrelses-justeret."""
    return round(
        sum(r["weight"] for r in (resolve_item(i, db, size) for i in inventory) if r["carried"]),
        3,
    )


# Default Str-til-skade-multiplier ud fra våbentype (kan overrides pr. inventory-post)
_DEFAULT_STR_MULT = {
    "two-handed": 1.5, "one-handed": 1.0, "light": 1.0, "unarmed": 1.0, "ranged": 0.0,
}


def derive_attacks(inventory: list[InventoryItem], db, size: str = "medium") -> list[Attack]:
    """Lav Attack-objekter ud fra våben i tilstand 'wielded'.

    Skade/crit/type/range slås op i weapons-kataloget (dmg_s for Small, ellers
    dmg_m). Str-til-skade tages fra posten (str_mult), ellers two_handed-flaget
    (×1,5 for enhåndsvåben), ellers default fra weapon_class. bonus = til-hit.
    """
    attacks: list[Attack] = []
    for item in inventory:
        if item.state != "wielded" or not item.ref.startswith("weapons/"):
            continue
        w = db.get_weapon(item.ref.split("/", 1)[1])
        if not w:
            continue
        wclass = w["weapon_class"]
        if item.str_mult is not None:
            mult = item.str_mult
        elif item.two_handed and wclass in ("light", "one-handed"):
            mult = 1.5
        else:
            mult = _DEFAULT_STR_MULT.get(wclass, 1.0)
        # Dobbeltvåben (fx quarterstaff "1d6/1d6") → brug første ende til ét angreb
        base = (w["dmg_s"] if size.lower() == "small" else w["dmg_m"]) or ""
        base = base.split("/")[0]
        attacks.append(Attack(
            name=item.name or w["name"],
            kind="ranged" if wclass == "ranged" else "melee",
            base_damage=base,
            str_damage_mult=mult,
            bonus=item.bonus,
            crit=w["critical"] or "x2",
            type=w["damage_type"] or "",
            range=f"{w['range_ft']} ft." if w["range_ft"] else "",
        ))
    return attacks


def spell_charge_key(level: int, index: int) -> str:
    """Nøgle til spell_charges-dict'en for en spell på (level, index)."""
    return f"{level}-{index}"


def spell_attack_damage(row: dict, caster_level: int) -> str:
    """Udregn skade-strengen for et katalog-spell-angreb (gemmes aldrig).

    base_damage + min(floor(caster_level * dmg_per_level / dmg_per_level_div),
                      dmg_per_level_max) + dmg_bonus.
    Produce Flame (1d6, +1/niv, cap 5) ved niveau 2 → "1d6+2".
    Flame Blade (1d8, +1/2 niv, cap 10) ved niveau 5 → "1d8+2".
    Magic Stone (1d6, +1 flad) → "1d6+1".
    """
    bonus = int(row.get("dmg_bonus") or 0)
    per = int(row.get("dmg_per_level") or 0)
    if per:
        div = int(row.get("dmg_per_level_div") or 1)
        lvl_bonus = (caster_level * per) // div
        cap = row.get("dmg_per_level_max")
        if cap is not None:
            lvl_bonus = min(lvl_bonus, int(cap))
        bonus += lvl_bonus
    base = row["base_damage"]
    return f"{base}{bonus:+d}" if bonus else base


def derive_spell_attacks(char: "Character", db) -> list[dict]:
    """Lav angreb ud fra spells der står på "I brug" via spell_attacks-kataloget.

    Hver post: {attack, level, index, spell_id, charges_max, charges_remaining,
    alt_note}. charges_max=None betyder ubegrænset (ingen nedtælling).
    """
    out: list[dict] = []
    for lvl, indices in (char.spells_active or {}).items():
        prepared = char.spells_prepared.get(lvl, [])
        for idx in indices:
            if not (0 <= idx < len(prepared)):
                continue
            sid = prepared[idx]
            for r in db.get_spell_attacks(sid):
                atk = Attack(
                    name=r["label"],
                    kind=r["kind"],
                    str_damage_mult=0,
                    fixed_damage=spell_attack_damage(r, char.level),
                    bonus=int(r.get("to_hit") or 0),
                    crit=r.get("crit") or "x2",
                    type=r.get("dmg_type") or "",
                    range=f"{r['range_ft']} ft." if r.get("range_ft") else "",
                    source="spell",
                )
                charges_max = r.get("charges")
                key = spell_charge_key(lvl, idx)
                remaining = (char.spell_charges.get(key, charges_max)
                             if charges_max else None)
                out.append({
                    "attack": atk, "level": lvl, "index": idx, "spell_id": sid,
                    "charges_max": charges_max, "charges_remaining": remaining,
                    "alt_note": r.get("alt_note") or "",
                })
    return out


def spell_max_charges(spell_id: str, db) -> int | None:
    """Største ladnings-tal blandt en spells katalog-angreb (None hvis ingen)."""
    vals = [r["charges"] for r in db.get_spell_attacks(spell_id) if r.get("charges")]
    return max(vals) if vals else None


def _effective_armor_row(rec: dict, item: InventoryItem) -> dict:
    """Påfør masterwork/magi på en katalog-række → en effektiv kopi.

    Reglerne (3.5 SRD): mesterværk forbedrer rustnings-tjekstraffen (ACP) med +1
    mod 0 (aldrig positiv); en enhancement-bonus lægges til AC og medfører altid
    mesterværk (magisk rustning er pr. definition mesterværk). Resten af rækken
    (max_dex, spell_failure, druid_ok …) er uændret. Vi kopierer rækken, så
    db'ens cache aldrig muteres.
    """
    masterwork = item.masterwork or item.enhancement >= 1
    if not masterwork and item.enhancement == 0:
        return rec
    eff = dict(rec)
    if masterwork:
        eff["armor_check"] = min(0, int(rec.get("armor_check", 0)) + 1)
    if item.enhancement:
        eff["armor_bonus"] = int(rec.get("armor_bonus", 0)) + item.enhancement
    # Vis-navn afspejler tilpasningen (fx "Studded Leather +1 (mesterværk)").
    label = rec.get("name", "")
    if item.enhancement:
        label = f"{label} +{item.enhancement}"
    if item.masterwork and not item.enhancement:
        label = f"{label} (mesterværk)"
    eff["name"] = label
    return eff


def active_buff_keys(buffs: list) -> set:
    """Identiteter for aktive buffs — buff-navn og evt. spell_id, lowercased.

    Bruges til at afgøre om et betinget spell-angreb (Attack.requires) skal vises:
    angrebet matcher hvis dets 'requires' står i dette sæt.
    """
    keys: set[str] = set()
    for b in buffs or []:
        name = str(b.get("name", "")).strip().lower()
        if name:
            keys.add(name)
        sid = str(b.get("spell_id", "")).strip().lower()
        if sid:
            keys.add(sid)
    return keys


def active_spell_keys(spells_prepared: dict, spells_active: dict, db) -> set:
    """Identiteter for spells der står på 'I brug' — spell-id og navn, lowercased.

    Et betinget spell-angreb (Attack.requires) vises når dets 'requires' matcher
    et af disse — dvs. når den spell der skaber angrebet er aktiv (varighed kører).
    Erstatter den tidligere buff-baserede oplåsning.
    """
    keys: set[str] = set()
    for lvl, indices in (spells_active or {}).items():
        prepared = (spells_prepared or {}).get(lvl, [])
        for idx in indices:
            if 0 <= idx < len(prepared):
                sid = str(prepared[idx]).strip().lower()
                if sid:
                    keys.add(sid)
                row = db.get_spell(prepared[idx])
                if row and row.get("name"):
                    keys.add(str(row["name"]).strip().lower())
    return keys


def attack_visible(attack: Attack, active_keys: set) -> bool:
    """Skal et angreb vises på arket?

    Våben og spell-angreb uden 'requires' vises altid. Et spell-angreb MED
    'requires' vises kun når den spell der skaber det står på 'I brug'
    (dens id eller navn findes i active_keys).
    """
    if attack.source == "spell" and attack.requires:
        return attack.requires.strip().lower() in active_keys
    return True


def equipped_armor(inventory: list[InventoryItem], db):
    """Find båret rustning + skjold i inventaret (state=worn, ref til armor).

    Returnerer (armor_row, shield_row) som katalog-dicts eller None. Tager den
    første af hver slags: armor = type light/medium/heavy, shield = type shield.
    Masterwork/magi fra inventory-posten er påført rækken (se _effective_armor_row).
    """
    armor_row = shield_row = None
    for item in inventory:
        if item.state != "worn" or not item.ref.startswith("armor/"):
            continue
        rec = db.get_armor(item.ref.split("/", 1)[1])
        if not rec:
            continue
        rec = _effective_armor_row(rec, item)
        if rec["type"] == "shield":
            shield_row = shield_row or rec
        elif rec["type"] in ("light", "medium", "heavy"):
            armor_row = armor_row or rec
    return armor_row, shield_row


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
    "rogue": {
        "appraise", "balance", "bluff", "climb", "craft", "decipher_script",
        "diplomacy", "disable_device", "disguise", "escape_artist", "forgery",
        "gather_information", "hide", "intimidate", "jump", "knowledge_local",
        "listen", "move_silently", "open_lock", "perform", "profession",
        "search", "sense_motive", "sleight_of_hand", "spot", "swim", "tumble",
        "use_magic_device", "use_rope",
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
        # Sprog: automatiske kan altid; bonus vælges (antal = Int-mod). Human kan
        # vælge et hvilket som helst standardsprog (sættes dynamisk = STANDARD_LANGUAGES).
        "languages": {"automatic": ["Common"], "bonus": "any"},
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
        "languages": {"automatic": ["Common", "Elven"],
                      "bonus": ["Draconic", "Gnoll", "Gnome", "Goblin", "Orc", "Sylvan"]},
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
        "languages": {"automatic": ["Common", "Gnome"],
                      "bonus": ["Draconic", "Dwarven", "Elven", "Giant", "Goblin", "Orc"]},
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
    "halfling": {
        "size": "small", "speed": 20,
        "ability_adjust": {"dex": 2, "str": -2},
        # Racial skill-affinitet (ikke størrelses-Hide — den er kun tekst, som hos gnome).
        "skill_bonuses": {"climb": 2, "jump": 2, "move_silently": 2, "listen": 2},
        "languages": {"automatic": ["Common", "Halfling"],
                      "bonus": ["Dwarven", "Elven", "Gnome", "Goblin", "Orc"]},
        "save_bonus": 1,                  # +1 på ALLE saves (racial, lægges på i save_total)
        "bonus_feats": 0,
        "traits": {
            "stat_mods": "+2 DEX, -2 STR",
            "size": "Small",
            "size_bonuses": "+1 AC, +1 angreb, +4 Hide",
            "saves": "+1 på alle saves (medregnet i tallene)",
            "fear_save_bonus": "+2 morale mod frygt (oveni racial +1)",
            "thrown_attack_bonus": "+1 angreb med kastevåben og slynge",
            "skill_affinity": "+2 Climb, Jump og Move Silently; +2 Listen",
            "favored_class": "Rogue",
        },
    },
}


def race_data(race: str) -> dict:
    """Race-data (size, speed, ability-justeringer, skill-bonusser, traits) eller {}."""
    return _RACES.get(race.lower(), {})


# Standardsprog i SRD. Druidic er hemmeligt (kun druider) og er IKKE i "any"-puljen
# — det gives kun gennem klassen.
STANDARD_LANGUAGES = [
    "Abyssal", "Aquan", "Auran", "Celestial", "Common", "Draconic", "Dwarven",
    "Elven", "Giant", "Gnoll", "Gnome", "Goblin", "Halfling", "Ignan",
    "Infernal", "Orc", "Sylvan", "Terran", "Undercommon",
]

# Klasse-sprog: 'automatic' gives gratis (tæller ikke mod Int-bonus), 'bonus' kan
# vælges som et af bonussprogene. Klasser uden særlige sprog står ikke her.
_CLASS_LANGUAGES: dict[str, dict] = {
    "druid":  {"automatic": ["Druidic"], "bonus": ["Sylvan"]},
    "cleric": {"automatic": [], "bonus": ["Abyssal", "Celestial", "Infernal"]},
    "wizard": {"automatic": [], "bonus": ["Draconic"]},
}


def class_languages(cls: str) -> dict:
    """Klassens sprog ({'automatic': [...], 'bonus': [...]}) eller tomt."""
    return _CLASS_LANGUAGES.get(cls.lower(), {"automatic": [], "bonus": []})


def race_bonus_languages(race: str) -> list[str]:
    """Racens bonussprog-liste ('any' → alle standardsprog)."""
    bonus = race_data(race).get("languages", {}).get("bonus", [])
    return list(STANDARD_LANGUAGES) if bonus == "any" else list(bonus)


def automatic_languages(race: str, cls: str) -> list[str]:
    """Sprog karakteren altid kan (race + klasse), uden at bruge Int-bonus."""
    langs = list(race_data(race).get("languages", {}).get("automatic", []))
    for lang in _CLASS_LANGUAGES.get(cls.lower(), {}).get("automatic", []):
        if lang not in langs:
            langs.append(lang)
    return langs


def bonus_language_pool(race: str, cls: str) -> list[str]:
    """De bonussprog man må vælge imellem (race + klasse), minus de automatiske.

    Human ('bonus': 'any') må vælge et hvilket som helst standardsprog.
    """
    race_bonus = race_data(race).get("languages", {}).get("bonus", [])
    pool = list(STANDARD_LANGUAGES) if race_bonus == "any" else list(race_bonus)
    for lang in _CLASS_LANGUAGES.get(cls.lower(), {}).get("bonus", []):
        if lang not in pool:
            pool.append(lang)
    auto = set(automatic_languages(race, cls))
    return [lang for lang in pool if lang not in auto]


def bonus_language_count(int_modifier: int) -> int:
    """Antal bonussprog = Int-mod (aldrig negativt)."""
    return max(0, int_modifier)


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


# Feats hvor man vælger et specifikt våben (gemmes som {id, weapon} i stedet for
# en ren id-streng). Bruges af generatoren, level-up og visningen.
WEAPON_CHOICE_FEATS = {"weapon_focus", "weapon_specialization", "improved_critical"}


def feat_id(entry) -> str:
    """Feat-id'et, uanset om posten er en streng eller en {id, weapon}-dict."""
    return str(entry["id"] if isinstance(entry, dict) else entry)


def feat_weapon(entry) -> str:
    """Det valgte våben for en feat-post, eller "" hvis ingen."""
    return str(entry.get("weapon", "")) if isinstance(entry, dict) else ""


def feat_label(entry, feat_row: dict | None = None) -> str:
    """Visningsnavn: feat-navn + evt. valgt våben, fx 'Weapon Focus (Longsword)'."""
    name = (feat_row or {}).get("name") or feat_id(entry)
    wpn = feat_weapon(entry)
    return f"{name} ({wpn})" if wpn else name


def class_needs_domains(cls: str) -> bool:
    return cls.lower() == "cleric"


def base_skill_points(cls: str) -> int:
    """Klassens skill points pr. level før INT/race (til generatorens budget-preview)."""
    return _SKILL_POINTS.get(cls.lower(), 2)


# ---------------------------------------------------------------------------
# Feat-prerequisite-tjek til generatoren. Prerequisites er fri tekst i db'en
# (fx "Dex 15", "Str 13, Power Attack", "Spell Focus (Conjuration)", "BAB +4",
# "Ability to turn or rebuke undead", "Wild shape class ability"). Vi parser
# klausul-for-klausul og tjekker de typer vi kan verificere; ukendte klausuler
# behandles som rådgivende (ikke-blokerende) for at undgå falske afvisninger.
# ---------------------------------------------------------------------------
_ABILITY_PREREQ_RE = re.compile(r"^(str|dex|con|int|wis|cha)\s+(\d+)$", re.I)
_BAB_PREREQ_RE = re.compile(r"(?:base attack bonus|bab)\s*\+?(\d+)", re.I)
_LEVEL_PREREQ_RE = re.compile(r"level\s+(\d+)", re.I)  # fx "Fighter level 4"


def class_can_turn_undead(cls: str) -> bool:
    return cls.lower() == "cleric"


def class_has_wild_shape(cls: str, level: int) -> bool:
    return cls.lower() == "druid" and level >= 5


def feat_prereq_unmet(prereq_text: str, owned_feat_ids, scores: dict,
                      cls: str, level: int, bab: int,
                      feat_name_to_id: dict) -> list[str]:
    """Returnér de prerequisite-klausuler der IKKE er opfyldt (tom liste = OK).

    owned_feat_ids er de feats karakteren VIL have (valgte + klassens gratis) — så
    en feat-kæde som Dodge→Mobility er gyldig når begge vælges samtidig ved level 1.
    """
    if not prereq_text or prereq_text.strip().lower() == "none":
        return []
    owned = set(owned_feat_ids)
    unmet = []
    for clause in prereq_text.split(","):
        clause = clause.strip()
        if not clause:
            continue
        m = _ABILITY_PREREQ_RE.match(clause)
        if m:
            if int(scores.get(m.group(1).lower(), 10)) < int(m.group(2)):
                unmet.append(clause)
            continue
        m = _BAB_PREREQ_RE.search(clause)
        if m:
            if bab < int(m.group(1)):
                unmet.append(clause)
            continue
        m = _LEVEL_PREREQ_RE.search(clause)
        if m:
            if level < int(m.group(1)):
                unmet.append(clause)
            continue
        low = clause.lower()
        if "turn" in low and "undead" in low:
            if not class_can_turn_undead(cls):
                unmet.append(clause)
            continue
        if "wild shape" in low:
            if not class_has_wild_shape(cls, level):
                unmet.append(clause)
            continue
        if low.startswith("proficiency"):
            continue  # kan ikke verificeres her — rådgivende
        fid = feat_name_to_id.get(low)
        if fid is not None:
            if fid not in owned:
                unmet.append(clause)
            continue
        # ukendt klausul → rådgivende, blokér ikke
    return unmet


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


# Fil-persistens bor nu i persistence.py; character.py re-eksporterer dens
# offentlige navne (façade), så char_module.load_character / save_character m.fl.
# i app.py virker uændret. Importeres SIDST, når dataklasser + feat-hjælpere er
# defineret, så persistence.py's modimport rammer et fuldt-initialiseret modul.
from persistence import (  # noqa: E402,F401
    SNAPSHOT_KEEP, load_character, save_character, write_character_file,
    restore_snapshot, snapshot_dir, list_snapshots)
