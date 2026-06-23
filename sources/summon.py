"""Beregning af et summonet væsen (Summon Nature's Ally) — SRD v3.5.

Ansvar: tag et RÅT basis-væsen fra animals-kataloget + summon-parametre (antal,
Augment Summoning) og udregn det fulde, FASTE statblok (HP, AC, BAB, grapple,
saves, initiativ, til-hit, skade, skills). Intet gemmes — alt beregnes ved render,
ligesom for hovedkarakteren og companion.

Hvorfor et eget modul (ikke companion.py): et summonet væsen er et selvstændigt
sekundært væsen, men reglerne er anderledes nok til at deling ville sløre:
  • Det avanceres IKKE af casterniveau — en summonet wolf er bare en wolf på
    sine basis-HD (companion får bonus-HD, naturlig rustning, tricks, Link osv.).
  • BAB og saves afhænger af VÆSEN-TYPEN (companions er altid dyr: ¾ BAB, poor
    Will). Magical beasts har fuld BAB, fey ½, og dire-dyr/elementaler har egne
    save-profiler — derfor læses type/good_saves fra kataloget.
  • HP bruger den faktiske hit-die-type (d10/d6), ikke companions hardkodede d8.

Genbruger de rene byggeklodser fra character-facaden (AbilityScores, armor_class,
size-mods, effective_ability_scores, save-/skill-effekt-bonus) og effekt-motoren
(collect_active_effects/collect_riders) — så aktive buffs/tilstande virker præcis
som på companion. Augment Summoning modelleres som en almindelig enhancement-buff.
"""
import math

from character import (AbilityScores, armor_class, size_mod_attack,
                       size_mod_grapple, effective_ability_scores,
                       resolve_modifiers, resolve_ac_bonuses,
                       save_effect_bonus, skill_effect_bonus)
from effects import collect_active_effects, collect_riders


# Augment Summoning (feat): +4 enhancement til Str og Con på alt man conjurerer.
# Modelleres som almindelige modifiers, så de kaskaderer (Str→skade/grapple,
# Con→HP) via samme motor som Bull's Strength.
_AUGMENT_MODIFIERS = [
    {"target": "str", "type": "enhancement", "value": 4},
    {"target": "con", "type": "enhancement", "value": 4},
]


def _bab(creature_type: str | None, hd: int) -> int:
    """Base attack bonus efter væsen-type (SRD).

    magical_beast/outsider: 1·HD (god) · fey: ½·HD (dårlig) ·
    animal/elemental/øvrige: ¾·HD.
    """
    if creature_type in ("magical_beast", "outsider"):
        return hd
    if creature_type == "fey":
        return hd // 2
    return hd * 3 // 4


def _good_saves(animal: dict) -> set:
    """Hvilke saves er "gode" for væsenet.

    Eksplicit good_saves i kataloget vinder (elementaler pr. element, dire-dyr har
    god Will). Ellers udledt af typen: fey har god Ref+Will, alle andre (animal/
    magical_beast/elemental-default) har god Fort+Ref.
    """
    explicit = animal.get("good_saves")
    if explicit:
        return set(explicit)
    if animal.get("type") == "fey":
        return {"ref", "will"}
    return {"fort", "ref"}


def _save(is_good: bool, hd: int) -> int:
    """Basis-save: god = ½·HD + 2, dårlig = ⅓·HD (som et væsen hvis niveau = HD)."""
    return hd // 2 + 2 if is_good else hd // 3


def _has_feat(feats: list, needle: str) -> bool:
    needle = needle.lower()
    return any(needle in str(f).lower() for f in feats)


def _toughness_hp(feats: list) -> int:
    """Toughness giver +3 HP pr. gang feat'en er taget (SRD)."""
    return 3 * sum(1 for f in feats if str(f).strip().lower() == "toughness")


# Save-boostende feats (+2 til den pågældende save) — mange dyr/elementaler har dem.
_SAVE_FEAT = {"fort": "great fortitude", "ref": "lightning reflexes", "will": "iron will"}


