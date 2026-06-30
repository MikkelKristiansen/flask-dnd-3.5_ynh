"""Beregninger for D&D 3.5 karakterark — afledte tal udledt ved render.

Kerneprincip: gem aldrig beregnede totaler — udled dem fra base + udstyr +
effekter ved hver render. Her bor de rene regnefunktioner: skill-/save-/attack-/
grapple-/initiativ-totaler, AC, XP-progression, bæreevne/encumbrance, afledte
angreb fra inventory og spells, samt spell slots og skill-synergier. Funktionerne
tager en konkret karakters tal (og evt. db til katalog-opslag) og regner; de
holder ingen tilstand og skriver intet til disk.

character.py re-eksporterer disse navne (façade), så char_module.armor_class /
derive_attacks / save_total m.fl. virker uændret.
"""
import dataclasses
import math

from models import AbilityScores, Skill, Attack, InventoryItem, Character
from refdata import feat_id


# Point-buy (D&D 3.5 standard). Pris pr. pre-race score; interval 8-18. Budget 28
# = "standard" kampagne. Bruges af generatoren når metoden er point-buy.
POINT_BUY_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5,
                  14: 6, 15: 8, 16: 10, 17: 13, 18: 16}
POINT_BUY_BUDGET = 28


def point_buy_cost(score: int) -> int | None:
    """Point-buy-pris for én score, eller None hvis uden for 8-18."""
    return POINT_BUY_COST.get(int(score))


def point_buy_total(scores: dict) -> int:
    """Samlet point-buy-pris for de seks pre-race scores.

    Rejser ValueError hvis en score er uden for 8-18 (kan ikke købes).
    """
    total = 0
    for k in ("str", "dex", "con", "int", "wis", "cha"):
        cost = POINT_BUY_COST.get(int(scores[k]))
        if cost is None:
            raise ValueError(f"{k.upper()} skal være mellem 8 og 18 ved point-buy.")
        total += cost
    return total


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


def synergy_sources(skills: list[Skill]) -> dict[str, list[tuple[str, int]]]:
    """For hver modtager-skill: liste af (kilde-skill-id, bonus) bag synergien.

    Samme regel som compute_synergy_bonuses (kilde med ≥5 ranks), men bevarer
    HVOR bonussen kommer fra — bruges til tooltips på arket.
    """
    rank_map = {s.id: int(s.ranks) for s in skills}
    sources: dict[str, list[tuple[str, int]]] = {}
    for source_id, targets in SKILL_SYNERGIES.items():
        if rank_map.get(source_id, 0) >= SYNERGY_THRESHOLD:
            for target_id, bonus in targets:
                sources.setdefault(target_id, []).append((source_id, bonus))
    return sources


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
    # house_rule = DM tillader det trods metal-forbuddet → ingen advarsel.
    return [item["name"] for item in (armor, shield)
            if item and not int(item.get("druid_ok", 1)) and not item.get("house_rule")]


# ── Weapon & Armor Proficiency (SRD) ────────────────────────────────────────
# Manglende proficiency er IKKE et forbud: man må bruge grejet, men tager straf
# (−4 til angreb med uvant våben; rustnings-tjekstraffen rammer også angreb +
# Str/Dex-skills med uvant rustning). En house-rule pr. genstand (allowed/
# item.house_rule) fjerner straffen igen.

def weapon_proficient(weapon_row: dict | None, weapon_prof: dict | None,
                      allowed: set = frozenset()) -> bool:
    """Er man proficient med våbnet? Via kategori, eksplicit liste eller house-rule.

    weapon_prof=None → ingen proficiency-data for klassen → behandl som proficient
    (vi straffer ikke noget vi ikke kender reglerne for).
    """
    if not weapon_row or weapon_prof is None:
        return True
    wid = weapon_row.get("id", "")
    if wid in allowed:
        return True
    if weapon_row.get("category") in (weapon_prof.get("categories") or []):
        return True
    return wid in (weapon_prof.get("weapons") or [])


def armor_proficient(armor_row: dict | None, armor_prof: dict | None,
                     allowed: set = frozenset()) -> bool:
    """Er man proficient med rustningen/skjoldet? Tower shield er en egen tilladelse.

    armor_prof=None → ingen data → behandl som proficient (ingen straf).
    """
    if not armor_row or armor_prof is None:
        return True
    aid = armor_row.get("id", "")
    if aid in allowed:
        return True
    if armor_row.get("type") == "shield":
        if aid == "tower_shield":
            return bool(armor_prof.get("tower_shield"))
        return bool(armor_prof.get("shields"))
    return armor_row.get("type") in (armor_prof.get("types") or [])


