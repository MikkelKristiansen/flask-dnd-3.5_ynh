"""D&D 3.5 Flask-app — tablet-first karakterark."""
import io
import json
import os
import tempfile
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from ruamel.yaml import YAML
from werkzeug.middleware.proxy_fix import ProxyFix

import catalog
import character as char_module
import companion as companion_module
import db
import dice as dice_module
import effects
import refdata
import summon as summon_module
import wild_shape as wild_shape_module

from character_view import (build_character_view, _race_weapon_prof_ids,
                            _inv_row, _paladin_caps)
from paths import CHARACTERS_DIR, PORTRAITS_DIR, PORTRAIT_EXTS, _safe_slug
from portraits import _portrait_path, _validate_portrait, _write_portrait

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


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
# Karakterfiler er små (~få KB), men portræt-upload kan være et helt foto.
# 8 MB rummer rigeligt et almindeligt billede og holder stadig grænsen for store.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


def _char_path(slug: str) -> Path:
    return CHARACTERS_DIR / f"{slug}.yaml"


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


def _snapshots_for(slug: str) -> list[dict]:
    """Snapshots for en karakter til restore-UI'en — nyeste først, med læsbar dato.

    `is_current` sammenligner indhold med live-filen (ikke rækkefølge), så markeringen
    forbliver korrekt efter en restore, hvor den nuværende tilstand ikke nødvendigvis
    er det nyeste snapshot.
    """
    import datetime
    path = _char_path(slug)
    try:
        current = path.read_bytes()
    except OSError:
        current = None
    out = []
    for snap in reversed(char_module.list_snapshots(path)):
        try:
            ts = datetime.datetime.strptime(snap.stem, "%Y%m%d-%H%M%S-%f")
            label = ts.strftime("%-d. %b %Y, %H:%M:%S")
        except ValueError:
            label = snap.stem
        try:
            is_current = current is not None and snap.read_bytes() == current
        except OSError:
            is_current = False
        out.append({"file": snap.name, "label": label, "is_current": is_current})
    return out


# ── Pages ──────────────────────────────────────────────────────────────────

def _last_updated() -> str:
    import datetime
    try:
        mtime = Path(__file__).stat().st_mtime
        return datetime.datetime.fromtimestamp(mtime).strftime("%-d. %b %Y, %H:%M")
    except Exception:
        return "ukendt"


