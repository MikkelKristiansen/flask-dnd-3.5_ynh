"""Wild Shape (Su) for druider — D&D 3.5 SRD.

Druiden antager en dyre-/elemental-form: de FYSISKE ability scores (Str/Dex/Con),
størrelse, naturlig rustning, naturlige angreb, speed og Ex-special attacks kommer
fra FORMEN; de MENTALE scores (Int/Wis/Cha), HP, BAB, base-saves, niveau, feats og
skills beholdes fra DRUIDEN. Båret udstyr melder væk → ingen armor/shield-bonus.

Tynd tilstand i char.wild_shape: {animal_used, elemental_used, current_form}.
Det merged statblok beregnes her (gemmes aldrig) — som companion.py/summon.py.
"""
import math

import special_abilities
from character import (AbilityScores, armor_class, size_mod_attack,
                       grapple_total, initiative_total, save_total, race_data)


def _threshold(table: dict, level: int):
    """Værdi for højeste nøgle ≤ level i en {niveau: værdi}-dict (ellers None)."""
    best = None
    for k, v in (table or {}).items():
        ik = int(k)
        if ik <= level and (best is None or ik > best[0]):
            best = (ik, v)
    return best[1] if best else None


def _accumulate(table: dict, level: int) -> list:
    """Foren alle lister for nøgler ≤ level (sizes/types låses gradvist op)."""
    out: list = []
    for k in sorted(int(x) for x in (table or {})):
        if k <= level:
            for v in table[k]:
                if v not in out:
                    out.append(v)
    return out


def _feat_id(entry) -> str:
    return str(entry["id"] if isinstance(entry, dict) else entry)


def wild_shape_info(ws: dict | None, level: int, feats=()) -> dict | None:
    """Progressions-fakta for wild shape ved et givet niveau, eller None.

    uses/dag (animal + elemental), tilladte størrelser/typer (akkumuleret),
    varighed (1 t/niveau) og formens max HD (= druideniveau). Extra Wild Shape-
    feat giver +2 animal-uses pr. instans.
    """
    if not ws or level < int(ws.get("from_level", 99)):
        return None
    animal_uses = (_threshold(ws.get("animal_uses"), level) or 0)
    animal_uses += 2 * sum(1 for f in (feats or []) if _feat_id(f) == "extra_wild_shape")
    elemental_uses = 0
    el_from = ws.get("elemental_from_level")
    if el_from and level >= int(el_from):
        elemental_uses = _threshold(ws.get("elemental_uses"), level) or 0
    return {
        "animal_uses": animal_uses,
        "elemental_uses": elemental_uses,
        "sizes": _accumulate(ws.get("sizes"), level),
        "types": _accumulate(ws.get("types"), level),
        "duration_hours": level,   # 1 time pr. druideniveau
        "max_hd": level,           # formens HD må ikke overstige druideniveau
    }


def eligible_forms(info: dict | None, level: int, db) -> list:
    """Katalog-væsner druiden må antage: type ∈ tilladte, størrelse ∈ tilladte,
    HD ≤ druideniveau. Katalogets type=None betyder almindeligt dyr (= 'animal')."""
    if not info:
        return []
    sizes, types = set(info["sizes"]), set(info["types"])
    forms = []
    for a in db.get_all_animals():
        if int(a.get("base_hd", 0)) > level:
            continue
        if a.get("size") not in sizes:
            continue
        if (a.get("type") or "animal") not in types:
            continue
        forms.append({"id": a["id"], "name": a["name"],
                      "size": a["size"], "hd": a["base_hd"]})
    return sorted(forms, key=lambda f: f["name"])


def _apply_active_abilities(scores, gained: list, active_slugs, db):
    """Anvend aktive form-evne-buffs (fx Rage) på formens scores.

    Hver gained-evne med et buff_id markeres 'activatable'; er dens slug i
    active_slugs, slås buff_id'et op i effects-tabellen og dens ability-modifiers
    (str..cha) lægges på scoren mens en ac-modifier samles som ac_delta (føres
    siden ind i AC's misc). Returnerer (scores, ac_delta) — scores er en ny
    AbilityScores hvis noget ændrede sig, ellers den oprindelige.
    """
    keys = ("str", "dex", "con", "int", "wis", "cha")
    deltas = {k: 0 for k in keys}
    ac_delta = 0
    active = set(active_slugs or [])
    for ab in gained:
        buff_id = ab.get("buff_id")
        ab["activatable"] = bool(buff_id)
        ab["active"] = bool(buff_id) and ab["slug"] in active
        if not ab["active"]:
            continue
        for m in (db.get_effect(buff_id) or {}).get("modifiers", []):
            target, value = m.get("target"), int(m.get("value", 0))
            if target in deltas:
                deltas[target] += value
            elif target == "ac":
                ac_delta += value
    if not any(deltas.values()):
        return scores, ac_delta
    return AbilityScores(**{k: getattr(scores, k) + deltas[k] for k in keys}), ac_delta


