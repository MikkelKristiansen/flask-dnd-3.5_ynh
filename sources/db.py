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


def get_armor(armor_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM armor WHERE id = ?", (armor_id,)
        ).fetchone()
    return dict(row) if row else None


def get_all_armor() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM armor ORDER BY type, armor_bonus"
        ).fetchall()
    return [dict(r) for r in rows]


def get_weapon(weapon_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM weapons WHERE id = ?", (weapon_id,)
        ).fetchone()
    return dict(row) if row else None


def get_all_weapons() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM weapons ORDER BY category, weapon_class, name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_item(item_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    return dict(row) if row else None


def get_all_items() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM items ORDER BY category, name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_domain(domain_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM domains WHERE id = ?", (domain_id,)
        ).fetchone()
    return dict(row) if row else None


def get_domains(domain_ids: list[str]) -> list[dict]:
    """Returns the domain rows for the given ids, in the order given."""
    if not domain_ids:
        return []
    placeholders = ",".join("?" * len(domain_ids))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM domains WHERE id IN ({placeholders})", domain_ids
        ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[d] for d in domain_ids if d in by_id]


def get_domain_spells(
    domain_ids: list[str], level: int | None = None
) -> list[dict]:
    """Returns domain spells joined with the spells table.

    Joining means only spells that actually exist in the spells table are
    returned — domain entries for not-yet-seeded spells are silently skipped.
    Each row carries the spell columns plus ``domain_id`` and ``domain_level``.
    """
    if not domain_ids:
        return []
    placeholders = ",".join("?" * len(domain_ids))
    params: list = list(domain_ids)
    level_clause = ""
    if level is not None:
        level_clause = "AND ds.level = ?"
        params.append(level)
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT s.*, ds.domain_id AS domain_id, ds.level AS domain_level
                FROM domain_spells ds
                JOIN spells s ON s.id = ds.spell_id
                WHERE ds.domain_id IN ({placeholders}) {level_clause}
                ORDER BY ds.level, s.name""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


_CLASS_LEVEL_TABLES = {
    "druid": "druid_levels",
    "cleric": "cleric_levels",
    "ranger": "ranger_levels",
}


def get_class_level(class_name: str, level: int) -> dict | None:
    table = _CLASS_LEVEL_TABLES.get(class_name.lower())
    if table is None:
        return None
    with _connect() as conn:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE level = ?", (level,)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["features"] = json.loads(result["features"])
    result["spell_slots"] = [
        result[f"spells_{i}"] for i in range(10)
    ]
    return result