@app.route("/")
def index():
    files = sorted(CHARACTERS_DIR.glob("*.yaml"))
    chars = []
    for f in files:
        try:
            c   = char_module.load_character(str(f))
            ab  = c.ability_scores
            hp_pct = max(0, min(100, c.hp_current * 100 // c.hp_max)) if c.hp_max else 0
            xp_info = char_module.xp_progress(c.experience_points, c.level)
            enc = char_module.encumbrance_level(
                ab.str, char_module.carried_weight(c.inventory, db, c.size), c.size)
            chars.append({
                "slug":       f.stem,
                "name":       c.name,
                "race":       c.race,
                "cls":        c.cls,
                "level":      c.level,
                "hp_current": c.hp_current,
                "hp_max":     c.hp_max,
                "hp_pct":     hp_pct,
                "dead":       c.hp_current <= 0,
                "conditions": c.conditions,
                "xp_ready":   xp_info["ready"],
                "enc":        enc,
            })
        except Exception:
            chars.append({"slug": f.stem, "name": f.stem,
                          "race": "", "cls": "", "level": "?",
                          "hp_current": 0, "hp_max": 0, "hp_pct": 0,
                          "dead": False, "conditions": [], "xp_ready": False, "enc": ""})
    return render_template("index.html", chars=chars, last_updated=_last_updated(),
                           imported=request.args.get("imported"),
                           import_error=request.args.get("import_error"))


@app.route("/export/<slug>")
def export_character(slug):
    """Hent en karakters rå YAML som fil-download (off-box kopi)."""
    path = _char_path(slug)
    if not path.exists() or path.parent.resolve() != CHARACTERS_DIR.resolve():
        abort(404)
    return Response(
        path.read_bytes(),
        mimetype="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{slug}.yaml"'},
    )


@app.route("/import", methods=["POST"])
def import_character():
    """Importér en karakter-YAML fra brugerens disk.

    Validerer at filen rent faktisk kan loades som en karakter, før den skrives.
    Slug udledes af filnavnet (saniteret), med karakterens name som fallback.
    Overskriver en eksisterende karakter med samme slug — men kun efter et
    snapshot af den nuværende, så det kan fortrydes via Versioner.
    """
    file = request.files.get("file")
    if file is None or not file.filename:
        return redirect(url_for("index", import_error="Ingen fil valgt."))

    raw = file.read()

    # Valider: skal kunne loades som en rigtig karakter (ellers ville arket fejle).
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        char = char_module.load_character(tmp)
    except Exception as e:
        return redirect(url_for("index", import_error=f"Ugyldig karakterfil: {e}"))
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)

    slug = _safe_slug(Path(file.filename).stem) or _safe_slug(char.name)
    if not slug:
        return redirect(url_for("index", import_error="Kunne ikke udlede et navn fra filen."))

    overwrote = char_module.write_character_file(str(_char_path(slug)), raw)
    note = " (overskrev en eksisterende — tidligere version ligger under Versioner)" if overwrote else ""
    return redirect(url_for("index", imported=f"Importerede “{char.name}” som {slug}.yaml{note}"))


@app.route("/delete/<slug>", methods=["POST"])
def delete_character(slug):
    """Slet en karakter permanent: YAML-fil, snapshots og portræt.

    POST (ikke GET) så sletning ikke kan udløses ved et link-klik/prefetch.
    Stien valideres som i export_character, så et slug ikke kan pege uden for
    characters/. Bekræftelse sker i browseren (confirm-dialog på knappen).
    """
    path = _char_path(slug)
    if not path.exists() or path.parent.resolve() != CHARACTERS_DIR.resolve():
        abort(404)

    # Pænt navn til kvitteringen, hvis filen kan loades (ellers slug'et).
    try:
        name = char_module.load_character(str(path)).name
    except Exception:
        name = slug

    char_module.delete_character(str(path))
    portrait = _portrait_path(slug)
    if portrait is not None:
        portrait.unlink(missing_ok=True)

    return redirect(url_for("index", imported=f"Slettede “{name}”."))


# ── Karaktergenerator ───────────────────────────────────────────────────────

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


@app.route("/api/catalog")
def api_catalog():
    """Beriget udstyrs-katalog til udrustningsbutikken (UI tegnes ud fra dette).

    Tager parametre, IKKE en karakter — den bruges også under generering, hvor
    karakteren endnu ikke findes:
      cls   klasse-id → proficiency-flag + anbefalet-flag (valgfri)
      str   styrke-score → bæreevne-grænser (default 10)
      size  small/medium/large → størrelses-justeret vægt (default medium)
      race  race-id → ekstra våben-proficiency (fx elv: longsword) (valgfri)

    Python regner alle regel-afledte tal; JS lægger kun sammen. Se catalog.py.
    """
    cls = (request.args.get("cls") or "").strip()
    race = (request.args.get("race") or "").strip()
    size = (request.args.get("size") or "medium").strip().lower()
    try:
        str_score = int(request.args.get("str", 10))
    except (TypeError, ValueError):
        str_score = 10

    data = catalog.build_catalog(
        db,
        weapon_prof=refdata.class_weapon_proficiency(cls) if cls else None,
        armor_prof=refdata.class_armor_proficiency(cls) if cls else None,
        allowed_weapons=_race_weapon_prof_ids(race, db) if race else frozenset(),
        recommended_ids=refdata.starting_kit_ids(cls) if cls else frozenset(),
        str_score=str_score,
        size=size,
    )
    return jsonify(data)


@app.route("/dev/equipment-picker")
def dev_equipment_picker():
    """Isoleret dev-testside for udrustningsbutik-komponenten (kun i debug)."""
    if not app.debug:
        abort(404)
    return render_template("_equipment_picker_demo.html", classes=GEN_CLASSES)


@app.route("/create")
def create_form():
    return render_template("create.html", error=request.args.get("error"), **_gen_context())


@app.route("/create", methods=["POST"])
def create_character():
    """Byg en ny level-1-karakter fra formularen, valider mod reglerne og skriv YAML."""
    f = request.form
    try:
        # Valider et evt. portræt FØR vi skriver karakteren, så en ugyldig fil
        # afvises uden at efterlade en halvfærdig karakter.
        portrait_raw = _validate_portrait(request.files.get("portrait"))
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

        slug = _safe_slug(name)
        if not slug:
            raise ValueError("Kunne ikke udlede et filnavn fra navnet.")
        if _char_path(slug).exists():
            raise ValueError(f"En karakter med filnavnet {slug}.yaml findes allerede.")

        # Dump → valider via round-trip → skriv (atomar + snapshot).
        buf = io.StringIO()
        YAML().dump(data, buf)
        raw = buf.getvalue().encode("utf-8")
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".yaml")
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
            char_module.load_character(tmp)  # rejser ved ugyldig
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

        char_module.write_character_file(str(_char_path(slug)), raw)
        if portrait_raw is not None:
            _write_portrait(slug, portrait_raw)
    except (ValueError, KeyError) as e:
        return redirect(url_for("create_form", error=str(e)))

    return redirect(url_for("karakter", name=slug))


@app.route("/karakter/<name>")
def karakter(name):
    path = _char_path(name)
    if not path.exists():
        abort(404)
    char = char_module.load_character(str(path))
    portrait_path = _portrait_path(name)
    return render_template(
        "character.html",
        name=name,
        char=char,
        slug=name,
        snapshots=_snapshots_for(name),
        has_portrait=portrait_path is not None,
        # Ændringstidspunkt som cache-buster: URL'en skifter når billedet gør,
        # så browseren ikke viser et cachet gammelt portræt efter upload.
        portrait_ver=int(portrait_path.stat().st_mtime) if portrait_path else 0,
        **build_character_view(char, db),
    )


@app.route("/portrait/<slug>")
def portrait(slug):
    """Server karakterens portræt fra data-mappen (uden for Flasks static/)."""
    path = _portrait_path(slug)
    if path is None:
        abort(404)
    return send_from_directory(str(PORTRAITS_DIR), path.name)


