"""SQLite read-only access layer for SRD 3.5 data."""
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DND_DB_PATH",
                              str(Path(__file__).parent / "srd35.db")))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_spell(spell_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM spells WHERE id = ?", (spell_id,)).fetchone()
    return dict(row) if row else None


def search_spells(
    query: str = "",
    class_filter: str | None = None,
    level: int | None = None,
) -> list[dict]:
    conditions = []
    params: list = []

    if query:
        conditions.append("name LIKE ?")
        params.append(f"%{query}%")

    if class_filter == "druid" and level is not None:
        conditions.append("level_druid = ?")
        params.append(level)
    elif class_filter == "druid":
        conditions.append("level_druid IS NOT NULL")
    elif class_filter == "cleric" and level is not None:
        conditions.append("level_cleric = ?")
        params.append(level)
    elif class_filter == "wizard" and level is not None:
        conditions.append("level_wizard = ?")
        params.append(level)
    elif level is not None:
        conditions.append(
            "(level_druid = ? OR level_cleric = ? OR level_wizard = ?)"
        )
        params.extend([level, level, level])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM spells {where} ORDER BY name", params
        ).fetchall()
    return [dict(r) for r in rows]


def get_skill(skill_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
    return dict(row) if row else None


def get_all_skills() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM skills ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_feat(feat_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM feats WHERE id = ?", (feat_id,)).fetchone()
    return dict(row) if row else None


def get_all_feats() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM feats ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_condition(condition_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM conditions WHERE id = ?", (condition_id,)
        ).fetchone()
    return dict(row) if row else None


def get_all_conditions() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM conditions ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_druid_level(level: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM druid_levels WHERE level = ?", (level,)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["features"] = json.loads(result["features"])
    result["spell_slots"] = [
        result[f"spells_{i}"] for i in range(10)
    ]
    return result


def get_class_level(class_name: str, level: int) -> dict | None:
    """Generic class level lookup — currently only supports 'druid'."""
    if class_name.lower() == "druid":
        return get_druid_level(level)
    return None
