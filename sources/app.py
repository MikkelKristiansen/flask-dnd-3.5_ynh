"""D&D 3.5 Flask-app — tablet-first karakterark."""
import io
import json
import os
import re
import tempfile
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from ruamel.yaml import YAML
from werkzeug.middleware.proxy_fix import ProxyFix

import character as char_module
import companion as companion_module
import db
import dice as dice_module

# Klasser/racer generatoren understøtter (v1: de motoren er bevist mod + ranger).
GEN_CLASSES = ["Cleric", "Druid", "Ranger"]
GEN_RACES = ["Human", "Elf", "Gnome"]
GEN_DOMAINS = ["healing", "protection", "war", "knowledge", "good", "luck"]

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
# Karakterfiler er små (~få KB) — en beskeden grænse beskytter import-ruten.
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024
CHARACTERS_DIR = Path(os.environ.get("DND_CHARACTERS_DIR",
                                     str(Path(__file__).parent / "characters")))
# Portrætter lægges manuelt i data-mappen (ved siden af characters/), ikke i
# sources/static/ som overskrives ved upgrade. Konvention: portraits/<slug>.<ext>.
PORTRAITS_DIR = CHARACTERS_DIR.parent / "portraits"
PORTRAIT_EXTS = ("jpg", "jpeg", "png", "webp")


def _char_path(slug: str) -> Path:
    return CHARACTERS_DIR / f"{slug}.yaml"


def _portrait_path(slug: str) -> Path | None:
    """Find karakterens portrætfil i data-mappen, hvis en findes (slug.<ext>)."""
    safe = _safe_slug(slug)
    if not safe:
        return None
    for ext in PORTRAIT_EXTS:
        p = PORTRAITS_DIR / f"{safe}.{ext}"
        if p.exists():
            return p
    return None


def _safe_slug(text: str) -> str:
    """Saniter til et filsikkert slug: kun a-z, 0-9, bindestreg og underscore."""
    return re.sub(r"[^a-z0-9_-]+", "-", str(text).strip().lower()).strip("-")


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


# ── Karaktergenerator ───────────────────────────────────────────────────────

def _gen_context() -> dict:
    """Data til generatorformularen (klasse/race-lister + regel-data til JS)."""
    races_json = {
        r.lower(): {
            "ability_adjust": char_module.race_data(r).get("ability_adjust", {}),
            "skill_bonuses": char_module.race_data(r).get("skill_bonuses", {}),
            "size": char_module.race_data(r).get("size", "medium"),
            "speed": char_module.race_data(r).get("speed", 30),
            "feat_count": char_module.level1_feat_count(r),
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
            "bab1": int((db.get_class_level(c.lower(), 1) or {}).get("bab", 0)),
            "turn_undead": char_module.class_can_turn_undead(c),
            # Companion ved level 1 (kun druide; ranger får først ved level 4).
            "has_companion": companion_module.companion_effective_level(c, 1) > 0,
        }
        for c in GEN_CLASSES
    }
    all_feats = db.get_all_feats()
    armor = db.get_all_armor()
    weapons = [{"ref": f"weapons/{w['id']}", "name": w["name"], "group": w["category"]}
               for w in db.get_all_weapons()]
    return {
        "races": GEN_RACES,
        "classes": GEN_CLASSES,
        "skills": db.get_all_skills(),
        "feats": all_feats,
        "armors": [a for a in armor if a.get("type") != "shield"],
        "shields": [a for a in armor if a.get("type") == "shield"],
        "weapons": weapons,
        "animals": [{"id": a["id"], "name": a["name"]} for a in db.get_all_animals()],
        "domains": db.get_domains(GEN_DOMAINS),
        "races_json": races_json,
        "classes_json": classes_json,
        "feat_prereqs": {x["id"]: (x.get("prerequisites") or "") for x in all_feats},
        "feat_name_to_id": {x["name"].lower(): x["id"] for x in all_feats},
    }


@app.route("/create")
def create_form():
    return render_template("create.html", error=request.args.get("error"), **_gen_context())