@app.route("/api/portrait", methods=["POST"])
def api_portrait():
    """Skift/tilføj portræt på en eksisterende karakter (multipart-upload)."""
    slug = request.form.get("char", "")
    if not _char_path(slug).exists():
        return jsonify({"error": "not found"}), 404
    try:
        raw = _validate_portrait(request.files.get("portrait"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if raw is None:
        return jsonify({"error": "Ingen fil valgt."}), 400
    _write_portrait(slug, raw)
    return jsonify({"ok": True})


# ── API ────────────────────────────────────────────────────────────────────

@app.route("/api/hp", methods=["POST"])
def api_hp():
    data = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    # Midlertidigt HP (Virtue m.fl.) hæver loftet, så HP kan holdes over max.
    ceiling = char.hp_max + effects.temp_hp(char, db)
    new_hp = max(-20, min(ceiling, char.hp_current + delta))
    char_module.save_character(str(path), {"hp_current": new_hp})
    return jsonify({"hp_current": new_hp, "hp_max": char.hp_max})


@app.route("/api/spells", methods=["POST"])
def api_spells():
    data        = request.get_json()
    slug        = data.get("char")
    level       = int(data.get("level"))
    spell_index = int(data.get("spell_index", 0))
    mark_used   = bool(data.get("used"))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    spells_used = {k: list(v) for k, v in char.spells_used.items()}
    spells_active = {k: list(v) for k, v in char.spells_active.items()}
    spell_charges = dict(char.spell_charges)

    # Et slot der forlader "I brug" og bærer et væsen (direkte SNA-kast ELLER et
    # ofret spell) rydder det. is_sna styrer desuden reload (Kast-knappens synlighed).
    prepared = char.spells_prepared.get(level, [])
    is_sna = (0 <= spell_index < len(prepared)
              and prepared[spell_index].startswith("summon_natures_ally_"))
    bound_summon = _find_summon(char.summons, level, spell_index) is not None

    # Tre-tilstands-spells (self_duration) sender "state" = free|active|used.
    # To-tilstands-spells sender som før "used" = true/false.
    state = data.get("state")
    if state is not None:
        for d in (spells_used, spells_active):
            if level in d and spell_index in d[level]:
                d[level].remove(spell_index)
        key = char_module.spell_charge_key(level, spell_index)
        spell_charges.pop(key, None)
        if state == "active":
            spells_active.setdefault(level, []).append(spell_index)
            # Init ladninger fra kataloget (fx Magic Stone: 3 sten).
            sid = char.spells_prepared.get(level, [])
            if 0 <= spell_index < len(sid):
                maxc = char_module.spell_max_charges(sid[spell_index], db)
                if maxc:
                    spell_charges[key] = maxc
        elif state == "used":
            spells_used.setdefault(level, []).append(spell_index)
        # state == "free": fjernet fra begge ovenfor
        updates = {"spells_used": spells_used, "spells_active": spells_active,
                   "spell_charges": spell_charges}
        # Slot forlader "I brug" → fjern det bundne væsen (fanen forsvinder).
        if bound_summon and state != "active":
            summons = [s for s in char.summons
                       if not (s.get("spell_level") == level
                               and s.get("spell_index") == spell_index)]
            if len(summons) != len(char.summons):
                updates["summons"] = summons
        char_module.save_character(str(path), updates)
    else:
        if mark_used:
            spells_used.setdefault(level, [])
            if spell_index not in spells_used[level]:
                spells_used[level].append(spell_index)
        else:
            if level in spells_used and spell_index in spells_used[level]:
                spells_used[level].remove(spell_index)
        char_module.save_character(str(path), {"spells_used": spells_used})

    return jsonify({
        "spells_used": {str(k): v for k, v in spells_used.items()},
        "spells_active": {str(k): v for k, v in spells_active.items()},
        "spell_charges": spell_charges,
        # Reload hvis et SNA-spell (Kast-knap skifter) eller et væsen var bundet (fane).
        "is_summon": is_sna or bound_summon,
    })


@app.route("/api/spells_known", methods=["POST"])
def api_spells_known():
    """Lær eller glem et spell på en spontan casters kendte liste (sorcerer/bard)."""
    data     = request.get_json()
    slug     = data.get("char")
    action   = data.get("action")            # "add" | "remove"
    level    = int(data.get("level"))
    spell_id = str(data.get("spell_id", ""))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char  = char_module.load_character(str(path))
    known = {k: list(v) for k, v in char.spells_known.items()}
    lst   = known.setdefault(level, [])
    if action == "add" and spell_id and spell_id not in lst:
        lst.append(spell_id)
    elif action == "remove" and spell_id in lst:
        lst.remove(spell_id)
    char_module.save_character(str(path), {"spells_known": known})
    return jsonify({"ok": True, "spells_known": {str(k): v for k, v in known.items()}})


@app.route("/api/cast_known", methods=["POST"])
def api_cast_known():
    """Spontan caster: forbrug (+1) eller frigiv (−1) en slot af et niveau.

    Slot-loftet beregnes server-side ud fra klasse-level + caster-evne (klienten
    bestemmer ikke grænsen), så forbruget altid holder sig i [0, total]."""
    data  = request.get_json()
    slug  = data.get("char")
    level = int(data.get("level"))
    delta = int(data.get("delta", 1))        # +1 = kast, −1 = fortryd
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char    = char_module.load_character(str(path))
    cld     = db.get_class_level(char.cls.lower(), char.level)
    cast_ab = refdata.class_data(char.cls).get("cast_ability", "wis")
    total   = (char_module.spell_slots_total(
        cld, getattr(char.ability_scores, cast_ab)).get(level, 0) if cld else 0)
    used = dict(char.spells_known_used)
    used[level] = max(0, min(total, used.get(level, 0) + delta))
    char_module.save_character(str(path), {"spells_known_used": used})
    return jsonify({"ok": True, "level": level, "used": used[level], "total": total})


@app.route("/api/summon", methods=["POST"])
def api_summon():
    """Kast et Summon Nature's Ally-væsen — direkte eller ved spontant offer.

    To modes:
    - "cast": slot'et ER et forberedt SNA-spell, der sættes "I brug".
    - "sacrifice": slot'et er et hvilket som helst andet forberedt spell, der ofres
      til SNA af samme niveau (kun klasser med spontaneous_summon). Det ofrede slot
      sættes også "I brug" — så fanen lever, mens slot'et er optaget, og fjernes når
      det sættes "Brugt" (samme livscyklus som direkte kast; jf. /api/spells).

    Begge: SNA-niveau N = slot-niveauet. Augment Summoning snapshottes fra feats.
    HP sættes til fuld (hp_max pr. væsen). En tynd ref bindes til (spell_level=N,
    spell_index).
    """
    data        = request.get_json()
    slug        = data.get("char")
    mode        = data.get("mode", "cast")
    level       = int(data.get("level"))           # slot-niveau = SNA-niveau
    spell_index = int(data.get("spell_index", 0))
    creature    = (data.get("creature") or "").strip()
    count       = max(1, int(data.get("count") or 1))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))

    # Validér slot'et efter mode.
    prepared = char.spells_prepared.get(level, [])
    if not (0 <= spell_index < len(prepared)):
        return jsonify({"error": "ugyldigt slot"}), 400
    sid = prepared[spell_index]
    if mode == "sacrifice":
        if not refdata.class_data(char.cls).get("spontaneous_summon"):
            return jsonify({"error": "klassen kan ikke spontant summone"}), 400
        if sid.startswith("summon_natures_ally_"):
            return jsonify({"error": "brug Kast på selve SNA-spellet"}), 400
    elif not sid.startswith("summon_natures_ally_"):
        return jsonify({"error": "ikke et SNA-spell"}), 400
    if spell_index in char.spells_active.get(level, []) or \
            spell_index in char.spells_used.get(level, []):
        return jsonify({"error": "spell allerede brugt"}), 400

    # Validér: væsenet hører til denne SNA-niveau-liste.
    if creature not in refdata.summon_creatures(level):
        return jsonify({"error": "ugyldigt væsen"}), 400

    # Augment Summoning-snapshot fra karakterens feats (+4 Str/+4 Con på væsenet).
    augment = any(char_module.feat_id(e) == "augment_summoning" for e in char.feats)

    # Byg statblokken én gang for at få hp_max → fuld HP pr. væsen ved kast.
    ref = {"creature": creature, "spell_level": level, "spell_index": spell_index,
           "count": count, "augment": augment}
    stat = summon_module.build_summon(ref, db)
    if not stat:
        return jsonify({"error": "ugyldigt væsen"}), 400
    ref["hp_current"] = [stat["hp_max"]] * count

    # Sæt SNA-spellet "I brug" (samme mekanik som cycleSpell → state=active).
    spells_active = {k: list(v) for k, v in char.spells_active.items()}
    spells_used   = {k: list(v) for k, v in char.spells_used.items()}
    spells_active.setdefault(level, []).append(spell_index)

    # Append summon-ref og gem hele summons-listen + spell-tilstanden.
    summons = list(char.summons) + [ref]
    char_module.save_character(str(path), {
        "summons": summons,
        "spells_active": spells_active,
        "spells_used": spells_used,
    })
    return jsonify({"ok": True})


