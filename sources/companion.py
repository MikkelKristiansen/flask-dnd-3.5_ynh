"""Beregning af en dyreledsager (animal companion) — SRD v3.5.

Ansvar: tag et RÅ basis-dyr fra animals-tabellen + den effektive druide-/ranger-
niveau og udregn det fulde, avancerede statblok (HP, AC, BAB, grapple, saves,
initiativ, til-hit, skade, skills, special-evner). Intet gemmes — alt beregnes
ved render, ligesom for hovedkarakteren.

Hvorfor et eget modul: en companion er et helt sekundært væsen med sin egen
avancementtabel. At lægge den i character.py ville blande to ansvar; her får
den ét klart hjem. Genbruger de rene byggeklodser fra character.py
(AbilityScores, størrelses-modifiers, armor_class).

Companion-avancement (SRD "The Animal Companion"): efterhånden som druiden stiger
i niveau får dyret bonus-HD, bedre naturlig rustning, højere Str/Dex, flere
tricks og særlige evner (Link → Evasion → Devotion → Multiattack → …).
"""
import math

from character import AbilityScores, armor_class, size_mod_attack, size_mod_grapple

# Companion-avancement pr. EFFEKTIVT druideniveau. Universel regel-tabel (ikke
# katalog-data), derfor en konstant her ligesom SIZE_MOD_* i character.py.
# (min_niveau, bonus_hd, naturlig_rustning, str_dex_bonus, bonus_tricks, special-evner)
_ADVANCEMENT = [
    (1,   0,  0, 0, 1, ["Link", "Share Spells"]),
    (3,   2,  2, 1, 2, ["Evasion"]),
    (6,   4,  4, 2, 3, ["Devotion"]),
    (9,   6,  6, 3, 4, ["Multiattack"]),
    (12,  8,  8, 4, 5, []),
    (15, 10, 10, 5, 6, ["Improved Evasion"]),
    (18, 12, 12, 6, 7, []),
]


def companion_effective_level(cls: str, level: int) -> int:
    """Effektivt druideniveau for companion-avancement.

    Druide: = druideniveau. Ranger: = ½ rangerniveau, og companion fås først
    ved ranger-niveau 4 (→ effektivt 2). Andre klasser: 0 (ingen companion).
    """
    cls = (cls or "").lower()
    if cls == "druid":
        return max(0, level)
    if cls == "ranger":
        return level // 2 if level >= 4 else 0
    return 0


def _tier(eff_level: int) -> tuple:
    """Find avancementsrækken for et givet effektivt niveau."""
    chosen = _ADVANCEMENT[0]
    for row in _ADVANCEMENT:
        if eff_level >= row[0]:
            chosen = row
    return chosen


def _good_save(hd: int) -> int:
    return hd // 2 + 2


def _poor_save(hd: int) -> int:
    return hd // 3


def _has_feat(feats: list, needle: str) -> bool:
    needle = needle.lower()
    return any(needle in str(f).lower() for f in feats)


def _str_damage(str_mod: int, mult: float) -> int:
    """Str-bidrag til skade. En Str-BONUS ganges med mult (×1,5 enligt primært,
    ×0,5 sekundært); en Str-STRAF tæller altid fuldt (SRD)."""
    if str_mod >= 0:
        return math.floor(str_mod * mult)
    return str_mod