def proficiency_violations(weapon_prof: dict | None, armor_prof: dict | None,
                           inventory: list, db, allowed_weapons: set = frozenset(),
                           allowed_armor: set = frozenset()) -> dict:
    """Navne på equipped grej man IKKE er proficient med (til advarsler på arket).

    Returnerer {"weapons": [navne], "armor": [navne]}. En genstand med
    house_rule=True regnes altid som tilladt (DM-undtagelse). Kun wielded våben
    og worn rustning/skjold tjekkes.
    """
    bad_weapons: list[str] = []
    bad_armor: list[str] = []
    for item in inventory:
        if item.house_rule:
            continue
        if item.state == "wielded" and item.ref.startswith("weapons/"):
            w = db.get_weapon(item.ref.split("/", 1)[1])
            if w and not weapon_proficient(w, weapon_prof, allowed_weapons):
                bad_weapons.append(item.name or w["name"])
        elif item.state == "worn" and item.ref.startswith("armor/"):
            a = db.get_armor(item.ref.split("/", 1)[1])
            if a and not armor_proficient(a, armor_prof, allowed_armor):
                bad_armor.append(item.name or a["name"])
    return {"weapons": bad_weapons, "armor": bad_armor}


def armor_attack_penalty(armor_prof: dict | None, inventory: list, db,
                         allowed_armor: set = frozenset()) -> int:
    """Ekstra angrebs-straf (≤0) fordi man bærer uvant rustning/skjold.

    SRD: bærer man rustning man ikke er proficient med, rammer dens tjekstraf
    (ACP) også alle angreb. Summerer ACP for hver uvant, ikke-house-ruled del.
    """
    penalty = 0
    for item in inventory:
        if item.house_rule or item.state != "worn" or not item.ref.startswith("armor/"):
            continue
        a = db.get_armor(item.ref.split("/", 1)[1])
        if a and not armor_proficient(a, armor_prof, allowed_armor):
            penalty += int(a.get("armor_check", 0) or 0)
    return penalty


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
                 extra_damage: int = 0, has_finesse: bool = False) -> dict:
    """Beregn til-hit og skade-streng for ét angreb.

    Til-hit: bab + ability-mod (Str for melee, Dex for ranged) + størrelse + bonus
    + extra_bonus (Bless, Magic Fang, Divine Favor, shaken/sickened-straffe).
    Skade: fixed_damage hvis sat (spell/touch — extra_damage tæller ikke, det er
    ikke våbenskade), ellers base_damage + floor(Str-mod · str_damage_mult)
    + extra_damage. Skade-tillægget skjules når totalbonus er 0.
    """
    if attack.kind in ("ranged", "ranged_touch"):
        hit_ability = "dex"
    elif has_finesse and attack.finesse:
        hit_ability = "dex" if ability_scores.modifier("dex") > ability_scores.modifier("str") else "str"
    else:
        hit_ability = "str"
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


def weight_kind(table: str, record: dict) -> str:
    """Skaleringsklasse for en katalog-række ud fra dens tabel (til weight_for_size).

    Ét sted for reglen 'hvordan skalerer vægten med størrelse': våben/rustning
    halveres/fordobles, gear med SRD-fodnote 1 firdeles for Small, resten uændret.
    """
    if table in ("weapons", "armor"):
        return "half"
    if table == "items":
        return "quarter" if record.get("small_quarter") else "none"
    return "none"


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
            kind = weight_kind(table, record)
            if table == "items":
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

# Default-hænder pr. weapon_class (fallback). Bruges når katalogets `hands` ikke er
# sat — kun ranged er flertydig (slynge=1, langbue=2), så de har eksplicit `hands`.
_WEAPON_HANDS = {
    "light": 1, "one-handed": 1, "two-handed": 2, "unarmed": 0, "ranged": 2,
}


def weapon_hands(weapon_row: dict, two_handed: bool = False) -> int:
    """Hvor mange hænder optager våbnet? Katalogets `hands` vinder; ellers udled af
    weapon_class. Et enhåndsvåben grebet med to hænder (two_handed) optager 2."""
    hands = weapon_row.get("hands")
    if hands is None:
        hands = _WEAPON_HANDS.get(weapon_row["weapon_class"], 1)
    if two_handed and weapon_row["weapon_class"] in ("light", "one-handed"):
        hands = 2
    return hands