def _find_summon(summons: list, level: int, index: int) -> dict | None:
    """Find summon-ref'en for SNA-slot'et (spell_level, spell_index) — eller None."""
    for s in summons:
        if s.get("spell_level") == level and s.get("spell_index") == index:
            return s
    return None


@app.route("/api/summon_hp", methods=["POST"])
def api_summon_hp():
    """Justér HP for ÉT væsen i et summon (identificeret af SNA-slot + væsen-index).

    Spejler /api/companion_hp, men summons har en HP-liste (ét tal pr. count).
    Gemmer hele summons-listen (Fase 2's summons-nøgle).
    """
    data     = request.get_json()
    slug     = data.get("char")
    level    = int(data.get("spell_level"))
    index    = int(data.get("spell_index"))
    creature = int(data.get("creature_index", 0))
    delta    = int(data.get("delta", 0))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    ref = _find_summon(char.summons, level, index)
    if not ref:
        return jsonify({"error": "no summon"}), 400
    stat = summon_module.build_summon(ref, db)
    if not stat:
        return jsonify({"error": "no summon"}), 400
    hp_max = stat["hp_max"]
    hp_list = list(stat["hp_current"])      # resolveret liste (ét tal pr. væsen)
    if not (0 <= creature < len(hp_list)):
        return jsonify({"error": "bad creature index"}), 400
    hp_list[creature] = max(-9, min(hp_max, hp_list[creature] + delta))
    ref["hp_current"] = hp_list
    char_module.save_character(str(path), {"summons": char.summons})
    return jsonify({"hp_current": hp_list, "hp_max": hp_max, "creature_index": creature})


@app.route("/api/spell_charge", methods=["POST"])
def api_spell_charge():
    """Tæl en spells ladninger op/ned (Magic Stone: brug en sten).

    Rammer ladningerne 0, er spellen opbrugt → flyt fra "I brug" til "Brugt".
    """
    data        = request.get_json()
    slug        = data.get("char")
    level       = int(data.get("level"))
    spell_index = int(data.get("spell_index", 0))
    delta       = int(data.get("delta", -1))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    spells_used = {k: list(v) for k, v in char.spells_used.items()}
    spells_active = {k: list(v) for k, v in char.spells_active.items()}
    spell_charges = dict(char.spell_charges)
    key = char_module.spell_charge_key(level, spell_index)

    new = max(0, spell_charges.get(key, 0) + delta)
    if new <= 0:
        # Opbrugt → ladning væk, spell fra "I brug" til "Brugt".
        spell_charges.pop(key, None)
        if level in spells_active and spell_index in spells_active[level]:
            spells_active[level].remove(spell_index)
        spells_used.setdefault(level, [])
        if spell_index not in spells_used[level]:
            spells_used[level].append(spell_index)
    else:
        spell_charges[key] = new

    char_module.save_character(
        str(path), {"spells_used": spells_used, "spells_active": spells_active,
                    "spell_charges": spell_charges})
    return jsonify({
        "spells_used": {str(k): v for k, v in spells_used.items()},
        "spells_active": {str(k): v for k, v in spells_active.items()},
        "spell_charges": spell_charges,
    })


