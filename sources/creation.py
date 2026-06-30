"""Karakter-oprettelse: generator-kontekst + bygning af ny karakter-data.

Indeholder oprettelses-LOGIKKEN (ren udregning fra formular-felter til en rå
karakter-data-dict), adskilt fra app.py's HTTP-rute. Generatorens kuraterede
lister (GEN_CLASSES/RACES/DOMAINS) bor her, fordi de er en del af "hvad
generatoren tilbyder". Importerer kun logik-moduler -- aldrig app.
"""
import json

import catalog
import character as char_module
import companion as companion_module
import db
import refdata

from character_view import _race_weapon_prof_ids


# Klasser generatoren understøtter (motoren er bevist mod disse).
GEN_CLASSES = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Wizard"]
# Racer udledes fra data/races.yaml — en race er ren data (ingen motor-logik), så
# enhver race i datafilen er fuldt understøttet. Tilføj en race = tilføj en YAML-blok.
# .title() (ikke .capitalize()) så hyphenerede racer vises korrekt: half-orc → Half-Orc.
GEN_RACES = [r.title() for r in char_module.race_ids()]
# Alle 22 SRD-kerne-domæner. En kleriker vælger 2. Granted power er den primære
# gevinst ved level 1; domain-spells dækkes i det omfang de findes i spells-DB'en.
GEN_DOMAINS = [
    "air", "animal", "chaos", "death", "destruction", "earth", "evil", "fire",
    "good", "healing", "knowledge", "law", "luck", "magic", "plant", "protection",
    "strength", "sun", "travel", "trickery", "war", "water",
]


# Tilstand en butiks-valgt genstand får ud fra sin katalog-tabel.
_EQUIP_STATE_BY_TABLE = {"armor": "worn", "weapons": "wielded", "items": "backpack"}


