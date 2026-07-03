"""View-model-bygning for karakterarket.

build_character_view() samler ALLE template-kwargs til character.html ud fra en
indlæst karakter + katalog-db: aktive effekter -> effektive scores -> alle afledte
tal (angreb, saves, skills, AC, ...), udstyr, spells/domæner, companion, wild shape
og effekt-vælgerens kataloger. Ren udledning ved render -- intet gemmes.

Ligger adskilt fra app.py (HTTP-laget) og genbruges af DM-modulets statblok-
inspector. Importerer kun logik-moduler, aldrig app -- så ingen cyklisk import.
"""
import re

import character as char_module
import class_features as class_features_module
import combat_options as combat_options_module
import companion as companion_module
import creature_template
import effects
import refdata
import summon as summon_module
import wild_shape as wild_shape_module


def _race_weapon_prof_ids(race: str, db) -> set:
    """Våben-id'er en race giver proficiency i (fx elv: longsword, rapier, …).

    races.yaml angiver dem som fritekst-navne; her matches de mod våben-kataloget.
    Match på fuldt navn ELLER navn+"," så "longbow" også fanger "Longbow, composite".
    """
    raw = (refdata.race_data(race) or {}).get("weapon_proficiency", "")
    if not raw:
        return set()
    wanted = [n.strip().lower() for n in str(raw).split(",") if n.strip()]
    ids = set()
    for w in db.get_all_weapons():
        low = w["name"].strip().lower()
        if any(low == n or low.startswith(n + ",") for n in wanted):
            ids.add(w["id"])
    return ids


def _inv_row(item, r: dict) -> dict:
    """Byg en inventar-række til JSON (delt af render + /api/inventory).

    Markerer ammunition (is_ammo) og fjerner katalogets bundtstørrelse "(N)"
    fra navnet, da qty nu tæller enkelte skud, ikke bundter.
    """
    name = r["name"]
    rec = r.get("record")
    is_ammo = bool(r.get("source") == "items" and rec
                   and rec.get("category") == "ammunition")
    if is_ammo:
        name = re.sub(r"\s*\(\d+\)\s*$", "", name)
    return {
        "name": name, "weight": r["unit_weight"], "qty": item.qty,
        "notes": item.notes, "state": item.state, "is_ref": bool(item.ref),
        "ref": item.ref, "bonus": item.bonus, "str_mult": item.str_mult,
        "masterwork": item.masterwork, "enhancement": item.enhancement,
        "house_rule": item.house_rule,
        "off_hand": item.off_hand, "double": item.double,
        "is_ammo": is_ammo,
    }