def two_weapon_penalty(off_hand_light: bool, has_twf_feat: bool) -> tuple[int, int]:
    """Straf på (primær hånd, off-hånd) ved two-weapon fighting (SRD-tabel).

    Begge tal er ≤ 0. off_hand_light = off-hånds-våbnet er let (eller en
    dobbeltvåbens-ende). has_twf_feat = har Two-Weapon Fighting (inkl. ranger-stil).
    """
    if has_twf_feat:
        return (-2, -2) if off_hand_light else (-4, -4)
    return (-4, -8) if off_hand_light else (-6, -10)


def _twf_note(penalty: int, is_off_hand: bool) -> str:
    """Kort UI-markør for et TWF-straffet angreb ("−2 TWF (off-hånd)")."""
    if penalty == 0:
        return ""
    hand = "off-hånd" if is_off_hand else "primær"
    return f"{penalty:+d} TWF ({hand})"


def hand_usage(inventory: list[InventoryItem], db) -> dict:
    """Hvor mange hænder optager wielded våben + båret skjold? (Medium = 2 hænder.)

    Returnerer {used, parts: [(navn, hænder)], over}. over=True når used > 2 →
    blød advarsel i UI'en (man kan ikke fysisk holde så meget). Tower shield = 2.
    """
    used = 0
    parts: list[tuple[str, int]] = []
    for item in inventory:
        if item.state == "wielded" and item.ref.startswith("weapons/"):
            w = db.get_weapon(item.ref.split("/", 1)[1])
            if w:
                hands = weapon_hands(w, item.two_handed)
                used += hands
                parts.append((item.name or w["name"], hands))
        elif item.state == "worn" and item.ref.startswith("armor/"):
            a = db.get_armor(item.ref.split("/", 1)[1])
            if a and a.get("type") == "shield":
                hands = 2 if a.get("id") == "tower_shield" else 1
                used += hands
                parts.append((a["name"], hands))
    return {"used": used, "parts": parts, "over": used > 2}


def twf_context(cls: str, level: int, class_features: dict | None,
                feat_ids: list, armor_row: dict | None) -> dict:
    """Saml hvilke TWF-niveauer karakteren har — fodres til derive_attacks.

    Two-Weapon Fighting kommer enten fra feat, eller fra rangerens combat style
    (two-weapon) fra niveau 2 OG i let/ingen rustning. Improved/Greater kommer
    fra feats, eller rangerens stil-opgradering ved niveau 6/11.
    """
    style = (class_features or {}).get("Combat Style", "")
    light_or_none = armor_row is None or armor_row.get("type") == "light"
    ranger_twf = (cls.lower() == "ranger" and "two" in style.lower()
                  and level >= 2 and light_or_none)
    return {
        "has_twf": "two_weapon_fighting" in feat_ids or ranger_twf,
        "has_improved": ("improved_two_weapon_fighting" in feat_ids
                         or (ranger_twf and level >= 6)),
        "has_greater": ("greater_two_weapon_fighting" in feat_ids
                        or (ranger_twf and level >= 11)),
        "ranger_style": ranger_twf,
    }


