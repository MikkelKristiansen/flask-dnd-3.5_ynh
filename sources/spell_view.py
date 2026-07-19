"""View-model-bygning for spell-siden af karakterarket.

build_spell_view() samler alt det character_view.py skal bruge om en karakters
spells: forberedte/kendte slots, ⚡ Kast-knap-data (angreb/save/heal), aktive
kategori-E-effekter (med runde-tæller), aktive kategori-F-utility, summon-/cure-
kataloger, domæne-spells og gnome-SLA'er. Ren udledning ved render — intet gemmes.

Udtrukket af character_view.py (som var vokset til 958 linjer med mange blandede
ansvar), samme mønster som companion.py/wild_shape.py/summon.py/combat_options.py
allerede bruger for deres respektive områder. Kun afhængig af (char, db) — ingen
effektive ability scores/modifiers nødvendige her (det er combat/AC's domæne).
"""
import re

import character as char_module
import creature_template
import refdata


def build_spell_view(char, db) -> dict:
    """Byg alle spell-relaterede template-kwargs for karakterarket."""
    ab = char.ability_scores

    # Casting-ability er data-drevet (cha for bard/sorcerer, int for wizard,
    # wis for cleric/druid/ranger/paladin). Default wis for klasser uden feltet.
    cast_type    = refdata.class_cast_type(char.cls)
    cast_ability = refdata.class_data(char.cls).get("cast_ability", "wis")
    cast_mod     = ab.modifier(cast_ability)

    class_level_data = db.get_class_level(char.cls.lower(), char.level)
    slots: dict[int, int] = {}
    if class_level_data:
        slots = char_module.spell_slots_total(class_level_data, getattr(ab, cast_ability))

    # Spell-tilstande: selv-varigheds-spells (self_duration) har tre tilstande
    # (Ledig/I brug/Brugt); øvrige har to (Ledig/Brugt). 'used' = slot brugt
    # (både I brug og Brugt tæller), bruges kun til slot-optælling i templaten.
    spell_data: dict[int, list] = {}
    for lvl, spell_ids in char.spells_prepared.items():
        used_indices = set(char.spells_used.get(lvl, []))
        active_indices = set(char.spells_active.get(lvl, []))
        rows = []
        for i, sid in enumerate(spell_ids):
            spell = db.get_spell(sid)
            if i in active_indices:
                state = "active"
            elif i in used_indices:
                state = "used"
            else:
                state = "free"
            self_dur = bool(spell and spell.get("self_duration"))
            is_summon = refdata.summon_family(sid) is not None
            # Tre-tilstand ("I brug"-bar): self_duration ELLER en kategori-F utility
            # med en varighed at vise (Fly, Tongues …) ELLER et vedvarende kategori-
            # B/E-spell (Flaming Sphere, Call Lightning) der gør skade hver runde
            # mens det er aktivt. Additivt — self_duration er sat inkonsekvent på
            # F-spells, så uden dette kunne de aldrig aktiveres/vises.
            three_state = self_dur
            if not three_state and not is_summon and char_module.spell_is_utility(sid, db):
                dur = char_module.spell_duration(spell or {}, char.level)
                if dur and not dur["instantaneous"]:
                    three_state = True
            if (not three_state and not is_summon
                    and char_module.spell_is_sustained_combat(sid, char.level, db)):
                three_state = True
            # ⚡ Kast-knap: øjeblikkelige angrebs-/heal-spells (Magic Missile, Cure
            # Light Wounds) kastes direkte — rul + brug slot. Self_duration-,
            # summon- og vedvarende (three_state) spells bruger i stedet toggle +
            # den vedvarende visning (Spell-angreb/-effekter/Aktive effekter); de må
            # ikke ALSO have en engangs-knap (to modstridende måder at bruge samme slot).
            cast = None
            if not (self_dur or is_summon or three_state):
                cast = (char_module.spell_cast_info(sid, char.level, db)
                        or char_module.spell_heal_cast_info(sid, char.level, db))
            rows.append({
                "id": sid, "index": i, "spell": spell,
                "used": state != "free", "state": state,
                "self_duration": self_dur,
                "three_state": three_state,
                "is_summon": is_summon,
                "cast": cast,
            })
        spell_data[lvl] = rows

    # Spontant kast: kun klasser med spontaneous_summon-flaget (druide) kan ofre
    # et forberedt spell til SNA af samme niveau.
    can_sacrifice = bool(refdata.class_data(char.cls).get("spontaneous_summon"))

    # Summon-picker-katalog: {niveau: [{id, template, name}]}. Væsnerne kommer fra
    # de summon-familier casteren faktisk har på niveauet: SNA og/eller SM (udledt
    # af de forberedte spells' familie), plus SNA hvis klassen kan ofre (druide).
    # Summon Monster-væsner bærer en celestial/fiendish-skabelon → vist i navnet.
    summon_catalog: dict[int, list] = {}
    for lvl, spell_ids in char.spells_prepared.items():
        families = {refdata.summon_family(sid) for sid in spell_ids}
        families.discard(None)
        if can_sacrifice:
            families.add("sna")          # offer kan lave SNA på ethvert niveau
        # Sporene (niveau-N-listen + evt. lavere lister for 1d3 / 1d4+1 af samme slags)
        # slås sammen; hvert væsen bærer sit spor (antal + hvilken liste det kom fra).
        # Dedup på (id, skabelon), stærkeste spor først (offset 0 vises før 1/2).
        entries = []
        seen: set = set()
        for fam in families:
            for tier in refdata.summon_tiers(fam, lvl):
                for e in tier["entries"]:
                    key = (e["base"], e["template"])
                    if key in seen:
                        continue
                    seen.add(key)
                    base_name = (db.get_animal(e["base"]) or {}).get("name", e["base"])
                    entries.append({
                        "id": e["base"], "template": e["template"],
                        "name": creature_template.display_name(base_name, e["template"]),
                        "count": tier["count"],
                        "tier_level": tier["list_level"],
                        "offset": tier["offset"],
                    })
        if entries:
            summon_catalog[lvl] = entries

    # Spontan cure/inflict (cleric, SRD): ofre en forberedt IKKE-domæne-plads til
    # en cure-spell af samme niveau eller lavere. Retning følger alignment (evil →
    # inflict, ellers cure — en neutral cleric vælger reelt selv ved level 1, vi
    # defaulter til cure). Domæne-spells ligger separat (domain_spells_prepared),
    # så alt i spells_prepared er per definition ikke-domæne og kan ofres.
    can_spontaneous_cure = bool(refdata.class_data(char.cls).get("spontaneous_cure"))
    cure_direction = "inflict" if "evil" in (char.alignment or "").lower() else "cure"
    cure_catalog: dict[int, list] = {}
    if can_spontaneous_cure:
        convertible = sorted(
            ({"id": s["id"], "name": s["name"], "level": s.get("level_cleric") or 0}
             for s in db.search_spells(class_filter="cleric")
             if s["id"].startswith(cure_direction + "_")
             and s.get("level_cleric") is not None),
            key=lambda s: (s["level"], s["name"]))
        # Pr. forberedt slot-niveau: cure-spells af det niveau eller lavere.
        for lvl in char.spells_prepared:
            eligible = [s for s in convertible if s["level"] <= lvl]
            if eligible:
                cure_catalog[lvl] = eligible

    # Gnome spell-like abilities with DB lookup
    sla_data = []
    for sla in char.racial_traits.get("spell_like_abilities", []):
        if isinstance(sla, dict) and sla.get("id"):
            spell_id = sla["id"]
            note     = sla.get("note", "")
            freq     = sla.get("freq", "")
        elif isinstance(sla, str):
            # Legacy format: "Speak with Animals (gravende dyr) — 1/dag"
            parts    = sla.split(" — ", 1)
            freq     = parts[1].strip() if len(parts) > 1 else ""
            name_part = parts[0].strip()
            m = re.match(r"^(.+?)\s*\((.+?)\)$", name_part)
            clean_name, note = (m.group(1).strip(), m.group(2).strip()) if m else (name_part, "")
            spell_id = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")
        else:
            continue
        spell = db.get_spell(spell_id)

        # Save-DC som monstre skal slå for at modstå evnen.
        # SLA-formel (SRD): 10 + spell level + Cha-modifier. Gnomen lægger +1
        # til DC for illusionsskoler.
        save_dc = None
        save_text = None
        if spell:
            levels = [spell.get(f"level_{c}") for c in
                      ("druid", "cleric", "wizard", "ranger", "paladin")]
            levels = [lv for lv in levels if lv is not None]
            raw_save = (spell.get("save") or "").strip()
            # "None"/tom = ingen redningskast, så ingen DC at vise.
            if levels and raw_save.lower() != "none" and raw_save != "":
                extra = char.racial_traits.get("illusion_dc_bonus", 0) \
                    if "illusion" in (spell.get("school") or "").lower() else 0
                save_dc = char_module.spell_like_dc(
                    min(levels), ab.modifier("cha"), extra)
                save_text = raw_save

        sla_data.append({
            "id":    spell_id,
            "note":  note,
            "freq":  freq,
            "spell": spell,
            "save_dc":   save_dc,
            "save_text": save_text,
        })

    # Spells grupperet pr. niveau — til forberedelses-/known-modal. Klassen caster
    # fra sin mappede kolonne: sorcerer → level_wizard, bard → level_bard, osv.
    cls_lower = char.cls.lower()
    spell_col = db.spell_list_column(cls_lower)
    available_spells: dict[int, list] = {}
    if spell_col:
        for spell in db.search_spells(class_filter=cls_lower):
            lvl = spell.get(spell_col)
            if lvl is not None:
                available_spells.setdefault(lvl, []).append(spell)

    # Spontane castere (sorcerer/bard): de caster spontant fra en KENDT liste, ikke
    # fra forberedte slots. Hvert niveau har en slot-pulje (slots) der bruges op af
    # spells_known_used. Save-DC pr. spell = 10 + niveau + cast-mod + Spell Focus.
    known_data: dict[int, list] = {}
    if cast_type in ("spontaneous", "spellbook"):
        for lvl, spell_ids in char.spells_known.items():
            rows = []
            for sid in spell_ids:
                spell  = db.get_spell(sid)
                school = (spell or {}).get("school", "")
                dc = char_module.spell_save_dc(
                    lvl, cast_mod, char_module.spell_focus_bonus(char.feats, school))
                # ⚡ Kast-data til øjeblikkelige angrebs-/heal-spells (Magic Missile,
                # Fireball, Cure …) — samme som forberedte castere får, så en spontan
                # caster kan rulle det enkelte spell og forbruge én pulje-slot. Utility/
                # varigheds-spells giver None (ingen knap; de er en separat opgave).
                cast = (char_module.spell_cast_info(sid, char.level, db)
                        or char_module.spell_heal_cast_info(sid, char.level, db))
                rows.append({"id": sid, "spell": spell, "dc": dc, "cast": cast})
            known_data[lvl] = rows

    # Kategori E (område/save-spells på "I brug"): skade-formel + save-DC til bordet.
    # Save-DC = 10 + spell-niveau + caster-evne-mod + Spell Focus (skole-afhængigt).
    # Vedvarende rækker (Flaming Sphere) bærer også en tracker (se derive_spell_effects).
    spell_effects = []
    for e in char_module.derive_spell_effects(char, db):
        focus = char_module.spell_focus_bonus(char.feats, e["school"])
        e["dc"] = char_module.spell_save_dc(e["level"], cast_mod, focus)
        spell_effects.append(e)

    # Kategori F (ren utility på "I brug"): ingen tal — bare navn + beregnet varighed.
    # Ingen DC/cast_mod nødvendig; ren visning fra spell_duration.
    spell_utilities = char_module.derive_active_utility(char, db)

    # ⚡ Kast-knap: anden pass over spell_data (rækkerne blev bygget tidligt, før
    # cast_mod var kendt). Dekorér HVER cast (angreb/save/heal) med knap-tekst,
    # terning-feltets label og title. Al tekst bygges her i Python (ikke i
    # templaten) — så spell-navne med ' (Evard's, Otiluke's) ikke bryder en
    # onclick-streng. Save-cast (kategori E) bygges her (kræver cast_mod), men KUN
    # hvis rækken ikke allerede er three_state — et vedvarende spell bruger toggle
    # + Spell-effekter i stedet for en engangs-knap.
    _SAVE_NAMES = {"reflex": "Refleks", "fortitude": "Fysik", "will": "Vilje"}
    _SAVE_FX = {"half": "halv", "negates": "negerer", "partial": "delvis"}
    for lvl, entries in spell_data.items():
        for entry in entries:
            c = entry["cast"]
            if (c is None and not entry["self_duration"] and not entry["is_summon"]
                    and not entry["three_state"]):
                c = char_module.spell_save_cast_info(entry["id"], char.level, db)
                if c:
                    school = (entry["spell"] or {}).get("school", "")
                    focus = char_module.spell_focus_bonus(char.feats, school)
                    c["dc"] = char_module.spell_save_dc(lvl, cast_mod, focus)
                    c["save_name"] = _SAVE_NAMES.get(
                        c["save_type"], c["save_type"].capitalize())
                    c["save_fx_label"] = _SAVE_FX.get(c["save_effect"], c["save_effect"])
                    entry["cast"] = c
            if not c:
                continue
            name = (entry["spell"] or {}).get("name") or entry["id"]
            if c["kind"] == "save":
                dc_txt = f'{c["save_name"]} DC {c["dc"]}'
                if c["save_fx_label"]:
                    dc_txt += f' ({c["save_fx_label"]})'
                c["roll_expr"] = c["damage"]        # E-skade rulles samlet, ikke pr. skud
                c["button_label"] = f"⚡ Kast · {dc_txt}"
                if c["damage"]:
                    c["roll_label"] = f"{name} skade · {dc_txt}"
                    c["title"] = (f"Kast {name} — {dc_txt} · rul {c['damage']} skade "
                                  f"og brug slotten")
                else:
                    c["roll_label"] = f"{name} · {dc_txt}"
                    c["title"] = (f"Kast {name} — {dc_txt}; ingen skade at rulle. "
                                  f"Bruger slotten.")
            elif c["kind"] == "heal":
                c["button_label"] = "⚡ Kast · helbred"
                c["roll_label"] = f"{name} helbredelse"
                c["title"] = f"Kast {name} — rul {c['damage']} helbredelse og brug slotten"
            else:                                    # kategori B (angreb)
                shots = f" ×{c['shots']}" if c["shots"] > 1 else ""
                scaled = f" ×{c['shots']} ({c['roll_expr']})" if c["shots"] > 1 else ""
                hit = "rammer automatisk, " if c["auto_hit"] else ""
                c["button_label"] = f"⚡ Kast{shots}"
                c["roll_label"] = f"{name} skade"
                c["title"] = (f"Kast {name} — {hit}rul {c['damage']}{scaled} skade "
                              f"og brug slotten")

    # Domain spells — a cleric with chosen domains gets one domain slot per
    # spell level he can cast (SRD). The slot may only hold a domain spell.
    domain_slots: dict[int, int] = {}
    domains_info: list = []
    domain_available: dict[int, list] = {}
    domain_prepared: dict[int, dict] = {}
    if char.domains:
        domains_info = db.get_domains(char.domains)
        domain_slots = {lvl: 1 for lvl in slots if lvl >= 1}
        for spell in db.get_domain_spells(char.domains):
            lvl = spell.get("domain_level")
            if lvl in domain_slots:
                domain_available.setdefault(lvl, []).append(spell)
        for lvl in domain_slots:
            sid = char.domain_spells_prepared.get(lvl)
            if sid:
                domain_prepared[lvl] = {
                    "id": sid,
                    "spell": db.get_spell(sid),
                    "used": bool(char.domain_spells_used.get(lvl, False)),
                }

    return {
        "spell_data": spell_data,
        "slots": slots,
        "can_sacrifice": can_sacrifice,
        "summon_catalog": summon_catalog,
        "can_spontaneous_cure": can_spontaneous_cure,
        "cure_direction": cure_direction,
        "cure_catalog": cure_catalog,
        "sla_data": sla_data,
        "available_spells": available_spells,
        "domain_slots": domain_slots,
        "domains_info": domains_info,
        "domain_available": domain_available,
        "domain_prepared": domain_prepared,
        "spell_schools": refdata.SPELL_SCHOOLS,
        "cast_type": cast_type,
        "cast_ability": cast_ability,
        "cast_mod": cast_mod,
        "known_data": known_data,
        "spell_effects": spell_effects,
        "spell_utilities": spell_utilities,
    }
