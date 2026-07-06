"""Blueprint: DM-modul (R1) — kampagne-oversigt + play-visning.

Ruter under /dm:
  GET  /dm/                     oversigt: sessioner + opret-formular
  POST /dm/sessions             opret session (navn, eventyr, party)
  POST /dm/sessions/<slug>/delete
  GET  /dm/play/<slug>          åbn session; ?scene=<id> navigerer + gemmer

Scene-INDHOLDET vises basalt her (read-aloud, prosa, roster, rum). Party-
statblokke + billed-/entity-opslag kommer i R1 commit 4.
"""
import re

from flask import (Blueprint, abort, redirect, render_template, request,
                   send_from_directory, url_for)
from markupsafe import Markup, escape

import db
import dm_party
import dm_session as ds
from paths import ADVENTURES_DIR, CHARACTERS_DIR

dm_bp = Blueprint("dm", __name__, url_prefix="/dm")

_ENTITY_RE = re.compile(r"@([A-Za-zÆØÅæøå]+)\[([^\]]+)\]")


@dm_bp.app_template_filter("entities")
def _entities_filter(text: str) -> Markup:
    """Vis @type[id] som en diskret markeret id-tekst (klikbar i commit 4)."""
    out, last = [], 0
    for m in _ENTITY_RE.finditer(text or ""):
        out.append(escape(text[last:m.start()]))
        out.append(Markup('<span class="ent ent-{}">{}</span>').format(
            m.group(1).lower(), m.group(2)))
        last = m.end()
    out.append(escape((text or "")[last:]))
    return Markup("").join(out)


def _character_slugs() -> list[str]:
    if not CHARACTERS_DIR.exists():
        return []
    return sorted(p.stem for p in CHARACTERS_DIR.glob("*.yaml"))


@dm_bp.route("/")
def index():
    return render_template("dm/index.html",
                           sessions=ds.list_sessions(),
                           adventures=ds.list_adventures(),
                           characters=_character_slugs())


@dm_bp.route("/sessions", methods=["POST"])
def create():
    name = (request.form.get("name") or "").strip()
    adventure = request.form.get("adventure") or ""
    party = request.form.getlist("party")
    if not adventure:
        abort(400, "Vælg et eventyr.")
    try:
        session = ds.create_session(name, adventure, party)
    except FileNotFoundError:
        abort(404, "Eventyret findes ikke.")
    return redirect(url_for("dm.play", slug=session.slug))


@dm_bp.route("/sessions/<slug>/delete", methods=["POST"])
def delete(slug):
    ds.delete_session(slug)
    return redirect(url_for("dm.index"))


@dm_bp.route("/media/<path:filename>")
def media(filename):
    """Servér eventyr-billeder (kort/handouts). Kilden er `adventures/media/…`,
    som ligger i install-mappen sammen med selve eventyrene. send_from_directory
    afviser sti-traversal, så `filename` ikke kan slippe ud af ADVENTURES_DIR."""
    return send_from_directory(ADVENTURES_DIR, filename)


@dm_bp.route("/play/<slug>")
def play(slug):
    try:
        session = ds.load_session(slug)
    except FileNotFoundError:
        abort(404)
    adventure = ds.load_adventure(session.adventure)
    scene_ids = {sc.id for sc in adventure.scenes}
    scene_id = request.args.get("scene")
    if scene_id and scene_id in scene_ids:
        session = ds.goto_scene(slug, scene_id)          # persistér navigation
    active = next((sc for sc in adventure.scenes if sc.id == session.active_scene),
                  adventure.scenes[0] if adventure.scenes else None)
    party = dm_party.party_view(session.party, db)
    return render_template("dm/play.html", session=session,
                           adventure=adventure, active=active, party=party)