def derive_attacks(inventory: list[InventoryItem], db, size: str = "medium",
                   weapon_prof: dict | None = None,
                   allowed_weapons: set = frozenset(),
                   twf: dict | None = None) -> list[Attack]:
    """Lav Attack-objekter ud fra våben i tilstand 'wielded'.

    Skade/crit/type/range slås op i weapons-kataloget (dmg_s for Small, ellers
    dmg_m). Str-til-skade tages fra posten (str_mult), ellers two_handed-flaget
    (×1,5 for enhåndsvåben), ellers default fra weapon_class. bonus = til-hit.

    weapon_prof (når givet) bruges til at lægge −4 på til-hit for uvante våben;
    item.house_rule eller allowed_weapons fjerner straffen igen.

    Two-weapon fighting: poster med off_hand=True (eller en double=True dobbeltvåbens-
    ende) tæller som off-hånds-angreb → ½ Str + straf efter two_weapon_penalty på
    ALLE wielded angreb. twf (fra twf_context) bestemmer feat-rabatten samt evt.
    ekstra off-hånds-angreb (Improved −5 / Greater −10).
    """
    wielded: list[tuple[InventoryItem, dict]] = []
    for item in inventory:
        if item.state != "wielded" or not item.ref.startswith("weapons/"):
            continue
        w = db.get_weapon(item.ref.split("/", 1)[1])
        if w:
            wielded.append((item, w))

    # Er der overhovedet et off-hånds-angreb i spil? (eksplicit flag eller dobbeltvåben)
    off_items = [(it, w) for it, w in wielded if it.off_hand]
    twf_active = bool(off_items) or any(it.double for it, _ in wielded)
    if off_items:
        off_light = off_items[0][1]["weapon_class"] == "light"
    else:
        off_light = twf_active  # dobbeltvåbens-ende tæller som let
    has_twf = bool(twf and twf.get("has_twf"))
    prim_pen, off_pen = two_weapon_penalty(off_light, has_twf) if twf_active else (0, 0)

    def dmg(w: dict, which: int = 0) -> str:
        base = (w["dmg_s"] if size.lower() == "small" else w["dmg_m"]) or ""
        parts = base.split("/")
        return parts[which] if which < len(parts) else parts[0]

    _FINESSE_WEAPON_IDS = {"rapier", "whip", "spiked_chain"}

    def make(item, w, name, base_damage, mult, pen, is_off) -> Attack:
        not_prof = not (item.house_rule
                        or weapon_proficient(w, weapon_prof, allowed_weapons))
        wclass = w["weapon_class"]
        return Attack(
            name=name,
            kind="ranged" if wclass == "ranged" else "melee",
            base_damage=base_damage,
            str_damage_mult=mult,
            bonus=item.bonus - (4 if not_prof else 0) + pen,
            crit=w["critical"] or "x2",
            type=w["damage_type"] or "",
            range=f"{w['range_ft']} ft." if w["range_ft"] else "",
            not_proficient=not_prof,
            note=_twf_note(pen, is_off),
            finesse=wclass == "light" or w["id"] in _FINESSE_WEAPON_IDS,
        )

    attacks: list[Attack] = []
    off_attacks: list[Attack] = []
    for item, w in wielded:
        wclass = w["weapon_class"]
        name = item.name or w["name"]
        if item.off_hand:
            mult = item.str_mult if item.str_mult is not None else 0.5
            off_attacks.append(make(item, w, name, dmg(w), mult, off_pen, True))
        elif item.double:
            # Dobbeltvåben brugt som to våben: primær ende (fuld Str) + off-ende (½ Str, let)
            pmult = item.str_mult if item.str_mult is not None else 1.0
            attacks.append(make(item, w, name, dmg(w, 0), pmult, prim_pen, False))
            off_attacks.append(make(item, w, f"{name} (off-hånd)", dmg(w, 1), 0.5, off_pen, True))
        else:
            if item.str_mult is not None:
                mult = item.str_mult
            elif item.two_handed and wclass in ("light", "one-handed"):
                mult = 1.5
            else:
                mult = _DEFAULT_STR_MULT.get(wclass, 1.0)
            attacks.append(make(item, w, name, dmg(w, 0), mult, prim_pen, False))

    # Ekstra off-hånds-angreb fra Improved (−5) / Greater (−10) — kloner det første off-angreb.
    if off_attacks and twf:
        template = off_attacks[0]
        extras = []
        if twf.get("has_improved"):
            extras.append((-5, "2. off-hånd"))
        if twf.get("has_greater"):
            extras.append((-10, "3. off-hånd"))
        for extra_pen, lbl in extras:
            off_attacks.append(dataclasses.replace(
                template,
                name=f"{template.name} ({lbl})",
                bonus=template.bonus + extra_pen,
                note=f"{extra_pen:+d} ekstra off-hånd",
            ))

    return attacks + off_attacks


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


# ── Materiale-/kvalitets-modifikatorer (SRD special materials) ──────────────
# Kun PRIS-reglen bor her (i kobber). Hvilke felter en valgt mod sætter på en
# inventory-post (masterwork-flag, +1 til-hit, materiale-mærkat) afgøres i
# catalog.py — så rules.py forbliver rene regel-tal.
# Alkymisk sølv koster efter våbenklasse (SRD: let 20 gp, enhånds 90, tohånds 180).
_SILVER_DELTA_CP = {"light": 2000, "one-handed": 9000, "two-handed": 18000}


