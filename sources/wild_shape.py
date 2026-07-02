"""Wild Shape (Su) for druider — D&D 3.5 SRD.

Druiden antager en dyre-/elemental-form: de FYSISKE ability scores (Str/Dex/Con),
størrelse, naturlig rustning, naturlige angreb, speed og Ex-special attacks kommer
fra FORMEN; de MENTALE scores (Int/Wis/Cha), HP, BAB, base-saves, niveau, feats og
skills beholdes fra DRUIDEN. Båret udstyr melder væk → ingen armor/shield-bonus.

Tynd tilstand i char.wild_shape: {animal_used, elemental_used, current_form}.
Det merged statblok beregnes her (gemmes aldrig) — som companion.py/summon.py.
"""
import math
import re

import special_abilities
from character import (AbilityScores, armor_class, size_mod_attack,
                       grapple_total, initiative_total, save_total, race_data)

_DICE_RE = re.compile(r"\d*d\d+")   # første terning-udtryk i en evne-label (fx '2d4')


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


def _damage_str(dice: str, mod: int) -> str:
    return f"{dice}{mod:+d}" if mod else dice


def _rider_roll(ab: dict, dice: str, str_mod: int, mult: float,
                bab: int | None = None, smod: int = 0, count: int | None = None) -> dict:
    """Byg én rytter-rulle med skade + hover-opdelinger, som de øvrige angreb.

    mult er Str-multiplikatoren (1,0 for rake/constrict, 1,5 for rend/trample).
    bab != None ⇒ rytteren rulles med til-hit (kun rake) og får hit_parts. Skade-
    delene (dmg_parts) har 'die' = grundterningen + evt. STR-linje; total-strengen
    bygges som resten (terning{+mod}).
    """
    mod = math.floor(str_mod * mult)
    dmg_parts = [{"label": "terning", "die": dice}]
    if mod:
        dmg_parts.append({"label": "STR" if mult == 1.0 else f"STR ×{mult:g}", "value": mod})
    roll = {"name": ab["name"], "damage": _damage_str(dice, mod), "dmg_parts": dmg_parts}
    if bab is not None:
        hit_parts = [{"label": "BAB", "value": bab}, {"label": "STR", "value": str_mod}]
        if smod:
            hit_parts.append({"label": "størrelse", "value": smod})
        roll["to_hit"] = bab + smod + str_mod
        roll["hit_parts"] = hit_parts
    if count is not None:
        roll["count"] = count
    return roll


def _attach_riders(gained: list, bab: int, str_mod: int, size: str) -> None:
    """Beregn engangs-angrebsryttere (rake/rend/constrict/trample) for formen.

    Rul-rækker bruger formens BAB + Str-mod + størrelse — som de øvrige naturlige
    angreb (RAW). Grundterningen hentes fra evnens label ('rake 2d4+4' → 2d4), så
    formens egen Str-bonus erstattes af druidens. Note-ryttere (trip/pounce/improved
    grab/poison) får kun en trigger-tekst. Hver gained-rytter får ab['rider'] =
    {trigger, rolls:[{name, to_hit?, damage, count?, hit_parts?, dmg_parts}]}.
    """
    smod = size_mod_attack(size)
    for ab in gained:
        rt = ab.get("rider_type")
        if not rt:
            continue
        m = _DICE_RE.search(ab.get("label") or "")
        dice = m.group(0) if m else None
        rolls = []
        if dice:
            if rt == "extra_attacks":            # rake: ekstra naturlige angreb (m. til-hit)
                rolls = [_rider_roll(ab, dice, str_mod, 1.0, bab=bab, smod=smod,
                                     count=int(ab.get("rider_count") or 1))]
            elif rt == "on_grapple":             # constrict: auto skade ved grapple (×1 Str)
                rolls = [_rider_roll(ab, dice, str_mod, 1.0)]
            elif rt in ("two_hit", "trample"):   # rend/trample: skade + 1,5×Str
                rolls = [_rider_roll(ab, dice, str_mod, 1.5)]
        ab["rider"] = {"trigger": special_abilities.RIDER_TRIGGERS.get(rt, ""), "rolls": rolls}


def _form_skills(skills, scores, size: str, db) -> list:
    """Fysiske (Str/Dex/Con) skills genberegnet med formens scores.

    RAW polymorph: druiden beholder sine egne ranks + misc, men de FYSISKE scores
    er formens — så kun Str/Dex/Con-baserede skills ændrer sig (mentale er uændrede,
    vises ikke her). Hide får desuden formens størrelses-modifier (×4 pr. step:
    Small +4 … Large −4). Formens egne racial skill-bonusser arves IKKE (RAW).
    Returnerer [{name, total}] sorteret — kun de skills druiden har i sin liste.
    """
    hide_mod = size_mod_attack(size) * 4
    out = []
    for s in skills:
        rec = db.get_skill(s.id)
        if not rec or rec.get("ability") not in ("str", "dex", "con"):
            continue
        total = int(s.ranks) + scores.modifier(rec["ability"]) + int(s.misc or 0)
        if s.id == "hide":
            total += hide_mod
        out.append({"name": rec.get("name", s.id), "total": total})
    return sorted(out, key=lambda x: x["name"])


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
    bab = db.base_attack_bonus(char.cls, char.level)
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
    size_m = size_mod_attack(size)
    attacks = []
    for atk in attack_list:
        secondary = atk.get("group") == "secondary"
        to_hit = bab + size_m + str_mod + (-5 if secondary else 0)
        # Til-hit-opdeling til hover (formens feats gælder ikke → ingen Weapon Focus).
        hit_parts = [{"label": "BAB", "value": bab},
                     {"label": "STR", "value": str_mod}]
        if size_m:
            hit_parts.append({"label": "størrelse", "value": size_m})
        if secondary:
            hit_parts.append({"label": "sekundær", "value": -5})
        mult = 1.5 if lone_primary else (0.5 if secondary else 1.0)
        str_dmg = math.floor(str_mod * mult)
        damage = f"{atk['damage']}{str_dmg:+d}" if str_dmg else atk["damage"]
        # Skade-opdeling til hover (terning + Str×mult).
        dmg_parts = [{"label": "terning", "die": atk["damage"]}]
        if str_dmg:
            dmg_parts.append({"label": "STR" if mult == 1.0 else f"STR ×{mult:g}",
                              "value": str_dmg})
        attacks.append({
            "name": atk["name"], "count": atk.get("count", 1),
            "to_hit": to_hit, "damage": damage,
            "group": atk.get("group", "primary"),
            "hit_parts": hit_parts, "dmg_parts": dmg_parts,
        })

    # Angrebsryttere (rake/rend/constrict/trample → rul; trip/pounce/… → note).
    # Bruger formens endelige str_mod, så en aktiv Rage også løfter rytter-skaden.
    _attach_riders(natural_abilities["gained"], bab, str_mod, size)

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
        "skills": _form_skills(char.skills, scores, size, db),  # fysiske skills i form
    }