@app.route("/api/conditions", methods=["POST"])
def api_conditions():
    data         = request.get_json()
    slug         = data.get("char")
    condition_id = data.get("condition_id")
    action       = data.get("action")   # "add" | "remove"
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    target = data.get("target", "character")
    char = char_module.load_character(str(path))

    # Summon: muter tilstands-listen på den summon-ref der matcher SNA-slot'et.
    if target == "summon":
        ref = _find_summon(char.summons,
                           int(data.get("spell_level")), int(data.get("spell_index")))
        if not ref:
            return jsonify({"error": "no summon"}), 400
        conditions = list(ref.get("conditions") or [])
        if action == "add" and condition_id and condition_id not in conditions:
            conditions.append(condition_id)
        elif action == "remove" and condition_id in conditions:
            conditions.remove(condition_id)
        ref["conditions"] = conditions
        char_module.save_character(str(path), {"summons": char.summons})
        return jsonify({"conditions": conditions})

    if target == "companion":
        comp = char.companion or {}
        if not comp:
            return jsonify({"error": "no companion"}), 400
        conditions = list(comp.get("conditions") or [])
    else:
        conditions = list(char.conditions)

    if action == "add" and condition_id and condition_id not in conditions:
        conditions.append(condition_id)
    elif action == "remove" and condition_id in conditions:
        conditions.remove(condition_id)

    key = "companion_conditions" if target == "companion" else "conditions"
    char_module.save_character(str(path), {key: conditions})
    return jsonify({"conditions": conditions})


@app.route("/api/buffs", methods=["POST"])
def api_buffs():
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")           # "add" | "remove"
    target = data.get("target", "character")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    ref = None
    if target == "summon":
        ref = _find_summon(char.summons,
                           int(data.get("spell_level")), int(data.get("spell_index")))
        if not ref:
            return jsonify({"error": "no summon"}), 400
        buffs = list(ref.get("buffs") or [])
    elif target == "companion":
        comp = char.companion or {}
        if not comp:
            return jsonify({"error": "no companion"}), 400
        buffs = list(comp.get("buffs") or [])
    else:
        buffs = list(char.buffs)

    if action == "add":
        b = data.get("buff") or {}
        name = str(b.get("name", "")).strip()
        if name:
            entry = {"name": name, "note": str(b.get("note", "")).strip(),
                     "affects": [str(a) for a in (b.get("affects") or [])]}
            if b.get("spell_id"):
                entry["spell_id"] = str(b["spell_id"])
            # value-override (fx valgt ability-skade) — bæres med så modifieren
            # kan slås op med den faktiske mængde. Kun gem hvis den er et tal.
            if b.get("value") is not None:
                try:
                    entry["value"] = int(b["value"])
                except (TypeError, ValueError):
                    pass
            buffs.append(entry)
    elif action == "remove":
        i = int(data.get("index", -1))
        if 0 <= i < len(buffs):
            buffs.pop(i)

    if target == "summon":
        ref["buffs"] = buffs
        char_module.save_character(str(path), {"summons": char.summons})
    else:
        key = "companion_buffs" if target == "companion" else "buffs"
        char_module.save_character(str(path), {key: buffs})
    return jsonify({"ok": True})


@app.route("/api/roll/<path:expression>")
def api_roll(expression):
    try:
        result = dice_module.roll(expression)
        result["expression"] = expression
        # Valgfrit gulv (3.5: et succesfuldt angreb giver mindst 1 i skade).
        # Kun relevant for skade-rul — almindelige rul sender ingen min.
        minimum = request.args.get("min", type=int)
        if minimum is not None and result["total"] < minimum:
            result["total"] = minimum
            result["floored"] = True
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/xp", methods=["POST"])
def api_xp():
    data  = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char   = char_module.load_character(str(path))
    new_xp = max(0, char.experience_points + delta)
    char_module.save_character(str(path), {"experience_points": new_xp})
    return jsonify({
        "experience_points": new_xp,
        "xp_info": char_module.xp_progress(new_xp, char.level),
    })


@app.route("/api/levelup", methods=["POST"])
def api_levelup():
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if not char_module.xp_progress(char.experience_points, char.level)["ready"]:
        return jsonify({"error": "not ready"}), 400

    con_mod   = char.ability_scores.modifier("con")
    hp_roll   = max(1, int(data.get("hp_roll", 1)))
    hp_gained = max(1, hp_roll + con_mod)
    skill_deltas  = {k: float(v) for k, v in (data.get("skill_deltas") or {}).items()}
    new_feat      = data.get("new_feat") or None
    ability_boost = data.get("ability_boost") or None
    new_level     = char.level + 1

    char_module.save_character(str(path), {
        "level":         new_level,
        "hp_max":        char.hp_max + hp_gained,
        "hp_current":    char.hp_current + hp_gained,
        "skill_deltas":  skill_deltas,
        "new_feat":      new_feat,
        "ability_boost": ability_boost,
    })
    return jsonify({"ok": True, "new_level": new_level, "hp_gained": hp_gained})


def _armor_slot(item, db) -> str | None:
    """'body' for en krops-rustning, 'shield' for et skjold, ellers None."""
    if not item.ref.startswith("armor/"):
        return None
    rec = db.get_armor(item.ref.split("/", 1)[1])
    if not rec:
        return None
    return "shield" if rec.get("type") == "shield" else "body"


def _enforce_armor_slots(inventory, idx, db) -> None:
    """Hård slot-håndhævelse: kun én worn krops-rustning + ét worn skjold ad gangen.

    Når post idx sættes til 'worn', flyttes enhver anden worn rustning i SAMME slot
    (body/shield) tilbage til 'backpack'. Så opstår der aldrig en ulovlig tilstand
    med to bårne rustninger — i tråd med "kun lovlige kombinationer giver lovlige tal".
    """
    item = inventory[idx]
    if item.state != "worn":
        return
    slot = _armor_slot(item, db)
    if slot is None:
        return
    for j, other in enumerate(inventory):
        if j != idx and other.state == "worn" and _armor_slot(other, db) == slot:
            other.state = "backpack"