def _feat_save_bonus(feats: list, save: str) -> int:
    """+2 hvis væsenet har den save-boostende feat (Great Fortitude/Lightning
    Reflexes/Iron Will). Uden dette afviger fx en hajs Fort fra SRD-printet."""
    return 2 if _has_feat(feats, _SAVE_FEAT[save]) else 0


def _str_damage(str_mod: int, mult: float) -> int:
    """Str-bidrag til skade: en BONUS ganges med mult (×1,5 enligt primært,
    ×0,5 sekundært); en STRAF tæller altid fuldt (SRD)."""
    if str_mod >= 0:
        return math.floor(str_mod * mult)
    return str_mod


def build_summon_stat(animal: dict, db, active_modifiers: list | None = None,
                      riders: dict | None = None) -> dict:
    """Udregn det fulde, faste statblok for ÉT summonet væsen.

    Alle tal afledes (SRD): BAB efter type; HP = gennemsnit pr. hit-die + Con
    (+ Toughness); saves = gode/dårlige efter væsenets save-profil; AC = 10 +
    størrelse + Dex + naturlig rustning. Angreb bruger Dex ved Weapon Finesse,
    ellers Str; et ENESTE primært angreb får ×1,5 Str, sekundære −5 og ½ Str.

    active_modifiers/riders: aktive effekter (inkl. Augment Summoning) via samme
    motor som hovedkarakter/companion. Uden effekter er alt det rå basis-væsen.
    """
    active_modifiers = active_modifiers or []
    riders = riders or {"lose_dex": False, "half_speed": False, "flags": []}
    net = resolve_modifiers(active_modifiers)

    ctype = animal.get("type")
    hd = animal["base_hd"]
    hit_die = animal.get("hit_die") or 8
    size = animal["size"]
    feats = list(animal["feats"])

    base_scores = AbilityScores(
        str=animal["str"], dex=animal["dex"], con=animal["con"],
        int=animal["int"], wis=animal["wis"], cha=animal["cha"],
    )
    # Effekt-ability-ændringer (Augment Summoning, Bull's Strength, skade) kaskaderer.
    scores = effective_ability_scores(base_scores, active_modifiers)
    str_mod = scores.modifier("str")
    dex_mod = scores.modifier("dex")
    con_mod = scores.modifier("con")
    wis_mod = scores.modifier("wis")

    bab = _bab(ctype, hd)
    natural = animal["natural_armor"]
    # HP bruger den effektive Con (Augment/Bear's Endurance slår igennem på HP).
    hp_max = max(1, math.floor((hit_die + 1) / 2 * hd) + con_mod * hd) + _toughness_hp(feats)

    ac_bonuses = resolve_ac_bonuses(
        {"natural": natural, "deflection": 0, "dodge": 0, "misc": 0},
        [m for m in active_modifiers if m.get("target") == "ac"])
    ac = armor_class(scores, size, lose_dex=riders.get("lose_dex", False), **ac_bonuses)
    grapple = bab + str_mod + size_mod_grapple(size)
    initiative = (dex_mod + (4 if _has_feat(feats, "improved initiative") else 0)
                  + net.get("init", 0))

    good = _good_saves(animal)
    saves = {
        "fort": _save("fort" in good, hd) + con_mod + _feat_save_bonus(feats, "fort") + save_effect_bonus(active_modifiers, "fortitude"),
        "ref": _save("ref" in good, hd) + dex_mod + _feat_save_bonus(feats, "ref") + save_effect_bonus(active_modifiers, "reflex"),
        "will": _save("will" in good, hd) + wis_mod + _feat_save_bonus(feats, "will") + save_effect_bonus(active_modifiers, "will"),
    }

    # Angreb: til-hit + skade pr. naturligt våben (+ direkte attack-/skade-bonus).
    attack_extra = net.get("attack", 0)
    damage_extra = net.get("damage", 0)
    attack_list = animal["attacks"]
    finesse = _has_feat(feats, "weapon finesse")
    lone_primary = (len(attack_list) == 1
                    and attack_list[0].get("group") == "primary"
                    and attack_list[0].get("count", 1) == 1)
    attacks = []
    for atk in attack_list:
        secondary = atk.get("group") == "secondary"
        hit_mod = dex_mod if finesse else str_mod
        focus = 1 if _has_feat(feats, f"weapon focus ({atk['name'].lower()})") else 0
        to_hit = (bab + size_mod_attack(size) + hit_mod + focus
                  + (-5 if secondary else 0) + attack_extra)
        mult = 1.5 if lone_primary else (0.5 if secondary else 1.0)
        bonus = _str_damage(str_mod, mult) + damage_extra
        damage = f"{atk['damage']}{bonus:+d}" if bonus else atk["damage"]
        attacks.append({
            "name": atk["name"], "count": atk.get("count", 1), "to_hit": to_hit,
            "damage": damage, "group": atk.get("group", "primary"),
        })

    # Skills: total = misc + ability-mod (fra skill-definitionen) + effekt-bonus.
    skills = []
    for sk in animal["skills"]:
        sd = db.get_skill(sk["id"])
        ability = sd["ability"] if sd else None
        mod = scores.modifier(ability) if ability and ability != "none" else 0
        skills.append({
            "name": sd["name"] if sd else sk["id"],
            "total": sk["misc"] + mod + skill_effect_bonus(active_modifiers, sk["id"]),
            "note": sk.get("note", ""),
        })

    return {
        "creature_id": animal["id"],
        "creature_name": animal["name"],
        "type": ctype or "animal",
        "size": size,
        "total_hd": hd,
        "hit_die": hit_die,
        "abilities": {a: getattr(scores, a) for a in
                      ("str", "dex", "con", "int", "wis", "cha")},
        "hp_max": hp_max,
        "ac": ac,
        "natural_armor": natural,
        "bab": bab,
        "grapple": grapple,
        "initiative": initiative,
        "saves": saves,
        "speed": animal["speed"],
        "attacks": attacks,
        "special_attacks": animal.get("special_attacks"),
        "special_qualities": animal.get("special_qualities"),
        "skills": skills,
        "feats": feats,
        "effect_flags": riders.get("flags", []),
    }