def advance_companion(animal: dict, eff_level: int, db) -> dict:
    """Udregn det fulde companion-statblok fra et basis-dyr + effektivt niveau.

    Alle tal afledes (SRD): BAB = ¾ × HD; saves = god Fort/Ref + dårlig Will som
    et væsen hvis niveau = HD; HP = gennemsnit pr. HD + Con; AC = 10 + størrelse
    + Dex + naturlig rustning. Angreb bruger Dex ved Weapon Finesse, ellers Str;
    sekundære angreb får −5 og ½ Str; et ENESTE primært angreb får ×1,5 Str.
    """
    _, bonus_hd, na_bonus, ability_bonus, bonus_tricks, specials = _tier(eff_level)

    total_hd = animal["base_hd"] + bonus_hd
    scores = AbilityScores(
        str=animal["str"] + ability_bonus,
        dex=animal["dex"] + ability_bonus,
        con=animal["con"], int=animal["int"], wis=animal["wis"], cha=animal["cha"],
    )
    con_mod = scores.modifier("con")
    str_mod = scores.modifier("str")
    dex_mod = scores.modifier("dex")
    size = animal["size"]
    feats = list(animal["feats"])

    bab = total_hd * 3 // 4
    natural = animal["natural_armor"] + na_bonus
    hp_max = max(1, math.floor(4.5 * total_hd) + con_mod * total_hd)

    ac = armor_class(scores, size, natural=natural)
    grapple = bab + str_mod + size_mod_grapple(size)
    initiative = dex_mod + (4 if _has_feat(feats, "improved initiative") else 0)
    saves = {
        "fort": _good_save(total_hd) + con_mod,
        "ref": _good_save(total_hd) + dex_mod,
        "will": _poor_save(total_hd) + scores.modifier("wis"),
    }

    # Angreb: til-hit + skade pr. naturligt våben.
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
        to_hit = bab + size_mod_attack(size) + hit_mod + focus + (-5 if secondary else 0)
        mult = 1.5 if lone_primary else (0.5 if secondary else 1.0)
        bonus = _str_damage(str_mod, mult)
        damage = f"{atk['damage']}{bonus:+d}" if bonus else atk["damage"]
        count = atk.get("count", 1)
        attacks.append({
            "name": atk["name"], "count": count, "to_hit": to_hit,
            "damage": damage, "group": atk.get("group", "primary"),
        })

    # Skills: total = misc + ability-mod (fra skill-definitionen), så de følger
    # med når avancement hæver Str/Dex. misc har ranks + racial bagt ind.
    skills = []
    for sk in animal["skills"]:
        sd = db.get_skill(sk["id"])
        ability = sd["ability"] if sd else None
        mod = scores.modifier(ability) if ability and ability != "none" else 0
        skills.append({
            "name": sd["name"] if sd else sk["id"],
            "total": sk["misc"] + mod,
            "note": sk.get("note", ""),
        })

    # Multiattack ved niveau 9+: bonus-feat hvis ≥3 naturlige angreb, ellers et
    # ekstra angreb med primærvåbnet ved −5 (kun relevant ved høje niveauer).
    if "Multiattack" in specials and not _has_feat(feats, "multiattack"):
        feats = feats + ["Multiattack"]

    return {
        "animal_id": animal["id"],
        "animal_name": animal["name"],
        "size": size,
        "effective_level": eff_level,
        "total_hd": total_hd,
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
        "specials": specials,
        "bonus_tricks": bonus_tricks,
    }


def build_companion(char, db) -> dict | None:
    """Byg det beregnede companion-statblok for en karakter, eller None.

    Læser den TYNDE reference fra char.companion (name, animal, hp_current,
    tricks), slår basis-dyret op og avancerer det til karakterens effektive
    niveau. Returnerer None hvis karakteren ingen (gyldig) companion har.
    """
    comp = char.companion or {}
    animal_id = comp.get("animal")
    if not animal_id:
        return None
    animal = db.get_animal(animal_id)
    if not animal:
        return None

    eff_level = companion_effective_level(char.cls, char.level)
    stat = advance_companion(animal, max(1, eff_level), db)
    stat["name"] = comp.get("name") or animal["name"]
    stat["tricks"] = list(comp.get("tricks") or [])
    hp_max = stat["hp_max"]
    hp_cur = comp.get("hp_current")
    stat["hp_current"] = hp_max if hp_cur is None else min(hp_cur, hp_max)
    return stat
