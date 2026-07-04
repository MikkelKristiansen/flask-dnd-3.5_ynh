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
import re

from models import AbilityScores, Skill, Attack, InventoryItem, Character
from refdata import feat_id, feat_weapon
from attacks import size_mod_attack


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


def armor_class(ability_scores: AbilityScores, size: str, *,
                armor: dict | None = None, shield: dict | None = None,
                enc_max_dex: int | None = None,
                natural: int = 0, deflection: int = 0,
                dodge: int = 0, misc: int = 0,
                armor_effect: int = 0, shield_effect: int = 0,
                lose_dex: bool = False) -> dict:
    """Beregn AC, touch-AC og flat-footed-AC (3.5 SRD).

    armor/shield er rækker fra armor-tabellen (dict) eller None. Dex-bonus til AC
    cappes af det laveste af rustningens/skjoldets max_dex og encumbrance-max_dex
    (en Dex-straf rammer altid fuldt). Touch ignorerer rustning/skjold/naturlig
    armor; flat-footed mister Dex-bonus og dodge (men beholder en Dex-straf).

    armor_effect/shield_effect: armor-/skjold-bonus fra en spell (Mage Armor +4,
    Shield +4). En armor-bonus stacker IKKE med båret rustning (SRD: kun den
    højeste tæller); ligeså skjold. De to SLAGS stacker dog indbyrdes. Som al
    rustnings-/skjold-bonus tæller de i full + flat, men IKKE i touch.

    lose_dex (blinded/cowering/stunned/flat-footed-tilstand): den normale AC og
    touch mister også Dex-bonus og dodge — som flat-footed — men beholder en
    Dex-STRAF. Flat-footed-tallet er uændret.
    """
    worn_armor = armor["armor_bonus"] if armor else 0
    worn_shield = shield["armor_bonus"] if shield else 0
    body_bonus = max(worn_armor, armor_effect)       # magi vs. båret rustning: højeste
    shield_bonus = max(worn_shield, shield_effect)
    armor_bonus = body_bonus + shield_bonus
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

    # Opdeling af hoved-AC (til hover). base vises altid; øvrige dele kun når ≠ 0.
    # Summen af parts er lig full. Rustning og skjold vises hver for sig; en spell
    # der slår det bårne (Mage Armor > ingen/let rustning) mærkes "magisk".
    parts = [{"label": "base", "value": 10}]
    if body_bonus:
        parts.append({"label": "magisk rustning" if armor_effect > worn_armor else "rustning",
                      "value": body_bonus})
    if shield_bonus:
        parts.append({"label": "magisk skjold" if shield_effect > worn_shield else "skjold",
                      "value": shield_bonus})
    for label, value in (("Dex", ac_dex), ("størrelse", size_mod), ("natural", natural),
                         ("deflection", deflection), ("dodge", ac_dodge), ("misc", misc)):
        if value:
            parts.append({"label": label, "value": value})
    return {"ac": full, "touch": touch, "flat_footed": flat, "parts": parts}


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


# Tilstande en genstand kan have. CARRIED_STATES tæller med i båret vægt.
INVENTORY_STATES = {"wielded", "worn", "backpack", "stored", "dropped"}


# ── Materiale-/kvalitets-modifikatorer (SRD special materials) ──────────────


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


def attack_visible(attack: Attack, active_keys: set) -> bool:
    """Skal et angreb vises på arket?

    Våben og spell-angreb uden 'requires' vises altid. Et spell-angreb MED
    'requires' vises kun når den spell der skaber det står på 'I brug'
    (dens id eller navn findes i active_keys).
    """
    if attack.source == "spell" and attack.requires:
        return attack.requires.strip().lower() in active_keys
    return True