@app.route("/api/inventory", methods=["POST"])
def api_inventory():
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")   # "add" | "remove"
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char      = char_module.load_character(str(path))
    inventory = list(char.inventory)

    if action == "add":
        ref   = str(data.get("ref", "")).strip()
        state = str(data.get("state", "backpack")).lower()
        if state not in char_module.INVENTORY_STATES:
            state = "backpack"
        if ref:
            # Katalog-genstand: navn/vægt slås op via ref ved visning
            sm = data.get("str_mult")
            kwargs = dict(
                ref=ref, state=state,
                qty=max(1, int(data.get("qty", 1))),
                bonus=int(data.get("bonus", 0)),
                str_mult=(None if sm in (None, "") else float(sm)),
                notes=str(data.get("notes", "")),
            )
            # Materiale-/kvalitets-mods fra butikken (masterwork/cold iron/sølv) →
            # ekstra felter (masterwork-flag, +1 til-hit, materiale-mærkat i navn).
            table, _, oid = ref.partition("/")
            getter = {"weapons": db.get_weapon, "armor": db.get_armor}.get(table)
            record = getter(oid) if getter else None
            if record:
                kwargs.update(catalog.apply_material_overlay(record, table, data.get("mods")))
            inventory.append(char_module.InventoryItem(**kwargs))
            _enforce_armor_slots(inventory, len(inventory) - 1, db)
        else:
            name = str(data.get("name", "")).strip()
            if not name:
                return jsonify({"error": "name required"}), 400
            inventory.append(char_module.InventoryItem(
                name=name,
                weight=float(data.get("weight", 0)),
                qty=max(1, int(data.get("qty", 1))),
                notes=str(data.get("notes", "")),
                state=state,
            ))
    elif action == "remove":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(inventory):
            inventory.pop(idx)
    elif action == "update":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(inventory):
            old = inventory[idx]
            # Bevar katalog-ref; navn/vægt redigeres kun for custom.
            # qty kan gå til 0 (fx ammo brugt op); ingen negative.
            old.qty   = max(0, int(data.get("qty", old.qty)))
            old.notes = str(data.get("notes", old.notes))
            if "state" in data:
                st = str(data["state"]).lower()
                if st in char_module.INVENTORY_STATES:
                    old.state = st
                    _enforce_armor_slots(inventory, idx, db)
            if "off_hand" in data:
                old.off_hand = bool(data.get("off_hand"))
            if "double" in data:
                old.double = bool(data.get("double"))
            if "bonus" in data:
                old.bonus = int(data.get("bonus") or 0)
            if "str_mult" in data:
                sm = data.get("str_mult")
                old.str_mult = None if sm in (None, "") else float(sm)
            if "masterwork" in data:
                old.masterwork = bool(data.get("masterwork"))
            if "enhancement" in data:
                old.enhancement = int(data.get("enhancement") or 0)
            if "house_rule" in data:
                old.house_rule = bool(data.get("house_rule"))
            if not old.ref:
                old.name   = str(data.get("name", old.name))
                old.weight = float(data.get("weight", old.weight))

    char_module.save_character(str(path), {"inventory": inventory})
    ab     = char.ability_scores
    weight = char_module.carried_weight(inventory, db, char.size)
    enc    = char_module.encumbrance_level(ab.str, weight, char.size)
    inv_rows = [_inv_row(i, char_module.resolve_item(i, db, char.size))
               for i in inventory]
    return jsonify({
        "inventory":  inv_rows,
        "weight":     weight,
        "enc":        enc,
        "enc_limits": char_module.carry_limits(ab.str, char.size),
    })


_ATTACK_KINDS = {"melee", "ranged", "melee_touch", "ranged_touch"}


def _build_attack(a: dict) -> char_module.Attack:
    """Byg et Attack-objekt fra rå modal-data. Kilde styrer skade-modellen:
    spell → fast skade (Str tælles ikke med); våben → terning + Str×mult.
    """
    name = str(a.get("name", "")).strip()
    if not name:
        raise ValueError("name required")
    source = str(a.get("source", "weapon")).lower()
    if source != "spell":
        source = "weapon"
    kind = str(a.get("kind", "melee")).lower()
    if kind not in _ATTACK_KINDS:
        kind = "melee"
    damage = str(a.get("damage", "")).strip()
    common = dict(
        name=name, kind=kind, bonus=int(a.get("bonus") or 0),
        crit=(str(a.get("crit", "")).strip() or "x2"),
        type=str(a.get("type", "")).strip(),
        range=str(a.get("range", "")).strip(),
    )
    if source == "spell":
        return char_module.Attack(
            base_damage="1d4", str_damage_mult=0.0, fixed_damage=damage,
            source="spell", requires=str(a.get("requires", "")).strip(), **common)
    sm = a.get("str_mult")
    sm = 1.0 if sm in (None, "") else float(sm)
    return char_module.Attack(
        base_damage=(damage or "1d4"), str_damage_mult=sm, fixed_damage="",
        source="weapon", requires="", **common)


@app.route("/api/attacks", methods=["POST"])
def api_attacks():
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")        # "add" | "update" | "remove"
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char    = char_module.load_character(str(path))
    attacks = list(char.attacks)

    if action in ("add", "update"):
        try:
            atk = _build_attack(data.get("attack") or {})
        except (ValueError, TypeError):
            return jsonify({"error": "ugyldigt angreb"}), 400
        if action == "add":
            attacks.append(atk)
        else:
            idx = int(data.get("index", -1))
            if 0 <= idx < len(attacks):
                attacks[idx] = atk
    elif action == "remove":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(attacks):
            attacks.pop(idx)

    char_module.save_character(str(path), {"attacks": attacks})
    return jsonify({"ok": True})


