"""One-time seeder: data/*.yaml → srd35.db

Run:  python importer.py
Idempotent — safe to run multiple times (drops and recreates tables).

Kilden til sandheden for SRD-data er de deklarative filer i data/:
  data/schema.sql      — tabelstruktur (DDL)
  data/<tabel>.yaml    — én fil pr. tabel med rådata

Denne fil er bevidst tynd: den læser skemaet, opretter tabellerne og indlæser
hver YAML-fil generisk. Tilføj en ny kategori ved at (1) tilføje CREATE TABLE i
schema.sql, (2) lægge en data/<tabel>.yaml ved siden af, og (3) føje tabelnavnet
til TABLES nedenfor. Ingen ny indlæsningskode nødvendig.

SRD-tekst er Open Game Content fra System Reference Document v3.5, gengivet under
Open Game License v1.0a. Kilde: olimot/srd-v3.5-md. 'd20 System' og 'Wizards of
the Coast' er varemærker tilhørende Wizards of the Coast og bruges ikke under OGL.
Se OGL afsnit 15 for fuld attribution.
"""
import os
import sqlite3
from pathlib import Path

from ruamel.yaml import YAML

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
DB_PATH = Path(os.environ.get("DND_DB_PATH", str(BASE / "srd35.db")))

# Tabeller indlæses i denne rækkefølge. Hver svarer til data/<navn>.yaml og en
# CREATE TABLE i data/schema.sql.
TABLES = [
    "spells",
    "skills",
    "feats",
    "conditions",
    "druid_levels",
    "cleric_levels",
    "ranger_levels",
    "rogue_levels",
    "domains",
    "domain_spells",
    "spell_attacks",
    "armor",
    "weapons",
    "items",
    "animals",
]


def _load_rows(path: Path) -> list[dict]:
    """Læs en datafil. Tom/manglende fil → tom liste."""
    if not path.exists():
        return []
    yaml = YAML(typ="safe")
    return yaml.load(path) or []


def seed() -> None:
    schema = (DATA_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)

    counts: dict[str, int] = {}
    for table in TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        stmt = (
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(':' + c for c in cols)})"
        )
        rows = _load_rows(DATA_DIR / f"{table}.yaml")
        for row in rows:
            conn.execute(stmt, {c: row.get(c) for c in cols})
        counts[table] = len(rows)

    conn.commit()
    conn.close()

    print(f"Database seeded at {DB_PATH}")
    for table in TABLES:
        print(f"  {counts[table]:>4} {table}")


if __name__ == "__main__":
    seed()
