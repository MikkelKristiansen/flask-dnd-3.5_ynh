"""dm_routes_media — DM-modulets billed-/fil-ruter på dm_bp.

Udspaltet fra dm.py: eventyr-media (upload/slet/servér) + monster-token-administration
(side/upload/slet). Selvstændige I/O-ruter (dm_media / monster_tokens ejer disk-I/O'en).
Dekorerer SAMME dm_bp (fra dm) → url_for uændret; dm.py importerer modulet i bunden.
(Serve-ruten for selve token-billedet, /dm/monster_token/<slug>, ligger i app.py.)
"""
from flask import (abort, redirect, render_template, request,
                   send_from_directory, url_for)

import dm_media
import dm_session as ds
import monster_tokens
from dm import dm_bp


@dm_bp.route("/adventures/<adventure>/media", methods=["POST"])
def upload_media(adventure):
    if adventure not in ds.list_adventures():
        abort(404)
    adv_dir = ds.adventure_dir(adventure)
    names, errors = [], []
    for f in request.files.getlist("images"):
        if not f or not f.filename:
            continue
        try:
            names.append(dm_media.save_media(adv_dir, f))
        except ValueError as e:
            errors.append(f"{f.filename}: {e}")
    q = {}
    if names:
        q["uploaded"] = ", ".join(names)
    if errors:
        q["error"] = " · ".join(errors)
    return redirect(url_for("dm.adventure", adventure=adventure, **q))


@dm_bp.route("/adventures/<adventure>/media/<filename>/delete", methods=["POST"])
def delete_media(adventure, filename):
    if adventure not in ds.list_adventures():
        abort(404)
    dm_media.delete_media(ds.adventure_dir(adventure), filename)
    return redirect(url_for("dm.adventure", adventure=adventure))


# ── Monster-tokens (billed-standees, browser-upload) ─────────────────────────
@dm_bp.route("/monster-tokens")
def monster_tokens_page():
    """Administrér monster-billed-tokens i browseren: se, upload, slet — erstatter
    scp. Filnavnet bliver token-slug (goblin.png → 'goblin'); brættet viser standeen
    for de monstre hvis slug matcher."""
    return render_template("dm/monster_tokens.html",
                           tokens=monster_tokens.list_tokens(),
                           uploaded=request.args.get("uploaded"),
                           error=request.args.get("error"))


@dm_bp.route("/monster-tokens/upload", methods=["POST"])
def upload_monster_tokens():
    names, errors = [], []
    for f in request.files.getlist("images"):
        if not f or not f.filename:
            continue
        try:
            names.append(monster_tokens.save_token(f))
        except ValueError as e:
            errors.append(f"{f.filename}: {e}")
    q = {}
    if names:
        q["uploaded"] = ", ".join(names)
    if errors:
        q["error"] = " · ".join(errors)
    return redirect(url_for("dm.monster_tokens_page", **q))


@dm_bp.route("/monster-tokens/<slug>/delete", methods=["POST"])
def delete_monster_token(slug):
    monster_tokens.delete_token(slug)
    return redirect(url_for("dm.monster_tokens_page"))


@dm_bp.route("/media/<adventure>/<path:filename>")
def media(adventure, filename):
    """Servér et eventyrs billeder fra `adventures/<eventyr>/media/…`.
    `adventure` saniteres til ét mappe-segment; send_from_directory afviser
    desuden sti-traversal i `filename`."""
    return send_from_directory(ds.adventure_dir(adventure), filename)
