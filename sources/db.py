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


# Hvilken spell-list-kolonne en klasse caster fra. Sorcerer deler wizard-listen
# (der er ingen level_sorcerer-kolonne i SRD); bard har sin egen level_bard.
_SPELL_LIST_COLUMN = {
    "druid": "level_druid", "cleric": "level_cleric", "wizard": "level_wizard",
    "sorcerer": "level_wizard", "bard": "level_bard",
}


def spell_list_column(cls: str) -> str | None:
    """Spell-list-kolonnen klassen caster fra (fx 'level_wizard'), eller None for
    klasser uden spells. Én kilde til sandhed for klasse→spell-liste-mappingen."""
    return _SPELL_LIST_COLUMN.get((cls or "").lower())


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

    col = spell_list_column(class_filter) if class_filter else None
    if col and level is not None:
        conditions.append(f"{col} = ?")   # col fra fast dict — ikke bruger-input
        params.append(level)
    elif col:
        conditions.append(f"{col} IS NOT NULL")
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


def get_fighter_bonus_feats() -> list[dict]:
    """Feats der må vælges som fighter-bonus-feat (fighter_bonus = 1 i feats.yaml)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM feats WHERE fighter_bonus = 1 ORDER BY name"
        ).fetchall()
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


def _animal_row(row) -> dict:
    """Konverter en animals-række til dict og afkod JSON-felterne."""
    rec = dict(row)
    rec["attacks"] = json.loads(rec["attacks"])
    rec["skills"] = json.loads(rec["skills"])
    rec["feats"] = json.loads(rec["feats"])
    if rec.get("good_saves"):
        rec["good_saves"] = json.loads(rec["good_saves"])
    return rec


def get_animal(animal_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM animals WHERE id = ?", (animal_id,)
        ).fetchone()
    return _animal_row(row) if row else None


def get_all_animals() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM animals ORDER BY name").fetchall()
    return [_animal_row(r) for r in rows]


def _effect_row(row) -> dict:
    """Konverter en effects-række til dict og afkod JSON-felterne (modifiers/riders/affects)."""
    rec = dict(row)
    rec["modifiers"] = json.loads(rec["modifiers"] or "[]")
    rec["riders"] = json.loads(rec["riders"] or "[]")
    rec["affects"] = json.loads(rec["affects"] or "[]")
    return rec


def get_effect(effect_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM effects WHERE id = ?", (effect_id,)
        ).fetchone()
    return _effect_row(row) if row else None


def get_all_effects() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM effects ORDER BY name").fetchall()
    return [_effect_row(r) for r in rows]


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


def get_spell_attacks(spell_id: str) -> list[dict]:
    """Katalog-angreb for én spell (0..n rækker). Tom liste hvis ingen."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM spell_attacks WHERE spell_id = ?", (spell_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_class_level(class_name: str, level: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM class_levels WHERE class = ? AND level = ?",
            (class_name.lower(), level),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result.pop("class", None)  # tabel-diskriminator, ikke en del af niveau-dataene
    result["features"] = json.loads(result["features"])
    result["spell_slots"] = [
        result[f"spells_{i}"] for i in range(10)
    ]
    return result