def _paladin_caps(char, cha_mod):
    """Dagens paladin-ressourcer (SRD): lay-on-hands-pulje + smite-uses.

    Lay on Hands: pulje = paladin-level × Cha-bonus HP/dag, kun hvis Cha ≥ 12
    (mod ≥ 1). Smite Evil: 1/dag + 1 pr. 5 levels (5./10./15./20.), max 5.
    """
    lay_pool = char.level * cha_mod if cha_mod >= 1 else 0
    smite_per_day = min(5, 1 + char.level // 5)
    return lay_pool, smite_per_day


def build_character_view(char, db):
    """Byg hele view-modellen (alle template-kwargs) for et karakterark ud fra
    en indlæst karakter + katalog-db.

    Ren udledning ved render: aktive effekter -> effektive scores -> alle afledte
    tal, udstyr/encumbrance, spells/domæner, angreb, companion og effekt-vælgerens
    kataloger. Indeholder ingen request-/slug-afhængige felter (name/slug/
    snapshots/portræt lægger route'en på), så den er uafhængig af Flask-konteksten.
    """
    ab = char.ability_scores

    # Mekaniske effekter: aktive buffs/tilstande → modifiers → effektive ability
    # scores (eff), der kaskaderer ud i alle afledte tal (angreb, skade, saves,
    # skills, grapple, init, AC-Dex). Direkte ikke-ability-bonusser udskydes til
    # en senere fase. Uden aktive effekter er eff == ab, så tallene er uændrede.
    # Permanente planlægningstal (level-up, encumbrance, racial SLA-DC) bruger
    # bevidst de rå scores — en midlertidig buff må ikke påvirke dem.
    active_modifiers, effect_sources = effects.collect_character_effects(char, db)
    # Kampindstillinger (Point Blank/Dodge/Charge/Fighting Defensively/Power
    # Attack/Combat Expertise m.fl.): samme modifier-form som buffs/tilstande,
    # så de bare lægges oveni FØR net beregnes nedenfor. char_feat_ids beregnes
    # lokalt her (i stedet for at flytte hele feat_data-blokken, der først
    # kommer længere nede) — billigt, og undgår at rode med feat_data's egen
    # opbygning. bab flyttet herop (var tidligere beregnet længere nede, ved
    # angrebs-blokken) fordi Power Attacks "N ≤ BAB"-cap skal kendes allerede
    # her, før net beregnes.
    _feat_ids_early = [char_module.feat_id(e) for e in char.feats]
    bab = db.base_attack_bonus(char.cls, char.level)
    active_modifiers = active_modifiers + combat_options_module.active_modifiers(
        char, _feat_ids_early, bab)
    eff = char_module.effective_ability_scores(ab, active_modifiers)
    # Direkte (ikke-ability) bonusser: nettobonus pr. target (attack/damage/
    # save_*/skill_*/speed). AC behandles separat (typerne skal holdes adskilt).
    net = char_module.resolve_modifiers(active_modifiers)
    # Betingede bonusser (kun-mod-X, fx Bless vs frygt) — vises som note, ikke i tallet.
    conditional_notes = []
    for src in effect_sources:
        for m in char_module.conditional_modifiers(src["modifiers"]):
            conditional_notes.append({
                "name": src["name"], "target": m["target"],
                "value": int(m.get("value", 0)), "only_vs": m["only_vs"],
            })
    # Ikke-numeriske ryttere: mekaniske flag (lose_dex/half_speed) + advarsler.
    riders = effects.collect_riders(effect_sources)
    # Midlertidigt HP (Virtue + Bear's Endurance fra hævet Con): hæver HP-loftet,
    # så det kan tracking-bruges.
    temp_hp = effects.temp_hp_from_modifiers(active_modifiers, ab, eff, char.level)

    # Equipped rustning/skjold → bruges til både AC og rustnings-tjekstraf (ACP).
    # Udledes fra inventaret (worn-poster); falder tilbage til combat.armor/shield
    # for endnu-ikke-migrerede karakterer.
    inv_armor, inv_shield = char_module.equipped_armor(char.inventory, db)
    armor_row  = inv_armor  or (db.get_armor(char.armor)  if char.armor  else None)
    shield_row = inv_shield or (db.get_armor(char.shield) if char.shield else None)
    acp = char_module.armor_check_penalty(armor_row, shield_row)
    # Druide i metalrustning/-skjold mister spellcasting (+ su/sp-evner) i 24t
    druid_armor_block = char_module.druid_armor_violations(char.cls, armor_row, shield_row)

    # Weapon & armor proficiency: uvant grej giver straf (−4 på angreb / ACP-på-
    # angreb), ikke et forbud. Race kan give ekstra våben-proficiency (elv m.fl.);
    # en house-rule pr. genstand (item.house_rule) fjerner straf + advarsel.
    weapon_prof = char_module.class_weapon_proficiency(char.cls)
    armor_prof  = char_module.class_armor_proficiency(char.cls)
    allowed_weapons = _race_weapon_prof_ids(char.race, db)
    prof_block = char_module.proficiency_violations(
        weapon_prof, armor_prof, char.inventory, db, allowed_weapons)
    armor_atk_pen = char_module.armor_attack_penalty(armor_prof, char.inventory, db)

    racial_save = int(char_module.race_data(char.race).get("save_bonus", 0))
    # Base fort/ref/will udledes af klasse+level (gemmes aldrig — se db.base_saves),
    # så de aldrig bliver forældede ved level-up. Præcis samme mønster som BAB.
    class_saves = db.base_saves(char.cls, char.level)
    # Saves vises effektivt (eff) men bærer basis-værdien med, så en ▲/▼-markør
    # kan vise hvornår en aktiv effekt ændrede tallet.
    saves = []
    for label, skey, akey in (("Fortitude", "fortitude", "con"),
                              ("Reflex", "reflex", "dex"),
                              ("Will", "will", "wis")):
        eff_bonus = char_module.save_effect_bonus(active_modifiers, skey)
        base_v = char_module.save_total(class_saves.get(skey, 0), getattr(ab, akey), racial_save)
        eff_v = char_module.save_total(class_saves.get(skey, 0), getattr(eff, akey),
                                       racial_save, eff_bonus)
        src = effects.stat_sources(effect_sources, {"save_all", char_module.SAVE_TARGETS[skey]}, akey)
        saves.append(effects.delta_row(label, eff_v, base_v, src))

    synergy_bonuses = char_module.compute_synergy_bonuses(char.skills)
    synergy_src_map = char_module.synergy_sources(char.skills)
    char_skill_map = {s.id: s for s in char.skills}
    all_skill_defs = db.get_all_skills()
    skill_name = {sk["id"]: sk["name"] for sk in all_skill_defs}
    skill_breakdowns = {}   # {id: {name, total, parts:[{label,value}]}} — til hover-opdeling
    skill_data = []
    for defn in all_skill_defs:
        s = char_skill_map.get(defn["id"]) or char_module.Skill(id=defn["id"], ranks=0.0)
        synergy = synergy_bonuses.get(s.id, 0)
        ranked = int(s.ranks) > 0
        trained_only = bool(defn.get("trained_only"))
        eff_bonus = char_module.skill_effect_bonus(active_modifiers, s.id)
        total = char_module.skill_total(s, eff, db, synergy, acp, eff_bonus)
        # Basis (uden aktive effekter) → ▲/▼-markør når en effekt ændrede skill'en.
        pre_effect = char_module.skill_total(s, ab, db, synergy, acp)
        acp_applied = acp * int(defn.get("armor_check", 0) or 0)
        # Opdeling til hover: hver bestanddel der lægges sammen til totalen, med
        # navngiven kilde (misc bærer sin label, fx "Nature Sense"; synergi viser
        # hvilke skills den kommer fra). Summen = item.total.
        ability = defn.get("ability")
        parts = [{"label": "ranks", "value": int(s.ranks)}]
        if ability and ability != "none":
            parts.append({"label": ability.upper(), "value": eff.modifier(ability)})
        if s.misc:
            parts.append({"label": s.misc_note or "diverse", "value": s.misc})
        if synergy:
            syn_names = ", ".join(skill_name.get(src, src)
                                  for src, _ in synergy_src_map.get(s.id, []))
            parts.append({"label": f"synergi ({syn_names})" if syn_names else "synergi",
                          "value": synergy})
        if acp_applied:
            parts.append({"label": "rustning (ACP)", "value": acp_applied})
        if eff_bonus:
            parts.append({"label": "effekter", "value": eff_bonus})
        skill_breakdowns[s.id] = {
            "name": defn["name"] if defn else s.id, "total": total, "parts": parts}
        skill_data.append({
            "skill": s, "defn": defn,
            "total": total,
            "acp_applied": acp_applied,
            # Synergibonusser er situationsbetingede (SRD) — vis også den "rene"
            # total uden synergi, så man kender værdien når synergien ikke gælder.
            "base_total": total - synergy,
            "synergy": synergy,
            "ranked": ranked,
            "trained_only": trained_only,
            # Utrænet kan kun bruges hvis skill'en ikke er trained-only,
            # eller hvis Tjørn faktisk har ranks i den.
            "usable": ranked or not trained_only,
            "effect_changed": total != pre_effect,
            "effect_up": total > pre_effect,
            "pre_effect": pre_effect,
            "effect_detail": " · ".join(
                f"{x['name']} {x['value']:+d}" for x in effects.stat_sources(
                    effect_sources, {"skill_all", f"skill:{s.id}"}, defn.get("ability"))),
        })
    # Feat-poster kan være rene id-strenge eller {id, weapon}; vis label med våben.
    feat_data = []
    for e in char.feats:
        fid = char_module.feat_id(e)
        row = db.get_feat(fid)
        feat_data.append((fid, row, char_module.feat_label(e, row)))
    char_feat_ids = _feat_ids_early  # samme liste som blev beregnet tidligt til kampindstillinger

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
            rows.append({
                "id": sid, "index": i, "spell": spell,
                "used": state != "free", "state": state,
                "self_duration": bool(spell and spell.get("self_duration")),
                "is_summon": refdata.summon_family(sid) is not None,
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

    condition_data  = [(cid, db.get_condition(cid)) for cid in char.conditions]
    all_conditions  = db.get_all_conditions()

    class_level_data = db.get_class_level(char.cls.lower(), char.level)
    slots: dict[int, int] = {}
    if class_level_data:
        # Casting-ability er nu data-drevet (cha for bard/sorcerer, int for wizard,
        # wis for cleric/druid/ranger/paladin). Default wis for klasser uden feltet.
        cast_ab = refdata.class_data(char.cls).get("cast_ability", "wis")
        slots = char_module.spell_slots_total(class_level_data, getattr(ab, cast_ab))

    xp_info    = char_module.xp_progress(char.experience_points, char.level)
    weight     = char_module.carried_weight(char.inventory, db, char.size)
    enc_limits = char_module.carry_limits(ab.str, char.size)
    enc        = char_module.encumbrance_level(ab.str, weight, char.size)
    base_speed = char.combat.get("speed", 30)
    # Beriget inventar-visning: navn/vægt slås op i kataloget for ref-poster,
    # størrelses-justeres, og state vises. is_ref => navn/vægt redigeres ikke i UI.
    inventory_json = [_inv_row(i, char_module.resolve_item(i, db, char.size))
                      for i in char.inventory]

    # Katalog til "tilføj fra katalog"-vælgeren (ref, navn, gruppe pr. type)
    catalog_json = {
        "weapons": [{"ref": f"weapons/{w['id']}", "name": w["name"], "group": w["category"]}
                    for w in db.get_all_weapons()],
        "armor":   [{"ref": f"armor/{a['id']}", "name": a["name"], "group": a["type"]}
                    for a in db.get_all_armor()],
        "items":   [{"ref": f"items/{it['id']}", "name": it["name"], "group": it["category"]}
                    for it in db.get_all_items()],
    }

    # Combat: beregn til-hit/skade pr. angreb + grapple + initiativ (gemmes aldrig i YAML).
    # Angreb = eksplicitte (spells/unarmed) + afledte fra våben i hånden (wielded).
    # (bab beregnes nu tidligere, se kommentar ved combat_options_module.active_modifiers ovenfor)
    # Betingede spell-angreb (Attack.requires) vises kun når den spell der
    # skaber dem står på "I brug" (varighed kører).
    active_keys = char_module.active_spell_keys(
        char.spells_prepared, char.spells_active, db)

    # Direkte angrebs-/skade-bonusser (Bless, Magic Fang, Divine Favor,
    # shaken/sickened-straffe). Ability-delen kaskaderer via eff; disse lægges på.
    # armor_atk_pen (≤0): uvant rustning → tjekstraffen rammer også alle angreb.
    attack_extra = net.get("attack", 0) + armor_atk_pen
    damage_extra = net.get("damage", 0)

    has_finesse = "weapon_finesse" in char_feat_ids

    def _atk_fields(atk):
        """Til-hit/skade for et angreb (effektivt) + delta-info vs. basis-scores.

        Bull's Strength m.fl. kaskaderer via eff; direkte bonusser (attack/damage)
        lægges på her. Basis er angrebet helt uden aktive effekter.

        Ud over de GLOBALE attack_extra/damage_extra (rammer alle angreb) lægges
        scope'ede bonusser oveni pr. angreb ud fra atk.kind — fx Point Blank Shot
        (attack_ranged/damage_ranged) rammer kun ranged-angreb, ikke melee.
        """
        if atk.kind in ("melee", "melee_touch"):
            scoped_atk, scoped_dmg = net.get("attack_melee", 0), net.get("damage_melee", 0)
        elif atk.kind in ("ranged", "ranged_touch"):
            scoped_atk, scoped_dmg = net.get("attack_ranged", 0), net.get("damage_ranged", 0)
        else:
            scoped_atk = scoped_dmg = 0
        atk_extra = attack_extra + scoped_atk
        dmg_extra = damage_extra + scoped_dmg

        e = char_module.attack_total(atk, eff, bab, char.size, atk_extra, dmg_extra, has_finesse)
        b = char_module.attack_total(atk, ab, bab, char.size, has_finesse=has_finesse)
        # Opdeling til hover (samme komponenter som e's to_hit): BAB + ability +
        # størrelse + våben + effekter. Genbruger skill-breakdown-tooltippen i JS.
        hit_bd = char_module.attack_to_hit_breakdown(
            atk, eff, bab, char.size, atk_extra, has_finesse)
        # Skade-opdeling (terning + Str×mult + effekter) — samme hover som til-hit.
        dmg_bd = char_module.attack_damage_breakdown(atk, eff, dmg_extra)
        return {**e,
                "hit_parts": hit_bd["parts"],
                "hit_changed": e["to_hit"] != b["to_hit"], "hit_up": e["to_hit"] > b["to_hit"],
                "base_to_hit": b["to_hit"],
                "dmg_parts": dmg_bd["parts"],
                "dmg_changed": e["damage"] != b["damage"],
                "dmg_up": effects.damage_bonus(e["damage"]) > effects.damage_bonus(b["damage"]),
                "base_dmg": b["damage"]}

    def _row(atk, manual, idx):
        return {"attack": atk, "manual": manual, "idx": idx, **_atk_fields(atk)}

    # Two-weapon fighting: hvilke TWF-niveauer har karakteren (feat ELLER ranger-stil
    # i let/ingen rustning)? Fodres til derive_attacks så off-hånds-straffen regnes.
    twf_ctx = char_module.twf_context(char.cls, char.level, char.class_features,
                                      char_feat_ids, armor_row)
    # Hånd-budget (blød advarsel): wielded våben + skjold må højst optage 2 hænder.
    hand_block = char_module.hand_usage(char.inventory, db)

    # Våben-angreb (udledt af inventaret) først, så manuelle angreb fra YAML.
    # Kun manuelle angreb kan redigeres her (idx = position i char.attacks).
    # derived fanges i en variabel (fremfor at forbruges direkte i comprehension'en)
    # så vi kan filtrere ranged-skabelonerne ud til Kampindstillinger Lag C
    # (Rapid Shot/Manyshot skal klone karakterens bedste wielded ranged-angreb).
    derived = char_module.derive_attacks(char.inventory, db, char.size,
                                         weapon_prof, allowed_weapons, twf_ctx,
                                         char.feats)
    ranged_templates = [a for a in derived if a.kind in ("ranged", "ranged_touch")]
    attack_rows = [_row(a, False, None) for a in derived
                   if char_module.attack_visible(a, active_keys)]
    attack_rows += [_row(a, True, i) for i, a in enumerate(char.attacks)
                    if char_module.attack_visible(a, active_keys)]

    # Kampindstillinger Lag C: options der injicerer en ekstra angrebsrække
    # (Rapid Shot/Manyshot). Klonen køres gennem _row, så scope-effekter (Rapid
    # Shots −2 på alle ranged) rammer den gratis via _atk_fields.
    for a in combat_options_module.extra_attacks(char, char_feat_ids, ranged_templates):
        attack_rows.append(_row(a, False, None))

    # Monk unarmed strike + Flurry of Blows: automatiske angreb baseret på level/size.
    # Kræver unarmored (ingen rustning), intet skjold og let last for flurry.
    monk_flurry_active = False
    if char.cls == "Monk":
        monk_flurry_active = (not armor_row) and (not shield_row) and (enc == "Light")
        _monk_damage = refdata.monk_unarmed_damage(char.level, char.size)
        _monk_penalty = refdata.monk_flurry_penalty(char.level)
        _monk_greater = refdata.monk_greater_flurry(char.level)
        monk_atks = char_module.monk_unarmed_attacks(
            char.level, char.size, _monk_penalty, _monk_greater,
            monk_flurry_active, _monk_damage,
        )
        for a in monk_atks:
            attack_rows.append(_row(a, False, None))

    # Udledte spell-angreb: fra spells på "I brug" via spell_attacks-kataloget.
    # Bærer evt. ladnings-info (Magic Stone: 3 sten) til nedtælling i UI'en.
    for d in char_module.derive_spell_attacks(char, db):
        atk = d["attack"]
        attack_rows.append({
            "attack": atk, "manual": False, "idx": None,
            **_atk_fields(atk),
            "charges_max": d["charges_max"],
            "charges_remaining": d["charges_remaining"],
            "charge_level": d["level"], "charge_index": d["index"],
            "alt_note": d["alt_note"],
        })

    # Rå felter for alle manuelle angreb → redigering i browseren (også de slukkede).
    attacks_json = [{
        "idx": i, "name": a.name, "kind": a.kind, "bonus": a.bonus,
        "base_damage": a.base_damage, "fixed_damage": a.fixed_damage,
        "str_damage_mult": a.str_damage_mult, "crit": a.crit, "type": a.type,
        "range": a.range, "source": a.source, "requires": a.requires,
    } for i, a in enumerate(char.attacks)]

    # AC: karakterens egne typede bonusser (combat) kombineres med aktive AC-
    # effekter (Shield of Faith deflection, Barkskin natural …) under stacking-
    # reglerne, og Dex kommer fra eff. Basis er rå scores + kun combat-felterne.
    _combat_ac = {
        "natural": int(char.combat.get("natural_armor", 0)),
        "deflection": int(char.combat.get("deflection", 0)),
        "dodge": int(char.combat.get("dodge", 0)),
        "misc": int(char.combat.get("misc_ac", 0)),
    }
    # Monk AC Bonus (Ex): + ability-mod (Wis) + level-skaleret bonus til AC når unarmored.
    # Data-drevet via klassens ac_ability; en klasse-feature → bygges på base-AC.
    _ac_ability = char_module.class_ac_ability(char.cls)
    if _ac_ability and not armor_row and not shield_row:
        _combat_ac["misc"] += max(0, ab.modifier(_ac_ability))
        if char.cls == "Monk":
            _combat_ac["misc"] += refdata.monk_ac_bonus(char.level)
    _ac_common = dict(
        armor=armor_row,
        shield=shield_row,
        enc_max_dex=char_module.encumbrance_consequences(enc, base_speed)["max_dex"],
    )
    ac_bonuses = char_module.resolve_ac_bonuses(
        _combat_ac, [m for m in active_modifiers if m.get("target") == "ac"])
    init_misc = int(char.combat.get("initiative_misc", 0))
    initiative = effects.delta_row(
        "Init",
        char_module.initiative_total(eff, char.feats, init_misc, net.get("init", 0)),
        char_module.initiative_total(ab, char.feats, init_misc),
        effects.stat_sources(effect_sources, {"init"}, "dex"))
    ac = char_module.armor_class(eff, char.size, **_ac_common, **ac_bonuses,
                                 lose_dex=riders["lose_dex"])
    ac_base = char_module.armor_class(ab, char.size, **_ac_common, **_combat_ac)
    # Pr. AC-tal: er det ændret af en effekt? (Dex + typede AC-bonusser + lose_dex.)
    ac_src = effects.stat_sources(effect_sources, {"ac"}, "dex")
    ac_delta = {k: effects.delta_row(k, ac[k], ac_base[k], ac_src) for k in ("ac", "touch", "flat_footed")}

    grapple = effects.delta_row("Grapple",
                         char_module.grapple_total(bab, eff.str, char.size),
                         char_module.grapple_total(bab, ab.str, char.size),
                         effects.stat_sources(effect_sources, set(), "str"))

    # Speed: longstrider (+) m.fl., derefter halvering hvis en rytter kræver det
    # (blinded/entangled/exhausted). base er karakterens rå hastighed.
    # Monk Fast Movement: dynamisk bonus — kun unarmored + let last (ikke bagt ind ved oprettelse).
    eff_speed = base_speed + net.get("speed", 0)
    if char.cls == "Monk" and monk_flurry_active:
        eff_speed += refdata.monk_fast_movement(char.level)
    if riders["half_speed"]:
        eff_speed //= 2
    speed = effects.delta_row("Speed", eff_speed, base_speed,
                       effects.stat_sources(effect_sources, {"speed"}))

    # Evnescores vises effektivt med basis + breakdown når en effekt ændrede dem.
    ability_breakdown = effects.ability_breakdown(effect_sources)
    abilities = []
    for abbr, key in (("STR", "str"), ("DEX", "dex"), ("CON", "con"),
                      ("INT", "int"), ("WIS", "wis"), ("CHA", "cha")):
        base_s, eff_s = getattr(ab, key), getattr(eff, key)
        abilities.append({
            "abbr": abbr, "key": key,
            "base": base_s, "score": eff_s,
            "base_mod": ab.modifier(key), "mod": eff.modifier(key),
            "sources": ability_breakdown.get(key, []),
            "changed": eff_s != base_s, "up": eff_s > base_s,
        })

    # Level-up info
    new_level = char.level + 1
    new_level_data = db.get_class_level(char.cls.lower(), new_level)
    new_features: list[str] = []
    if new_level_data:
        raw = new_level_data.get("features", [])
        new_features = raw if isinstance(raw, list) else [f"{k}: {v}" for k, v in raw.items()]
    levelup_info = {
        "current_level": char.level,
        "new_level":     new_level,
        "hit_die":       char_module.hit_die(char.cls),
        "con_modifier":  ab.modifier("con"),
        "skill_points":  char_module.skill_points_per_level(char.cls, ab.modifier("int"), char.race),
        "feat_level":    char_module.is_feat_level(new_level),
        "bonus_feat_level": "Bonus Feat" in new_features,   # klasse-bonus-feat (fx fighter), drevet af class_levels-data
        "ability_level": char_module.is_ability_level(new_level),
        "new_features":  new_features,
        "xp_ready":      xp_info["ready"],
    }
    # Feat-eligibility til level-up-vælgeren: genbrug den samme prereq-motor som
    # oprettelse (feat_prereq_unmet), så reglerne kun bor ét sted. Evalueres mod
    # Tjørns AKTUELLE tilstand (ejede feats + scores + klasse) og BAB på ny level.
    # Ved level-up vælges kun ét feat ad gangen, så kæder skal opfyldes af allerede
    # ejede feats — derfor er owned = nuværende feats (ikke det man er ved at vælge).
    _all_feats = db.get_all_feats()
    _name_by_id = {f["id"]: f["name"] for f in _all_feats}
    _name_to_id = {f["name"].lower(): f["id"] for f in _all_feats}
    _owned = char_module.owned_feat_tokens(char.feats, _name_by_id)
    _scores = {a: getattr(ab, a) for a in ("str", "dex", "con", "int", "wis", "cha")}
    _new_bab = int((new_level_data or {}).get("bab", 0))
    all_feats_json = []
    for f in _all_feats:
        unmet = char_module.feat_prereq_unmet(
            f.get("prerequisites") or "", _owned, _scores,
            char.cls, new_level, _new_bab, _name_to_id)
        all_feats_json.append({
            "id": f["id"], "name": f["name"],
            "type": f.get("type") or "",
            "prerequisites": f.get("prerequisites") or "",
            "benefit": f.get("benefit") or "",
            "eligible": not unmet,
            "unmet": unmet,
            "fighter_bonus": bool(f.get("fighter_bonus")),
        })
    all_skills_json = [
        {"id": s["id"], "name": s["name"], "ability": s.get("ability", ""),
         "trained_only": bool(s.get("trained_only")),
         "description": s.get("description") or ""}
        for s in db.get_all_skills()
    ]
    cls_skills_json = sorted(char_module.class_skills(char.cls))

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
    cast_type    = refdata.class_cast_type(char.cls)
    cast_ability = refdata.class_data(char.cls).get("cast_ability", "wis")
    cast_mod     = ab.modifier(cast_ability)
    known_data: dict[int, list] = {}
    if cast_type in ("spontaneous", "spellbook"):
        for lvl, spell_ids in char.spells_known.items():
            rows = []
            for sid in spell_ids:
                spell  = db.get_spell(sid)
                school = (spell or {}).get("school", "")
                dc = char_module.spell_save_dc(
                    lvl, cast_mod, char_module.spell_focus_bonus(char.feats, school))
                rows.append({"id": sid, "spell": spell, "dc": dc})
            known_data[lvl] = rows

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

    # Companion/mount: beregn det fulde statblok fra den tynde reference (eller None).
    companion = companion_module.build_companion(char, db)
    # Hvilken slags ledsager kan klassen tilkalde? Druide L1/ranger L4+ → animal
    # companion (companion_ok-filtreret liste); paladin L5+ → special mount (kun
    # warhorse/warpony). Begge bruger samme "Tilkald"-knap + companion-fane.
    is_mount = companion_module.mount_eligible(char.cls, char.level)
    if is_mount:
        companion_noun = "Mount"
        can_summon_companion = True
        companion_animals = [{"id": a["id"], "name": a["name"]} for a in db.get_all_animals()
                             if a["id"] in ("heavy_warhorse", "warpony")]
    else:
        companion_noun = "Animal Companion"
        can_summon_companion = companion_module.companion_effective_level(char.cls, char.level) > 0
        companion_animals = ([{"id": a["id"], "name": a["name"]} for a in db.get_all_animals()
                              if a.get("companion_ok") != 0] if can_summon_companion else [])

    # Wild Shape: progressions-info, lovlige former og evt. aktiv (merged) form.
    ws_data = char_module.class_wild_shape(char.cls)
    ws_info = wild_shape_module.wild_shape_info(ws_data, char.level, char.feats)
    wild_form = wild_shape_module.build_wild_shape_form(char, ws_data, db)
    wild_shape_ctx = None
    if ws_info:
        st = char.wild_shape or {}
        wild_shape_ctx = {
            **ws_info,
            "animal_left": ws_info["animal_uses"] - int(st.get("animal_used", 0)),
            "elemental_left": ws_info["elemental_uses"] - int(st.get("elemental_used", 0)),
            "forms": wild_shape_module.eligible_forms(ws_info, char.level, db),
        }

    # Summons: render hvert aktivt Summon Nature's Ally-væsen (tom liste = ingen faner).
    summons = summon_module.build_summons(char.summons, db)

    # Effekt-vælgerens kataloger bygges fra effects-tabellen (kilden til sandheden).
    buff_catalog, damage_catalog = effects.picker_catalogs()

    # Barbarian Rage: aktiverbar klasse-feature (genbruger buff-motoren via spell_id
    # "rage"). Brug/dag = 1 + level//4 (max 6) — vises som påmindelse; ingen daglig-
    # reset-tæller endnu. raging = om rage-buffen er aktiv lige nu.
    can_rage = char.cls == "Barbarian"
    rage_per_day = min(6, 1 + char.level // 4) if can_rage else 0
    raging = any(b.get("spell_id") == "rage" for b in char.buffs)

    # Paladin: Smite Evil + Lay on Hands (beregnet panel + dag-tællere). Bruger den
    # effektive Cha (eff), så Cha-buffs slår igennem på puljen, ligesom andre afledte tal.
    paladin_info = None
    if char.cls == "Paladin":
        cha_mod = eff.modifier("cha")
        lay_pool, smite_per_day = _paladin_caps(char, cha_mod)
        paladin_info = {
            "cha_mod": cha_mod,
            "lay_pool": lay_pool,
            "lay_remaining": max(0, lay_pool - char.lay_on_hands_used),
            "smite_per_day": smite_per_day,
            "smite_remaining": max(0, smite_per_day - char.smite_used),
            "smite_attack": max(0, cha_mod),   # +Cha til angreb (0 hvis ingen bonus)
            "smite_damage": char.level,        # +1 skade pr. paladin-level
        }

    # Rogue Sneak Attack: +1d6 ved level 1, +1d6 pr. 2 levels (max 10d6 ved level 19).
    # Betinget skade (flankeret / nægtet Dex), så den VISES og påføres af spilleren —
    # den må ikke lægges fast på hvert angreb (samme stil som Smite Evil).
    rogue_info = None
    if char.cls == "Rogue":
        rogue_info = {"sneak_dice": (char.level + 1) // 2}

    # Monk-features: Flurry of Blows, Ki Strike, Fast Movement, Evasion, AC-bonus.
    # Alle beregnes ved visning — intet gemmes i YAML.
    monk_info = None
    if char.cls == "Monk":
        _flurry_extra = 2 if refdata.monk_greater_flurry(char.level) else 1
        monk_info = {
            "flurry_penalty":       refdata.monk_flurry_penalty(char.level),
            "flurry_extra_attacks": _flurry_extra,
            "ki_strike":            refdata.monk_ki_strike(char.level),
            "evasion":              refdata.monk_evasion(char.level),
            "fast_movement":        refdata.monk_fast_movement(char.level) if monk_flurry_active else 0,
            "ac_bonus":             refdata.monk_ac_bonus(char.level),
            "unarmored":            monk_flurry_active,
        }

    # Klasseevner → klikbar visnings-model: hver evne får evt. en slug til
    # /api/detail/ability (samme klik-forklaring som wild shape). Kendes slug'en
    # ikke i kataloget, vises evnen uden klik (fallback), så data kan fyldes på
    # bagefter uden at nogen evne 404'er ved klik.
    known_ability_ids = {a["id"] for a in db.get_all_special_abilities()}
    class_feature_rows = class_features_module.feature_rows(
        char.class_features, known_ability_ids)

    return {
        "class_feature_rows": class_feature_rows,
        "companion": companion,
        "can_summon_companion": can_summon_companion,
        "companion_animals": companion_animals,
        "companion_noun": companion_noun,
        "wild_shape_info": wild_shape_ctx,
        "wild_form": wild_form,
        "summons": summons,
        "summon_catalog": summon_catalog,
        "can_sacrifice": can_sacrifice,
        "can_spontaneous_cure": can_spontaneous_cure,
        "cure_direction": cure_direction,
        "cure_catalog": cure_catalog,
        "abilities": abilities,
        "saves": saves,
        "skill_data": skill_data,
        "skill_breakdowns": skill_breakdowns,
        "feat_data": feat_data,
        "char_feat_ids": char_feat_ids,
        "combat_options_panel": combat_options_module.panel(char, char_feat_ids, bab),
        "spell_data": spell_data,
        "slots": slots,
        "condition_data": condition_data,
        "all_conditions": all_conditions,
        "buff_catalog": buff_catalog,
        "damage_catalog": damage_catalog,
        "can_rage": can_rage,
        "rage_per_day": rage_per_day,
        "raging": raging,
        "paladin_info": paladin_info,
        "rogue_info": rogue_info,
        "monk_info": monk_info,
        "xp_info": xp_info,
        "weight": weight,
        "enc_limits": enc_limits,
        "enc": enc,
        "base_speed": base_speed,
        "attack_rows": attack_rows,
        "attacks_json": attacks_json,
        "bab": bab,
        "grapple": grapple,
        "initiative": initiative,
        "ac": ac,
        "ac_delta": ac_delta,
        "speed": speed,
        "conditional_notes": conditional_notes,
        "effect_flags": riders["flags"],
        "temp_hp": temp_hp,
        "druid_armor_block": druid_armor_block,
        "prof_block": prof_block,
        "hand_block": hand_block,
        "armor_atk_pen": armor_atk_pen,
        "inventory_json": inventory_json,
        "catalog_json": catalog_json,
        "available_spells": available_spells,
        "domain_slots": domain_slots,
        "domains_info": domains_info,
        "domain_available": domain_available,
        "domain_prepared": domain_prepared,
        "sla_data": sla_data,
        "levelup_info": levelup_info,
        "all_feats_json": all_feats_json,
        "all_skills_json": all_skills_json,
        "cls_skills_json": cls_skills_json,
        "spell_schools": refdata.SPELL_SCHOOLS,
        "cast_type": cast_type,
        "cast_ability": cast_ability,
        "cast_mod": cast_mod,
        "known_data": known_data,
    }
