"""Blueprint: versionshistorik for karakterark — gendan, gem navngiven, omdøb.

Alle tre ruter tager et snapshot-filnavn fra klienten. Det navn er derfor
usikkert input, og de deler samme validering: filen SKAL være et faktisk
snapshot for netop denne karakter, ellers afvises den. Se _validated_snapshot.

_char_path importeres lazy (se routes_spells.py for hvorfor).
"""
from flask import Blueprint, jsonify, request

import character as char_module
import versions

versions_bp = Blueprint("versions", __name__)


def _char_or_404(slug: str):
    """Stien til en karakterfil, eller None hvis den ikke findes."""
    from app import _char_path
    path = _char_path(slug)
    return path if path.exists() else None


def _validated_snapshot(path, snapshot_name: str) -> str | None:
    """Godkend et snapshot-filnavn fra klienten, eller returnér None.

    Kun et navn der faktisk er et snapshot for DENNE karakter accepteres. Det
    lukker path traversal: "../../characters/anden.yaml" står ikke på listen.
    """
    valid = {s.name for s in char_module.list_snapshots(path)}
    return snapshot_name if snapshot_name in valid else None


@versions_bp.route("/api/restore", methods=["POST"])
def api_restore():
    """Rul arket tilbage til en tidligere version (den nuværende gemmes først)."""
    data = request.get_json()
    path = _char_or_404(data.get("char"))
    if path is None:
        return jsonify({"error": "not found"}), 404
    snapshot = _validated_snapshot(path, str(data.get("snapshot", "")))
    if snapshot is None:
        return jsonify({"error": "ukendt snapshot"}), 400
    char_module.restore_snapshot(str(path), snapshot)
    return jsonify({"ok": True})


@versions_bp.route("/api/version/save", methods=["POST"])
def api_version_save():
    """Gem den nuværende tilstand som en navngivet version."""
    data = request.get_json()
    path = _char_or_404(data.get("char"))
    if path is None:
        return jsonify({"error": "not found"}), 404
    try:
        dest = versions.save_named_snapshot(path, data.get("name", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "file": dest.name,
                    "name": versions.snapshot_label(dest)})


@versions_bp.route("/api/version/rename", methods=["POST"])
def api_version_rename():
    """Navngiv en eksisterende version bagudrettet. Tomt navn fjerner mærkatet."""
    data = request.get_json()
    path = _char_or_404(data.get("char"))
    if path is None:
        return jsonify({"error": "not found"}), 404
    snapshot = _validated_snapshot(path, str(data.get("snapshot", "")))
    if snapshot is None:
        return jsonify({"error": "ukendt snapshot"}), 400
    new_file = versions.rename_snapshot(path, snapshot, data.get("name", ""))
    return jsonify({"ok": True, "file": new_file,
                    "name": versions.snapshot_label(new_file)})