@app.route("/create", methods=["POST"])
def create_character():
    """Byg en ny level-1-karakter fra formularen, valider mod reglerne og skriv YAML."""
    f = request.form
    try:
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
        final = char_module.apply_racial_adjustments(base, race)
        int_mod = (final["int"] - 10) // 2
        con_mod = (final["con"] - 10) // 2

        # Skills: budget = (klasse-basis + INT + human) × 4; klasse-skill cap 4 (cost 1),
        # cross-class cap 2 (cost 2).
        budget = max(1, char_module.base_skill_points(cls) + int_mod
                     + (1 if race == "Human" else 0)) * 4
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
        feats_out = list(dict.fromkeys(chosen + char_module.class_bonus_feats(cls)))

        # Håndhæv feat-prerequisites (fx Augment Summoning kræver Spell Focus (Conjuration)).
        name_to_id = {x["name"].lower(): x["id"] for x in all_feats}
        prereq_by_id = {x["id"]: x.get("prerequisites") for x in all_feats}
        name_by_id = {x["id"]: x["name"] for x in all_feats}
        bab1 = int((db.get_class_level(cls.lower(), 1) or {}).get("bab", 0))
        for fid in chosen:
            missing = char_module.feat_prereq_unmet(
                prereq_by_id.get(fid) or "", feats_out, final, cls, 1, bab1, name_to_id)
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

        # Dyreledsager (valgfri, kun klasser med companion ved level 1 = druide).
        # Tynd reference: hp_current = beregnet max ved oprettelse; resten afledes.
        gen_companion = None
        animal_id = f.get("companion_animal", "").strip()
        if animal_id and companion_module.companion_effective_level(cls, 1) > 0:
            animal = db.get_animal(animal_id)
            if not animal:
                raise ValueError("Ukendt dyreledsager.")
            comp_name = f.get("companion_name", "").strip() or animal["name"]
            hp_max = companion_module.advance_companion(animal, 1, db)["hp_max"]
            gen_companion = {"name": comp_name, "animal": animal_id,
                             "hp_current": hp_max, "tricks": []}

        # Udstyr → forenet inventar (refs + tilstand). Rustning/skjold = worn,
        # våben = wielded; afledte angreb + AC + vægt udregnes fra inventaret.
        armor_id = f.get("armor", "").strip()
        shield_id = f.get("shield", "").strip()
        valid_armor = {a["id"] for a in db.get_all_armor()}
        valid_weapons = {w["id"] for w in db.get_all_weapons()}
        inventory = []
        if armor_id:
            if armor_id not in valid_armor:
                raise ValueError("Ukendt rustning valgt.")
            inventory.append({"ref": f"armor/{armor_id}", "state": "worn"})
        if shield_id:
            if shield_id not in valid_armor:
                raise ValueError("Ukendt skjold valgt.")
            inventory.append({"ref": f"armor/{shield_id}", "state": "worn"})
        wrefs = f.getlist("weapon_ref")
        wstates = f.getlist("weapon_state")
        for i, ref in enumerate(wrefs):
            ref = ref.strip()
            if not ref:
                continue
            table, _, wid = ref.partition("/")
            if table != "weapons" or wid not in valid_weapons:
                raise ValueError(f"Ukendt våben: {ref}.")
            state = wstates[i].strip() if i < len(wstates) else "wielded"
            if state not in char_module.INVENTORY_STATES:
                state = "wielded"
            inventory.append({"ref": ref, "state": state})

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

        gold = {k: int(f.get(f"gold_{k}", "") or 0) for k in ("pp", "gp", "sp", "cp")}
        combat = {"bab": int(cl1.get("bab", 0)), "speed": rd.get("speed", 30)}

        data = {
            "name": name,
            "race": race,
            "class": cls,
            "level": 1,
            "alignment": f.get("alignment", "").strip(),
            "deity": f.get("deity", "").strip(),
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
    except (ValueError, KeyError) as e:
        return redirect(url_for("create_form", error=str(e)))

    return redirect(url_for("karakter", name=slug))


@app.route("/karakter/<name>")
def karakter(name):
    path = _char_path(name)
    if not path.exists():
        abort(404)

    char = char_module.load_character(str(path))
    ab = char.ability_scores

    # Equipped rustning/skjold → bruges til både AC og rustnings-tjekstraf (ACP).
    # Udledes fra inventaret (worn-poster); falder tilbage til combat.armor/shield
    # for endnu-ikke-migrerede karakterer.
    inv_armor, inv_shield = char_module.equipped_armor(char.inventory, db)
    armor_row  = inv_armor  or (db.get_armor(char.armor)  if char.armor  else None)
    shield_row = inv_shield or (db.get_armor(char.shield) if char.shield else None)
    acp = char_module.armor_check_penalty(armor_row, shield_row)
    # Druide i metalrustning/-skjold mister spellcasting (+ su/sp-evner) i 24t
    druid_armor_block = char_module.druid_armor_violations(char.cls, armor_row, shield_row)

    saves = {
        "Fortitude": char_module.save_total(char.saves.get("fortitude", 0), ab.con),
        "Reflex":    char_module.save_total(char.saves.get("reflex",    0), ab.dex),
        "Will":      char_module.save_total(char.saves.get("will",      0), ab.wis),
    }

    synergy_bonuses = char_module.compute_synergy_bonuses(char.skills)
    char_skill_map = {s.id: s for s in char.skills}
    skill_data = []
    for defn in db.get_all_skills():
        s = char_skill_map.get(defn["id"]) or char_module.Skill(id=defn["id"], ranks=0.0)
        synergy = synergy_bonuses.get(s.id, 0)
        ranked = int(s.ranks) > 0
        trained_only = bool(defn.get("trained_only"))
        total = char_module.skill_total(s, ab, db, synergy, acp)
        acp_applied = acp * int(defn.get("armor_check", 0) or 0)
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
        })
    feat_data  = [(fid, db.get_feat(fid)) for fid in char.feats]

    spell_data: dict[int, list] = {}
    for lvl, spell_ids in char.spells_prepared.items():
        used_indices = set(char.spells_used.get(lvl, []))
        spell_data[lvl] = [
            {"id": sid, "index": i, "spell": db.get_spell(sid), "used": i in used_indices}
            for i, sid in enumerate(spell_ids)
        ]

    condition_data  = [(cid, db.get_condition(cid)) for cid in char.conditions]
    all_conditions  = db.get_all_conditions()

    class_level_data = db.get_class_level(char.cls.lower(), char.level)
    slots: dict[int, int] = {}
    if class_level_data:
        slots = char_module.spell_slots_total(class_level_data, ab.wis)

    xp_info    = char_module.xp_progress(char.experience_points, char.level)
    weight     = char_module.carried_weight(char.inventory, db, char.size)
    enc_limits = char_module.carry_limits(ab.str, char.size)
    enc        = char_module.encumbrance_level(ab.str, weight, char.size)
    base_speed = char.combat.get("speed", 30)
    # Beriget inventar-visning: navn/vægt slås op i kataloget for ref-poster,
    # størrelses-justeres, og state vises. is_ref => navn/vægt redigeres ikke i UI.
    inventory_json = []
    for i in char.inventory:
        r = char_module.resolve_item(i, db, char.size)
        inventory_json.append({
            "name": r["name"], "weight": r["unit_weight"], "qty": i.qty,
            "notes": i.notes, "state": i.state, "is_ref": bool(i.ref),
            "ref": i.ref, "bonus": i.bonus, "str_mult": i.str_mult,
        })

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
    bab = int(char.combat.get("bab", 0))
    all_attacks = char_module.derive_attacks(char.inventory, db, char.size) + list(char.attacks)
    attack_rows = [
        {"attack": atk, **char_module.attack_total(atk, ab, bab, char.size)}
        for atk in all_attacks
    ]
    grapple = char_module.grapple_total(bab, ab.str, char.size)
    initiative = char_module.initiative_total(
        ab, char.feats, int(char.combat.get("initiative_misc", 0)))
    ac = char_module.armor_class(
        ab, char.size,
        armor=armor_row,
        shield=shield_row,
        enc_max_dex=char_module.encumbrance_consequences(enc, base_speed)["max_dex"],
        natural=int(char.combat.get("natural_armor", 0)),
        deflection=int(char.combat.get("deflection", 0)),
        dodge=int(char.combat.get("dodge", 0)),
        misc=int(char.combat.get("misc_ac", 0)),
    )

    abilities = [
        ("STR", ab.str, ab.modifier("str")),
        ("DEX", ab.dex, ab.modifier("dex")),
        ("CON", ab.con, ab.modifier("con")),
        ("INT", ab.int, ab.modifier("int")),
        ("WIS", ab.wis, ab.modifier("wis")),
        ("CHA", ab.cha, ab.modifier("cha")),
    ]

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
        "ability_level": char_module.is_ability_level(new_level),
        "new_features":  new_features,
        "xp_ready":      xp_info["ready"],
    }
    all_feats_json = [
        {"id": f["id"], "name": f["name"],
         "type": f.get("type") or "",
         "prerequisites": f.get("prerequisites") or "",
         "benefit": f.get("benefit") or ""}
        for f in db.get_all_feats()
    ]
    all_skills_json = [
        {"id": s["id"], "name": s["name"], "ability": s.get("ability", "")}
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

    # Druid spells grouped by level — for preparation modal
    cls_lower = char.cls.lower()
    all_cls_spells = db.search_spells(class_filter=cls_lower)
    available_spells: dict[int, list] = {}
    for spell in all_cls_spells:
        lvl = spell.get(f"level_{cls_lower}")
        if lvl is not None:
            available_spells.setdefault(lvl, []).append(spell)

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

    # Companion: beregn det fulde statblok fra den tynde reference (eller None).
    companion = companion_module.build_companion(char, db)

    return render_template(
        "character.html",
        name=name,
        char=char,
        companion=companion,
        abilities=abilities,
        saves=saves,
        skill_data=skill_data,
        feat_data=feat_data,
        spell_data=spell_data,
        slots=slots,
        condition_data=condition_data,
        all_conditions=all_conditions,
        xp_info=xp_info,
        weight=weight,
        enc_limits=enc_limits,
        enc=enc,
        base_speed=base_speed,
        attack_rows=attack_rows,
        grapple=grapple,
        initiative=initiative,
        ac=ac,
        druid_armor_block=druid_armor_block,
        inventory_json=inventory_json,
        catalog_json=catalog_json,
        available_spells=available_spells,
        domain_slots=domain_slots,
        domains_info=domains_info,
        domain_available=domain_available,
        domain_prepared=domain_prepared,
        sla_data=sla_data,
        levelup_info=levelup_info,
        all_feats_json=all_feats_json,
        all_skills_json=all_skills_json,
        cls_skills_json=cls_skills_json,
        snapshots=_snapshots_for(name),
        slug=name,
        has_portrait=_portrait_path(name) is not None,
    )


@app.route("/portrait/<slug>")
def portrait(slug):
    """Server karakterens portræt fra data-mappen (uden for Flasks static/)."""
    path = _portrait_path(slug)
    if path is None:
        abort(404)
    return send_from_directory(str(PORTRAITS_DIR), path.name)


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
    new_hp = max(-20, min(char.hp_max, char.hp_current + delta))
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

    if mark_used:
        spells_used.setdefault(level, [])
        if spell_index not in spells_used[level]:
            spells_used[level].append(spell_index)
    else:
        if level in spells_used and spell_index in spells_used[level]:
            spells_used[level].remove(spell_index)

    char_module.save_character(str(path), {"spells_used": spells_used})
    return jsonify({"spells_used": {str(k): v for k, v in spells_used.items()}})


@app.route("/api/conditions", methods=["POST"])
def api_conditions():
    data         = request.get_json()
    slug         = data.get("char")
    condition_id = data.get("condition_id")
    action       = data.get("action")   # "add" | "remove"
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    conditions = list(char.conditions)

    if action == "add" and condition_id not in conditions:
        conditions.append(condition_id)
    elif action == "remove" and condition_id in conditions:
        conditions.remove(condition_id)

    char_module.save_character(str(path), {"conditions": conditions})
    return jsonify({"conditions": conditions})


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
            inventory.append(char_module.InventoryItem(
                ref=ref, state=state,
                qty=max(1, int(data.get("qty", 1))),
                bonus=int(data.get("bonus", 0)),
                str_mult=(None if sm in (None, "") else float(sm)),
                notes=str(data.get("notes", "")),
            ))
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
            if "bonus" in data:
                old.bonus = int(data.get("bonus") or 0)
            if "str_mult" in data:
                sm = data.get("str_mult")
                old.str_mult = None if sm in (None, "") else float(sm)
            if not old.ref:
                old.name   = str(data.get("name", old.name))
                old.weight = float(data.get("weight", old.weight))

    char_module.save_character(str(path), {"inventory": inventory})
    ab     = char.ability_scores
    weight = char_module.carried_weight(inventory, db, char.size)
    enc    = char_module.encumbrance_level(ab.str, weight, char.size)
    inv_rows = []
    for i in inventory:
        r = char_module.resolve_item(i, db, char.size)
        inv_rows.append({
            "name": r["name"], "weight": r["unit_weight"], "qty": i.qty,
            "notes": i.notes, "state": i.state, "is_ref": bool(i.ref),
            "ref": i.ref, "bonus": i.bonus, "str_mult": i.str_mult,
        })
    return jsonify({
        "inventory":  inv_rows,
        "weight":     weight,
        "enc":        enc,
        "enc_limits": char_module.carry_limits(ab.str, char.size),
    })


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
    char_module.save_character(str(path), {"spells_used": {}, "domain_spells_used": {}})
    return jsonify({"ok": True})


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
              "weapon": db.get_weapon, "armor": db.get_armor, "item": db.get_item}
    fn = lookup.get(dtype)
    if not fn:
        return jsonify({"error": "unknown type"}), 400
    row = fn(did)
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