@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    data = request.get_json()
    slug     = data.get("char")
    prepared = data.get("prepared_spells", {})   # {level_str: [spell_ids]}
    domain   = data.get("domain_prepared", {})   # {level_str: spell_id}
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    prepared_int = {int(k): list(v) for k, v in prepared.items()}
    domain_int = {int(k): str(v) for k, v in domain.items() if v}
    char_module.save_character(str(path), {
        "spells_prepared": prepared_int,
        "spells_used": {},          # ny forberedelse nulstiller brug
        "domain_spells_prepared": domain_int,
        "domain_spells_used": {},   # ny forberedelse nulstiller domæne-brug
    })
    return jsonify({
        "ok": True,
        "prepared_spells": {str(k): v for k, v in prepared_int.items()},
        "domain_prepared": {str(k): v for k, v in domain_int.items()},
    })


@app.route("/api/domain_used", methods=["POST"])
def api_domain_used():
    data  = request.get_json()
    slug  = data.get("char")
    level = int(data.get("level", 0))
    used  = bool(data.get("used", False))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    domain_used = dict(char.domain_spells_used)
    domain_used[level] = used
    char_module.save_character(str(path), {"domain_spells_used": domain_used})
    return jsonify({"ok": True, "domain_spells_used": {str(k): v for k, v in domain_used.items()}})


@app.route("/api/newday", methods=["POST"])
def api_newday():
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char_module.save_character(
        str(path),
        {"spells_used": {}, "spells_active": {}, "spell_charges": {},
         "spells_known_used": {}, "domain_spells_used": {}, "wild_shape": {},
         "lay_on_hands_used": 0, "smite_used": 0})
    return jsonify({"ok": True})


@app.route("/api/paladin", methods=["POST"])
def api_paladin():
    """Paladin-ressourcer: brug en Smite Evil eller helbred dig selv med Lay on Hands.

    Caps genberegnes server-side ud fra effektiv Cha + level (klienten bestemmer ikke
    grænserne). Lay on Hands helbreder paladinen selv (den eneste karakter arket kender)
    og trækker fra dagens pulje. Nulstilles ved "Ny dag".
    """
    data = request.get_json()
    slug = data.get("char")
    action = data.get("action")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if char.cls != "Paladin":
        return jsonify({"error": "ikke en paladin"}), 400

    active_modifiers, _ = effects.collect_character_effects(char, db)
    eff = char_module.effective_ability_scores(char.ability_scores, active_modifiers)
    lay_pool, smite_per_day = _paladin_caps(char, eff.modifier("cha"))

    if action == "smite":
        new_used = min(smite_per_day, char.smite_used + 1)
        char_module.save_character(str(path), {"smite_used": new_used})
        return jsonify({"ok": True, "smite_remaining": max(0, smite_per_day - new_used)})

    if action == "lay_on_hands":
        remaining = max(0, lay_pool - char.lay_on_hands_used)
        amount = max(0, min(int(data.get("amount", 0)), remaining))
        if amount <= 0:
            return jsonify({"error": "ingen pulje tilbage"}), 400
        new_used = char.lay_on_hands_used + amount
        ceiling = char.hp_max + effects.temp_hp(char, db)
        new_hp = min(ceiling, char.hp_current + amount)
        char_module.save_character(
            str(path), {"lay_on_hands_used": new_used, "hp_current": new_hp})
        return jsonify({"ok": True, "lay_remaining": max(0, lay_pool - new_used),
                        "hp_current": new_hp, "hp_max": char.hp_max})

    return jsonify({"error": "ukendt handling"}), 400


@app.route("/api/companion_hp", methods=["POST"])
def api_companion_hp():
    data  = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    comp = companion_module.build_companion(char, db)
    if not comp:
        return jsonify({"error": "no companion"}), 400
    hp_max = comp["hp_max"]
    hp_cur = comp["hp_current"]
    new_hp = max(-9, min(hp_max, hp_cur + delta))
    char_module.save_character(str(path), {"companion_hp_current": new_hp})
    return jsonify({"hp_current": new_hp, "hp_max": hp_max})


@app.route("/api/companion_tricks", methods=["POST"])
def api_companion_tricks():
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if not char.companion:
        return jsonify({"error": "no companion"}), 400
    # Normalisér: trim, fjern tomme, bevar rækkefølge, dedupér.
    seen, tricks = set(), []
    for t in (data.get("tricks") or []):
        name = str(t).strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            tricks.append(name)
    char_module.save_character(str(path), {"companion_tricks": tricks})
    return jsonify({"tricks": tricks})


@app.route("/api/companion", methods=["POST"])
def api_companion():
    """Tilkald en ny animal companion (summon) eller sig farvel til den (dismiss).

    summon: bygger en tynd ref {name, animal, hp_current=max, tricks:[]} ved
    karakterens effektive companion-niveau (samme mekanik som generatoren).
    dismiss: rydder char.companion helt (data går tabt — bekræftes i UI'en).
    """
    data   = request.get_json()
    slug   = data.get("char")
    action = str(data.get("action", "")).lower()
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    is_mount = companion_module.mount_eligible(char.cls, char.level)
    eff_level = companion_module.companion_effective_level(char.cls, char.level)
    if not is_mount and eff_level <= 0:
        return jsonify({"error": "Klassen kan ikke have en ledsager."}), 400

    if action == "dismiss":
        char_module.save_character(str(path), {"companion": {}})
        return jsonify({"ok": True})

    if action == "summon":
        animal_id = str(data.get("animal", "")).strip()
        animal = db.get_animal(animal_id)
        if is_mount:
            # Paladin-mount: kun de to standard-mounts, og statblok via mount-tabellen.
            if not animal or animal_id not in ("heavy_warhorse", "warpony"):
                return jsonify({"error": "Ukendt eller uegnet mount."}), 400
            deltas = companion_module.mount_deltas(char.level)
            kind = "mount"
        else:
            if not animal or animal.get("companion_ok") == 0:
                return jsonify({"error": "Ukendt eller uegnet dyr."}), 400
            deltas = companion_module.companion_deltas(max(1, eff_level))
            kind = "companion"
        name   = str(data.get("name", "")).strip() or animal["name"]
        hp_max = companion_module.advance_companion(animal, deltas, db)["hp_max"]
        comp = {"name": name, "animal": animal_id, "hp_current": hp_max, "tricks": []}
        if kind == "mount":
            comp["kind"] = "mount"
        char_module.save_character(str(path), {"companion": comp})
        return jsonify({"ok": True})

    return jsonify({"error": "ukendt action"}), 400


