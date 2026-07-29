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

Privat overlay: efter data/<tabel>.yaml indlæses paths.PRIVATE_DATA_DIR/<tabel>.yaml
hvis den findes — egne monstre/NPC'er og andet ikke-OGL-indhold, der ikke må i
det offentlige repo. Mappen ligger uden for repoet (sæt DND_PRIVATE_DATA_DIR).
Rækker med samme primærnøgle som en SRD-række OVERSKRIVER den; det er tilladt,
men seed'en advarer, så det aldrig sker uopdaget.

SRD-tekst er Open Game Content fra System Reference Document v3.5, gengivet under
Open Game License v1.0a. Kilde: olimot/srd-v3.5-md. 'd20 System' og 'Wizards of
the Coast' er varemærker tilhørende Wizards of the Coast og bruges ikke under OGL.
Se OGL afsnit 15 for fuld attribution.
"""
import os
import sqlite3
from pathlib import Path

from ruamel.yaml import YAML

from paths import PRIVATE_DATA_DIR

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
    "class_levels",
    "domains",
    "domain_spells",
    "spell_attacks",
    "armor",
    "weapons",
    "items",
    "animals",
    "monsters",
    "traps",
    "doors",
    "effects",
    "special_abilities",
    "magic_items",
    "specific_items",
]


def _load_rows(path: Path) -> list[dict]:
    """Læs en datafil. Tom/manglende fil → tom liste."""
    if not path.exists():
        return []
    yaml = YAML(typ="safe")
    return yaml.load(path) or []


def _overridden(base: list[dict], private: list[dict],
                key_cols: list[str]) -> list[str]:
    """Primærnøgler hvor en privat række overskriver en fra data/.

    Nyt privat indhold er det normale; en kollision betyder at SRD-versionen
    forsvinder ud af databasen, og det skal man vide at man har valgt.
    """
    def key(row: dict) -> tuple:
        return tuple(row.get(c) for c in key_cols)

    base_keys = {key(r) for r in base}
    return [":".join(str(v) for v in key(r)) for r in private
            if key(r) in base_keys]


def seed() -> None:
    schema = (DATA_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)

    counts: dict[str, int] = {}
    private_counts: dict[str, int] = {}
    warnings: list[str] = []
    for table in TABLES:
        info = list(conn.execute(f"PRAGMA table_info({table})"))
        cols = [r[1] for r in info]
        key_cols = [r[1] for r in info if r[5]]  # r[5] = pk-position, 0 = ikke pk
        stmt = (
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(':' + c for c in cols)})"
        )
        rows = _load_rows(DATA_DIR / f"{table}.yaml")
        private = _load_rows(PRIVATE_DATA_DIR / f"{table}.yaml")
        # Privat sidst: INSERT OR REPLACE lader overlayet vinde ved samme nøgle.
        for row in rows + private:
            conn.execute(stmt, {c: row.get(c) for c in cols})
        counts[table] = len(rows)
        private_counts[table] = len(private)
        warnings += [f"{table}: {k}" for k in _overridden(rows, private, key_cols)]

    conn.commit()
    conn.close()

    print(f"Database seeded at {DB_PATH}")
    for table in TABLES:
        extra = f"  (+{private_counts[table]} privat)" if private_counts[table] else ""
        print(f"  {counts[table]:>4} {table}{extra}")

    if any(private_counts.values()):
        print(f"Privat overlay: {PRIVATE_DATA_DIR}")
    if warnings:
        print("ADVARSEL — privat indhold overskriver SRD-rækker:")
        for w in warnings:
            print(f"  {w}")


if __name__ == "__main__":
    seed()