def material_modifiers(record: dict, table: str) -> list[dict]:
    """Tilgængelige materiale-/kvalitets-modifikatorer for en katalog-række.

    Returnerer [{key, label, delta_cp}] med prisdeltaer pr. SRD:
      masterwork  våben +300 gp / rustning+skjold +150 gp
      cold_iron   ×2 basispris (delta = basisprisen) — kun metal-nærkampsvåben
      silvered    efter våbenklasse — kun metal-nærkampsvåben der selv gør skade
    Cold iron / sølv tilbydes kun på let/enhånds/tohånds METAL-våben (ikke buer,
    slynger, ubevæbnet eller træ-/læder-våben som markeret med metal=0 i data).
    """
    if table == "weapons":
        mods = [{"key": "masterwork", "label": "Masterwork", "delta_cp": 30000}]
        wclass = record.get("weapon_class")
        if wclass in ("light", "one-handed", "two-handed") and record.get("metal") != 0:
            base = record.get("cost_cp")
            if base:
                mods.append({"key": "cold_iron", "label": "Cold Iron", "delta_cp": int(base)})
            silver = _SILVER_DELTA_CP.get(wclass)
            if silver:
                mods.append({"key": "silvered", "label": "Alch. Silver", "delta_cp": silver})
        return mods
    if table == "armor":
        return [{"key": "masterwork", "label": "Masterwork", "delta_cp": 15000}]
    return []


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
        # Frisk kopi med house_rule-flaget (DM tillader trods druide-metal-forbud),
        # så druid_armor_violations kan dæmpe advarslen uden at mutere db-cachen.
        rec = {**_effective_armor_row(rec, item), "house_rule": bool(item.house_rule)}
        if rec["type"] == "shield":
            shield_row = shield_row or rec
        elif rec["type"] in ("light", "medium", "heavy"):
            armor_row = armor_row or rec
    return armor_row, shield_row


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


def spell_save_dc(spell_level: int, cast_modifier: int, focus_bonus: int = 0) -> int:
    """Save-DC en modstander skal slå for at modstå et spell: 10 + spell-niveau +
    caster-evne-modifier (+ evt. Spell Focus-bonus for spellets skole)."""
    return 10 + spell_level + cast_modifier + focus_bonus


def monk_unarmed_attacks(level: int, size: str, flurry_penalty: int,
                         greater_flurry: bool, flurry_active: bool,
                         base_damage: str) -> list[Attack]:
    """Monkens unarmed strike og eventuelle flurry-ekstra-angreb.

    Primær: ét unarmed strike ved fuld bonus. Når flurry_active: tilføj 1 ekstra
    flurry-række (2 ved Greater Flurry). Straffen vises i ekstra-rækkernes note —
    design Mulighed A: primær-rækken vises ved fuld bonus, info-sektionen forklarer
    at straffen gælder alle angreb. base_damage er forudberegnet (fx fra refdata).
    """
    attacks: list[Attack] = []

    # Primær unarmed strike — altid til stede
    attacks.append(Attack(
        name="Unarmed strike",
        kind="melee",
        base_damage=base_damage,
        str_damage_mult=1.0,
        bonus=0,
        crit="x2",
        type="bludgeoning",
        not_proficient=False,
        note="",
        finesse=True,   # Weapon Finesse kan bruges på unarmed
    ))

    if flurry_active:
        # Flurry-straf-note til ekstra-rækkerne
        if flurry_penalty < 0:
            flurry_note = f"flurry: {flurry_penalty:+d} til alle angreb"
        else:
            flurry_note = "flurry"

        attacks.append(Attack(
            name="Unarmed strike (flurry)",
            kind="melee",
            base_damage=base_damage,
            str_damage_mult=1.0,
            bonus=flurry_penalty,
            crit="x2",
            type="bludgeoning",
            not_proficient=False,
            note=flurry_note,
            finesse=True,
        ))

        if greater_flurry:
            attacks.append(Attack(
                name="Unarmed strike (flurry 2)",
                kind="melee",
                base_damage=base_damage,
                str_damage_mult=1.0,
                bonus=flurry_penalty,
                crit="x2",
                type="bludgeoning",
                not_proficient=False,
                note=flurry_note,
                finesse=True,
            ))

    return attacks