@app.route("/api/wild_shape", methods=["POST"])
def api_wild_shape():
    """Skift til en wild shape-form (shape) eller tilbage til egen form (revert).

    shape: validér at klassen har wild shape ved niveauet, at formen er lovlig
    (type/størrelse/HD≤niveau) og at der er en use tilbage (animal eller elemental).
    Bruger en use, sætter current_form, og heler HP = niveau (en nats hvile, RAW).
    revert: rydder current_form (forbrugte uses bevares — de er brugt for dagen).
    """
    data   = request.get_json()
    slug   = data.get("char")
    action = str(data.get("action", "")).lower()
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    ws_data = char_module.class_wild_shape(char.cls)
    info = wild_shape_module.wild_shape_info(ws_data, char.level, char.feats)
    if not info:
        return jsonify({"error": "Klassen har ikke wild shape endnu."}), 400

    state = dict(char.wild_shape or {})

    if action == "revert":
        state["current_form"] = ""
        state["active_abilities"] = []   # form forlades → aktive evner (Rage) ender
        char_module.save_character(str(path), {"wild_shape": state})
        return jsonify({"ok": True})

    if action == "toggle_ability":
        if not state.get("current_form"):
            return jsonify({"error": "Ikke i en form."}), 400
        ability = str(data.get("ability", "")).strip()
        form = wild_shape_module.build_wild_shape_form(char, ws_data, db)
        activatable = {a["slug"] for a in form["natural_abilities"]["gained"]
                       if a.get("activatable")}
        if ability not in activatable:
            return jsonify({"error": "Evnen kan ikke aktiveres i denne form."}), 400
        active = list(state.get("active_abilities") or [])
        if ability in active:
            active.remove(ability)
        else:
            active.append(ability)
        state["active_abilities"] = active
        char_module.save_character(str(path), {"wild_shape": state})
        return jsonify({"ok": True, "active": ability in active})

    if action == "shape":
        form_id = str(data.get("form", "")).strip()
        eligible = {f["id"] for f in wild_shape_module.eligible_forms(info, char.level, db)}
        if form_id not in eligible:
            return jsonify({"error": "Ulovlig form (type/størrelse/HD)."}), 400
        animal = db.get_animal(form_id)
        is_elemental = (animal.get("type") == "elemental")
        used_key = "elemental_used" if is_elemental else "animal_used"
        cap = info["elemental_uses"] if is_elemental else info["animal_uses"]
        if int(state.get(used_key, 0)) >= cap:
            kind = "elemental" if is_elemental else "animal"
            return jsonify({"error": f"Ingen {kind}-uses tilbage i dag."}), 400
        state[used_key] = int(state.get(used_key, 0)) + 1
        state["current_form"] = form_id
        state["active_abilities"] = []   # ny form starter uden aktive evner
        # Heal HP = niveau (en nats hvile) ved hvert wild shape, RAW.
        new_hp = min(char.hp_max, char.hp_current + char.level)
        char_module.save_character(str(path), {"wild_shape": state, "hp_current": new_hp})
        return jsonify({"ok": True})

    return jsonify({"error": "ukendt action"}), 400


@app.route("/api/gold", methods=["POST"])
def api_gold():
    data = request.get_json()
    slug = data.get("char")
    coin = data.get("coin")
    val  = int(data.get("value", 0))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    gold = dict(char.gold)
    gold[coin] = max(0, val)
    char_module.save_character(str(path), {"gold": gold})
    return jsonify({"gold": gold})


@app.route("/api/notes", methods=["POST"])
def api_notes():
    data  = request.get_json()
    slug  = data.get("char")
    notes = str(data.get("notes", ""))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char_module.save_character(str(path), {"notes": notes})
    return jsonify({"ok": True})


@app.route("/api/restore", methods=["POST"])
def api_restore():
    data     = request.get_json()
    slug     = data.get("char")
    snapshot = str(data.get("snapshot", ""))
    path     = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    # Tillad kun et navn der faktisk er et snapshot for DENNE karakter (ingen path traversal).
    valid = {s.name for s in char_module.list_snapshots(path)}
    if snapshot not in valid:
        return jsonify({"error": "ukendt snapshot"}), 400
    char_module.restore_snapshot(str(path), snapshot)
    return jsonify({"ok": True})


@app.route("/api/detail/<dtype>/<did>")
def api_detail(dtype, did):
    lookup = {"spell": db.get_spell, "skill": db.get_skill,
              "feat": db.get_feat, "condition": db.get_condition,
              "weapon": db.get_weapon, "armor": db.get_armor, "item": db.get_item,
              "ability": db.get_special_ability}
    fn = lookup.get(dtype)
    if not fn:
        return jsonify({"error": "unknown type"}), 400
    row = fn(did)
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