def _parse_equipment(raw: str) -> list[dict]:
    """Parse udrustningsbutikkens skjulte 'equipment'-JSON → inventar-poster.

    Felt-format pr. post: {ref, category, qty}. Tilstanden udledes af tabellen i
    ref (armor=worn, weapons=wielded, items=backpack). Hver ref valideres mod
    kataloget; ugyldig JSON eller ukendt ref afvises med en klar fejl. Dubletter
    (samme ref) ignoreres. Returnerer den eksisterende inventar-dict-form, så den
    fodres uændret ind i create_character()s gem-logik.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        picked = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError("Ugyldigt udstyrs-valg (kunne ikke læses).")
    if not isinstance(picked, list):
        raise ValueError("Ugyldigt udstyrs-valg.")
    getters = {"weapons": db.get_weapon, "armor": db.get_armor, "items": db.get_item}
    inventory: list[dict] = []
    seen: set[str] = set()
    for entry in picked:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("ref", "")).strip()
        table, _, oid = ref.partition("/")
        record = getters[table](oid) if table in getters else None
        if not record:
            raise ValueError(f"Ukendt genstand i udstyr: {ref or '—'}.")
        if ref in seen:
            continue
        seen.add(ref)
        try:
            qty = max(1, int(entry.get("qty", 1)))
        except (ValueError, TypeError):
            qty = 1
        item = {"ref": ref, "state": _EQUIP_STATE_BY_TABLE[table], "qty": qty}
        # Materiale-/kvalitets-mods (masterwork/cold iron/sølv) → ekstra felter.
        item.update(catalog.apply_material_overlay(record, table, entry.get("mods")))
        inventory.append(item)
    return inventory


def _format_cost(cost_cp) -> str:
    """cp → læsbar pris: 1500→'15 gp', 70→'7 sp', 205→'2 gp 5 cp', 0→'—'.

    Tynd façade over catalog.format_cost, så pris-formateringen kun findes ét sted.
    """
    return catalog.format_cost(cost_cp)


def _class_bonus_feat_ids(cls: str) -> list:
    """Feat-id'er klassens level-1 bonus-feat vælges fra. Eksplicit pulje (monk:
    improved_grapple/stunning_fist) eller den brede fighter-bonus-pulje."""
    pool = char_module.class_bonus_feat_pool(cls)
    if pool is not None:
        return pool
    if char_module.class_bonus_feat_choices(cls):
        return [f["id"] for f in db.get_fighter_bonus_feats()]
    return []


def _gen_context() -> dict:
    """Data til generatorformularen (klasse/race-lister + regel-data til JS)."""
    races_json = {
        r.lower(): {
            "ability_adjust": char_module.race_data(r).get("ability_adjust", {}),
            "skill_bonuses": char_module.race_data(r).get("skill_bonuses", {}),
            "size": char_module.race_data(r).get("size", "medium"),
            "speed": char_module.race_data(r).get("speed", 30),
            "feat_count": char_module.level1_feat_count(r),
            "languages_auto": char_module.race_data(r).get("languages", {}).get("automatic", []),
            "languages_bonus": char_module.race_bonus_languages(r),
            "bio": char_module.race_bio(r),
            "weapon_prof_ids": sorted(_race_weapon_prof_ids(r, db)),
        }
        for r in GEN_RACES
    }
    classes_json = {
        c.lower(): {
            "skill_base": char_module.base_skill_points(c),
            "class_skills": sorted(char_module.class_skills(c)),
            "hit_die": char_module.hit_die(c),
            "needs_domains": char_module.class_needs_domains(c),
            "bonus_feats": char_module.class_bonus_feats(c),
            "bonus_feat_choices": char_module.class_bonus_feat_choices(c),
            "bonus_feat_ignore_prereqs": char_module.class_bonus_feat_ignore_prereqs(c),
            "starting_gold": char_module.class_starting_gold(c),
            "age_group": char_module.class_age_group(c),
            "bab1": int((db.get_class_level(c.lower(), 1) or {}).get("bab", 0)),
            "turn_undead": char_module.class_can_turn_undead(c),
            # Companion ved level 1 (kun druide; ranger får først ved level 4).
            "has_companion": companion_module.companion_effective_level(c, 1) > 0,
            "languages_auto": char_module.class_languages(c).get("automatic", []),
            "languages_bonus": char_module.class_languages(c).get("bonus", []),
            "weapon_proficiency": char_module.class_weapon_proficiency(c),
            "armor_proficiency": char_module.class_armor_proficiency(c),
        }
        for c in GEN_CLASSES
    }
    all_feats = db.get_all_feats()
    # Bonus-feat-kandidater: foreningen af alle klassers bonus-feat-puljer, hver
    # tagget med hvilke klasser der må vælge den (vises/skjules pr. klasse i JS).
    by_id = {f["id"]: f for f in all_feats}
    bonus_eligible: dict[str, set] = {}
    for c in GEN_CLASSES:
        for fid in _class_bonus_feat_ids(c):
            bonus_eligible.setdefault(fid, set()).add(c.lower())
    bonus_feat_candidates = sorted(
        ({**by_id[fid], "eligible": " ".join(sorted(cs))}
         for fid, cs in bonus_eligible.items() if fid in by_id),
        key=lambda f: f["name"])
    # weapons: bruges af våben-valg-feats (Weapon Focus m.fl.) — grupperet på group.
    # (Udstyrs-dropdowns er væk; udrustningsbutikken henter selv via /api/catalog.)
    weapons = [{"ref": f"weapons/{w['id']}", "name": w["name"], "group": w["category"],
                "cost_str": _format_cost(w.get("cost_cp"))}
               for w in db.get_all_weapons()]
    return {
        "races": GEN_RACES,
        "classes": GEN_CLASSES,
        "skills": db.get_all_skills(),
        "feats": all_feats,
        "bonus_feat_candidates": bonus_feat_candidates,
        "weapons": weapons,
        # Kun companion-egnede væsner i companion-vælgeren (companion_ok != 0).
        # Kataloget rummer også summon-kun-væsner (Summon Nature's Ally).
        "animals": [{"id": a["id"], "name": a["name"]} for a in db.get_all_animals()
                    if a.get("companion_ok") != 0],
        "domains": db.get_domains(GEN_DOMAINS),
        "races_json": races_json,
        "classes_json": classes_json,
        "feat_prereqs": {x["id"]: (x.get("prerequisites") or "") for x in all_feats},
        "feat_name_to_id": {x["name"].lower(): x["id"] for x in all_feats},
        "spell_schools": refdata.SPELL_SCHOOLS,
    }


def build_character_data(f) -> dict:
    """Valider generator-formularen og byg den rå karakter-data-dict (level 1).

    Rejser ValueError/KeyError ved ugyldigt input. Skriver intet og kender ikke
    til filer/slug/persistens -- det håndterer create_character-ruten i app.py.
    """
    name = f.get("name", "").strip()
    if not name:
        raise ValueError("Navn mangler.")
    race = f.get("race", "").strip()
    cls = f.get("cls", "").strip()
    if race not in GEN_RACES or cls not in GEN_CLASSES:
        raise ValueError("Ugyldig race eller klasse.")

    # Ability scores: basis-input → race-justering → endelige scores.
    base = {}
    for a in ("str", "dex", "con", "int", "wis", "cha"):
        iv = int(f.get(f"score_{a}", ""))
        if not 3 <= iv <= 20:
            raise ValueError(f"{a.upper()} skal være mellem 3 og 20 (før race).")
        base[a] = iv
    # Point-buy-metoden har sin egen validering (scores 8-18, budget 28).
    # 'free' og 'roll' bruger blot 3-20-grænsen ovenfor (rul er en JS-hjælper).
    if f.get("score_method", "free") == "pointbuy":
        cost = char_module.point_buy_total(base)
        if cost > char_module.POINT_BUY_BUDGET:
            raise ValueError(
                f"Point-buy: du brugte {cost} af {char_module.POINT_BUY_BUDGET} point.")
    final = char_module.apply_racial_adjustments(base, race)
    int_mod = (final["int"] - 10) // 2
    con_mod = (final["con"] - 10) // 2

    # Skills: budget = (klasse-basis + INT + racial bonus) × 4; klasse-skill cap 4
    # (cost 1), cross-class cap 2 (cost 2). Racial bonus (human: +1) kommer fra data.
    race_skill_bonus = char_module.race_data(race).get("skill_point_bonus_per_level", 0)
    budget = max(1, char_module.base_skill_points(cls) + int_mod
                 + race_skill_bonus) * 4
    cls_sk = char_module.class_skills(cls)
    spent, skills_out = 0, {}
    for s in db.get_all_skills():
        raw_v = f.get(f"skill_{s['id']}", "").strip()
        ranks = int(raw_v) if raw_v else 0
        if ranks <= 0:
            continue
        is_class = s["id"] in cls_sk
        cap = 4 if is_class else 2
        if ranks > cap:
            raise ValueError(f"{s['name']}: max {cap} ranks ved level 1.")
        spent += ranks * (1 if is_class else 2)
        skills_out[s["id"]] = {"id": s["id"], "ranks": float(ranks), "misc": 0}
    if spent > budget:
        raise ValueError(f"For mange skill points brugt ({spent} af {budget}).")
    # Racial skill-bonusser i misc (også på skills uden ranks).
    for sid, bonus in char_module.race_data(race).get("skill_bonuses", {}).items():
        if sid in skills_out:
            skills_out[sid]["misc"] += bonus
        else:
            skills_out[sid] = {"id": sid, "ranks": 0.0, "misc": bonus}

    # Feats: antal = 1 + race-bonus; klassens bonus-feats lægges til (Track).
    chosen = f.getlist("feats")
    need = char_module.level1_feat_count(race)
    if len(chosen) != need:
        raise ValueError(f"Vælg præcis {need} feat(s) — du valgte {len(chosen)}.")
    all_feats = db.get_all_feats()
    valid_feats = {x["id"] for x in all_feats}
    if any(x not in valid_feats for x in chosen):
        raise ValueError("Ukendt feat valgt.")
    # Fighter-bonus-feats: vælges fra fighter-puljen (type=Fighter), oveni de valgte.
    bonus_chosen = f.getlist("bonus_feats")
    bonus_need = char_module.class_bonus_feat_choices(cls)
    if len(bonus_chosen) != bonus_need:
        raise ValueError(
            f"Vælg præcis {bonus_need} bonus-feat(s) — du valgte {len(bonus_chosen)}.")
    if bonus_need:
        pool = set(_class_bonus_feat_ids(cls))
        if any(x not in pool for x in bonus_chosen):
            raise ValueError("Ugyldig bonus-feat valgt (ikke i klassens pulje).")
        if set(bonus_chosen) & set(chosen):
            raise ValueError("Samme feat valgt som både alm. feat og bonus-feat.")
    # Byg feat-poster: våben-feats gemmes som {id, weapon}, resten som id-streng.
    # Dedup på id (klassens gratis feats lægges efter de valgte).
    name_by_id = {x["id"]: x["name"] for x in all_feats}
    feats_out: list = []
    seen_ids: set[str] = set()
    weapon_names = {w["name"] for w in db.get_all_weapons()}
    for fid in chosen + bonus_chosen + char_module.class_bonus_feats(cls):
        if fid in seen_ids:
            continue
        seen_ids.add(fid)
        if fid in char_module.WEAPON_CHOICE_FEATS:
            # Våben kan komme fra alm. feat-sektion eller fighter-bonus-sektion.
            wpn = (f.get(f"feat_weapon_{fid}", "")
                   or f.get(f"bonus_feat_weapon_{fid}", "")).strip()
            if wpn not in weapon_names:
                raise ValueError(f"Vælg et gyldigt våben til {name_by_id.get(fid, fid)}.")
            feats_out.append({"id": fid, "weapon": wpn})
        elif fid in char_module.SCHOOL_CHOICE_FEATS:
            # Spell Focus m.fl.: vælg en troldskole (gemmes som {id, school}).
            school = (f.get(f"feat_school_{fid}", "")
                      or f.get(f"bonus_feat_school_{fid}", "")).strip()
            if school not in refdata.SPELL_SCHOOLS:
                raise ValueError(f"Vælg en gyldig troldskole til {name_by_id.get(fid, fid)}.")
            feats_out.append({"id": fid, "school": school})
        else:
            feats_out.append(fid)
    # Ejer-tokens inkl. kvalificerede labels ('spell focus (conjuration)'), så
    # navne-baserede prereqs (Augment Summoning) matcher det valgte.
    owned_tokens = char_module.owned_feat_tokens(feats_out, name_by_id)

    # Håndhæv feat-prerequisites (fx Augment Summoning kræver Spell Focus (Conjuration)).
    name_to_id = {x["name"].lower(): x["id"] for x in all_feats}
    prereq_by_id = {x["id"]: x.get("prerequisites") for x in all_feats}
    bab1 = int((db.get_class_level(cls.lower(), 1) or {}).get("bab", 0))
    # Monkens bonus-feat gives uden prereqs (SRD) → kun de alm. feats tjekkes for den.
    prereq_check = chosen if char_module.class_bonus_feat_ignore_prereqs(cls) else chosen + bonus_chosen
    for fid in prereq_check:
        missing = char_module.feat_prereq_unmet(
            prereq_by_id.get(fid) or "", owned_tokens, final, cls, 1, bab1, name_to_id)
        if missing:
            raise ValueError(f"{name_by_id.get(fid, fid)} kræver: {', '.join(missing)}.")

    # Domæner: cleric kræver præcis 2.
    domains = f.getlist("domains")
    if char_module.class_needs_domains(cls):
        valid_dom = {d["id"] for d in db.get_domains(GEN_DOMAINS)}
        if len(domains) != 2 or any(d not in valid_dom for d in domains):
            raise ValueError("En cleric skal vælge præcis 2 domæner.")
    else:
        domains = []

    # Sprog: automatiske (race + klasse) er gratis; antal bonussprog = Int-mod,
    # valgt fra race/klasse-puljen. Resultatet gemmes som én rå liste.
    auto_langs = char_module.automatic_languages(race, cls)
    pool = char_module.bonus_language_pool(race, cls)
    need_langs = char_module.bonus_language_count(int_mod)
    chosen_langs = [s.strip() for s in f.getlist("languages") if s.strip()]
    if len(chosen_langs) != need_langs:
        raise ValueError(f"Vælg præcis {need_langs} bonussprog (Int-mod {int_mod:+d}).")
    if len(set(chosen_langs)) != len(chosen_langs):
        raise ValueError("Samme bonussprog valgt flere gange.")
    if any(lang not in pool for lang in chosen_langs):
        raise ValueError("Ugyldigt bonussprog valgt.")
    languages = auto_langs + chosen_langs

    # Dyreledsager (valgfri, kun klasser med companion ved level 1 = druide).
    # Tynd reference: hp_current = beregnet max ved oprettelse; resten afledes.
    gen_companion = None
    animal_id = f.get("companion_animal", "").strip()
    if animal_id and companion_module.companion_effective_level(cls, 1) > 0:
        animal = db.get_animal(animal_id)
        if not animal:
            raise ValueError("Ukendt dyreledsager.")
        comp_name = f.get("companion_name", "").strip() or animal["name"]
        hp_max = companion_module.advance_companion(
            animal, companion_module.companion_deltas(1), db)["hp_max"]
        gen_companion = {"name": comp_name, "animal": animal_id,
                         "hp_current": hp_max, "tricks": []}

    # Udstyr fra udrustningsbutikken → forenet inventar (refs + tilstand).
    # Butikken afleverer valget i det skjulte felt 'equipment' som JSON:
    # en liste af {ref, category, qty}. Tilstanden udledes af kategorien
    # (rustning/skjold = worn, våben = wielded, øvrigt gear = backpack);
    # afledte angreb + AC + vægt udregnes derefter fra inventaret som før.
    inventory = _parse_equipment(f.get("equipment", ""))

    # Afledte rå-værdier (én gang, gemmes som rå data).
    cl1 = db.get_class_level(cls.lower(), 1) or {}
    hp = max(1, char_module.hit_die(cls) + con_mod)
    rd = char_module.race_data(race)
    raw_features = cl1.get("features") or []
    features = raw_features if isinstance(raw_features, list) else json.loads(raw_features)
    favored = f.get("favored_enemy", "").strip()
    class_features = {}
    for feat in features:
        if cls == "Ranger" and feat.endswith("Favored Enemy") and favored:
            class_features["Favored Enemy"] = (
                f"{favored} — +2 på Bluff/Listen/Sense Motive/Spot/Survival og +2 skade mod denne type")
        else:
            class_features[feat] = ""
    # Ranger combat style (vælges ved oprettelse, virker fra niveau 2). Two-Weapon
    # Combat ⇒ behandles som Two-Weapon Fighting i let/ingen rustning (se twf_context).
    if cls == "Ranger":
        style = f.get("combat_style", "").strip()
        if style:
            class_features["Combat Style"] = style

    gold = {k: int(f.get(f"gold_{k}", "") or 0) for k in ("pp", "gp", "sp", "cp")}
    combat = {"bab": int(cl1.get("bab", 0)),
              "speed": rd.get("speed", 30) + char_module.class_speed_bonus(cls)}

    data = {
        "name": name,
        "race": race,
        "class": cls,
        "level": 1,
        "alignment": f.get("alignment", "").strip(),
        "deity": f.get("deity", "").strip(),
        "gender": f.get("gender", "").strip(),
        "age": f.get("age", "").strip(),
        "height": f.get("height", "").strip(),
        "weight": f.get("weight", "").strip(),
        "size": rd.get("size", "medium"),
        "experience_points": 0,
        "hp": {"current": hp, "max": hp},
        "ability_scores": final,
        "saves": {"fortitude": int(cl1.get("fort", 0)),
                  "reflex": int(cl1.get("ref", 0)),
                  "will": int(cl1.get("will", 0))},
        "combat": combat,
        "attacks": [],
        "skills": list(skills_out.values()),
        "feats": feats_out,
        "conditions": [],
        "languages": languages,
        "spells_prepared": {},
        "spells_used": {},
        "inventory": inventory,
        "gold": gold,
        "class_features": class_features,
        "racial_traits": rd.get("traits", {}),
    }
    if domains:
        data["domains"] = domains
        data["domain_spells_prepared"] = {}
        data["domain_spells_used"] = {}
    if gen_companion:
        data["companion"] = gen_companion
    return data