def build_summon(ref: dict, db) -> dict | None:
    """Byg det beregnede statblok for ÉN summon-instans, eller None.

    Læser den TYNDE reference (creature, spell_level, spell_index, count,
    hp_current, augment, buffs, conditions), slår basis-væsenet op i kataloget og
    udregner det. ``augment`` (snapshot af om casteren havde Augment Summoning ved
    kast) lægger +4 Str/+4 Con på. ``count`` ens væsner deler statblok; hp_current
    er en liste med ét tal pr. væsen (klampet til hp_max).
    """
    creature_id = ref.get("creature")
    if not creature_id:
        return None
    animal = db.get_animal(creature_id)
    if not animal:
        return None

    # Aktive effekter (samme motor som hovedkarakter/companion) + Augment Summoning.
    active_modifiers, sources = collect_active_effects(
        ref.get("buffs"), ref.get("conditions"), db)
    if ref.get("augment"):
        active_modifiers = list(_AUGMENT_MODIFIERS) + active_modifiers
    riders = collect_riders(sources)
    stat = build_summon_stat(animal, db, active_modifiers, riders)

    count = max(1, int(ref.get("count") or 1))
    hp_max = stat["hp_max"]
    raw = list(ref.get("hp_current") or [])
    # Én HP-værdi pr. væsen; manglende/for høje klampes til hp_max.
    stat["count"] = count
    stat["hp_current"] = [hp_max if (i >= len(raw) or raw[i] is None)
                          else min(int(raw[i]), hp_max) for i in range(count)]
    stat["augment"] = bool(ref.get("augment"))
    stat["spell_level"] = ref.get("spell_level")
    stat["spell_index"] = ref.get("spell_index")
    stat["name"] = ref.get("name") or animal["name"]
    # Effekter (tracking): tilstande slås op i kataloget; buffs er selvbeskrivende.
    cond_ids = list(ref.get("conditions") or [])
    stat["conditions"] = [(cid, db.get_condition(cid)) for cid in cond_ids]
    stat["buffs"] = list(ref.get("buffs") or [])
    return stat


def build_summons(refs: list | None, db) -> list:
    """Byg statblokke for alle aktive summons på en karakter (tom liste hvis ingen)."""
    return [s for s in (build_summon(r, db) for r in (refs or [])) if s]
