"""D&D 3.5 Flask-app — tablet-first karakterark."""
import io
import os
import tempfile
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from ruamel.yaml import YAML
from werkzeug.middleware.proxy_fix import ProxyFix

import catalog
import character as char_module
import db
import dice as dice_module
import effects
import refdata

from character_view import build_character_view, _race_weapon_prof_ids
from paths import CHARACTERS_DIR, PORTRAITS_DIR, PORTRAIT_EXTS, _safe_slug
from portraits import _portrait_path, _validate_portrait, _write_portrait
from creation import GEN_CLASSES, _gen_context, build_character_data


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
# Karakterfiler er små (~få KB), men portræt-upload kan være et helt foto.
# 8 MB rummer rigeligt et almindeligt billede og holder stadig grænsen for store.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


@app.context_processor
def _inject_static_url():
    """Cache-busting for statiske assets: static_url('x.js') → /static/x.js?v=<mtime>.

    JS/CSS-filerne har ingen versions-query, så browseren cacher dem aggressivt og
    viser gammel kode efter et deploy indtil man hard-refresher. Ved at hænge filens
    ændringstidspunkt på som ?v= skifter URL'en automatisk når filen ændres, og
    browseren henter den nye. Falder tilbage til ren URL hvis filen ikke findes.
    """
    def static_url(filename):
        try:
            ver = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            return url_for("static", filename=filename)
        return f"{url_for('static', filename=filename)}?v={ver}"
    return {"static_url": static_url}


def _char_path(slug: str) -> Path:
    return CHARACTERS_DIR / f"{slug}.yaml"

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
        data = build_character_data(f)

        slug = _safe_slug(data["name"])
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

# ── API (kerne — resten er udspaltet i routes_*.py-blueprints, se bunden) ───

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
    # En toad-familiar giver +3 maks-HP (SRD) → hæver også loftet.
    comp = char.companion or {}
    fam_hp = refdata.familiar_hp_bonus(comp.get("animal")) if comp.get("kind") == "familiar" else 0
    ceiling = char.hp_max + fam_hp + effects.temp_hp(char, db)
    new_hp = max(-20, min(ceiling, char.hp_current + delta))
    char_module.save_character(str(path), {"hp_current": new_hp})
    return jsonify({"hp_current": new_hp, "hp_max": char.hp_max + fam_hp})

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


# ── Blueprints (domænernes egne routes — se hver fil for indhold) ──────────
from routes_spells import spells_bp
from routes_summon import summon_bp
from routes_combat import combat_bp
from routes_companion import companion_bp
from routes_progression import progression_bp
from routes_inventory import inventory_bp

for bp in (spells_bp, summon_bp, combat_bp, companion_bp, progression_bp, inventory_bp):
    app.register_blueprint(bp)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