def build_wild_shape_form(char, ws: dict | None, db) -> dict | None:
    """Det merged statblok for druidens nuværende form, eller None hvis ingen.

    Fysiske stats + størrelse + naturlig rustning + naturlige angreb + speed fra
    formen; mentale stats + HP + BAB + base-saves + niveau fra druiden. Udstyr
    melder væk (ingen armor/shield i AC).
    """
    state = char.wild_shape or {}
    form_id = state.get("current_form")
    if not form_id:
        return None
    animal = db.get_animal(form_id)
    if not animal:
        return None

    d = char.ability_scores
    scores = AbilityScores(
        str=animal["str"], dex=animal["dex"], con=animal["con"],
        int=d.int, wis=d.wis, cha=d.cha)
    size = animal["size"]
    bab = int(char.combat.get("bab", 0))
    natural = int(animal.get("natural_armor", 0) or 0)

    # Natural abilities: hvad kobles på (animal: kun Ex special attacks; elemental:
    # alt) + forklaring. Aktiverbare stat-evner (fx Rage = +4 Str/+4 Con/−2 AC)
    # anvendes på formens scores/AC, så tallene slår igennem mens de er tændt.
    form_type = animal.get("type") or "animal"
    natural_abilities = special_abilities.resolve_form_abilities(
        animal.get("special_attacks"), animal.get("special_qualities"), form_type, db)
    scores, ac_delta = _apply_active_abilities(
        scores, natural_abilities["gained"], state.get("active_abilities"), db)
    str_mod = scores.modifier("str")

    # AC: udstyr meldt væk → ingen armor/shield. Druidens typede ikke-gear-bonusser
    # (deflection/dodge/misc) beholdes; en aktiv stat-evne (Rage −2) føjes til misc.
    ac = armor_class(scores, size, natural=natural,
                     deflection=int(char.combat.get("deflection", 0)),
                     dodge=int(char.combat.get("dodge", 0)),
                     misc=int(char.combat.get("misc_ac", 0)) + ac_delta)

    # Saves: druidens base + de NYE ability-mods (Fort=form-Con, Ref=form-Dex),
    # Will bruger druidens egen Wis (mentale stats ændres ikke). Racial bonus med.
    racial = int(race_data(char.race).get("save_bonus", 0))
    saves = {
        "fort": save_total(int(char.saves.get("fortitude", 0)), scores.con, racial),
        "ref": save_total(int(char.saves.get("reflex", 0)), scores.dex, racial),
        "will": save_total(int(char.saves.get("will", 0)), scores.wis, racial),
    }

    # Naturlige angreb: druidens BAB + formens Str + størrelse. Ét enkelt primært
    # angreb får ×1,5 Str; sekundære får −5 og ½ Str. Formens feats gælder IKKE
    # (RAW: man får ikke formens feats, kun dens Ex-special attacks).
    attack_list = animal.get("attacks") or []
    lone_primary = (len(attack_list) == 1
                    and attack_list[0].get("group") == "primary"
                    and attack_list[0].get("count", 1) == 1)
    attacks = []
    for atk in attack_list:
        secondary = atk.get("group") == "secondary"
        to_hit = bab + size_mod_attack(size) + str_mod + (-5 if secondary else 0)
        mult = 1.5 if lone_primary else (0.5 if secondary else 1.0)
        bonus = math.floor(str_mod * mult)
        damage = f"{atk['damage']}{bonus:+d}" if bonus else atk["damage"]
        attacks.append({
            "name": atk["name"], "count": atk.get("count", 1),
            "to_hit": to_hit, "damage": damage,
            "group": atk.get("group", "primary"),
        })

    return {
        "animal_id": animal["id"],
        "animal_name": animal["name"],
        "size": size,
        "hd": animal["base_hd"],
        "abilities": {a: getattr(scores, a) for a in
                      ("str", "dex", "con", "int", "wis", "cha")},
        "ac": ac,
        "natural_armor": natural,
        "bab": bab,
        "grapple": grapple_total(bab, scores.str, size),
        "initiative": initiative_total(scores, char.feats,
                                       int(char.combat.get("initiative_misc", 0))),
        "saves": saves,
        "speed": animal["speed"],
        "attacks": attacks,
        "natural_abilities": natural_abilities,   # {gained: [...], reference: [...]}
    }
