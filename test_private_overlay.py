"""Tests for det private data-overlay: private-data/<tabel>.yaml lægges ovenpå
data/<tabel>.yaml når importer.py seeder srd35.db.

Seeder mod en midlertidig db-fil, så den rigtige srd35.db ikke røres.
"""
import sqlite3

import pytest

import importer

# Mindste monster-post skemaet accepterer. INSERT nævner alle kolonner, så
# schema.sql's DEFAULT 0 træder ikke i kraft — init/bab/saves skal skrives.
MINIMAL = """\
- id: {id}
  name: {name}
  size: medium
  type: humanoid
  hp_max: 5
  ac: 14
  ac_touch: 11
  ac_flat: 13
  init: 1
  speed: "30 ft."
  bab: 1
  save_fort: 3
  save_ref: 1
  save_will: 0
  attacks: '[]'
"""


@pytest.fixture
def seed_with(tmp_path, monkeypatch):
    """Seed en frisk db med et givet privat overlay. Returnerer en connection."""
    def _seed(**files: str):
        private = tmp_path / "private-data"
        private.mkdir()
        for table, body in files.items():
            (private / f"{table}.yaml").write_text(body, encoding="utf-8")
        db = tmp_path / "test.db"
        monkeypatch.setattr(importer, "PRIVATE_DATA_DIR", private)
        monkeypatch.setattr(importer, "DB_PATH", db)
        importer.seed()
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        return conn
    return _seed


def test_private_monster_lands_in_db(seed_with):
    # Et privat monster er ikke et særtilfælde i opslag: det ligger i samme
    # tabel som SRD-monstrene, så db.get_monster og DM-modulet finder det.
    conn = seed_with(monsters=MINIMAL.format(id="mk-test", name="Privat NPC"))
    row = conn.execute("SELECT * FROM monsters WHERE id = 'mk-test'").fetchone()
    assert row is not None, "privat monster nåede ikke i databasen"
    assert row["name"] == "Privat NPC"
    # SRD-indholdet er der stadig.
    assert conn.execute("SELECT 1 FROM monsters WHERE id = 'skelet'").fetchone()


def test_overlay_works_for_other_tables(seed_with):
    conn = seed_with(traps="- id: mk-faelde\n  name: Egen fælde\n  cr: '1'\n")
    row = conn.execute("SELECT name FROM traps WHERE id = 'mk-faelde'").fetchone()
    assert row["name"] == "Egen fælde"


def test_missing_overlay_dir_is_fine(tmp_path, monkeypatch):
    # Normaltilstanden på en maskine uden privat indhold — seed skal bare køre.
    monkeypatch.setattr(importer, "PRIVATE_DATA_DIR", tmp_path / "findes-ikke")
    monkeypatch.setattr(importer, "DB_PATH", tmp_path / "test.db")
    importer.seed()
    conn = sqlite3.connect(tmp_path / "test.db")
    assert conn.execute("SELECT COUNT(*) FROM monsters").fetchone()[0] > 0


def test_same_id_overrides_srd_and_warns(seed_with, capsys):
    # Tilladt, men aldrig i det stille: SRD-versionen forsvinder ud af db'en.
    conn = seed_with(monsters=MINIMAL.format(id="skelet", name="Mit eget skelet"))
    row = conn.execute("SELECT name FROM monsters WHERE id = 'skelet'").fetchone()
    assert row["name"] == "Mit eget skelet"
    out = capsys.readouterr().out
    assert "ADVARSEL" in out and "monsters: skelet" in out


def test_new_ids_do_not_warn(seed_with, capsys):
    seed_with(monsters=MINIMAL.format(id="mk-test", name="Privat NPC"))
    assert "ADVARSEL" not in capsys.readouterr().out


def test_overridden_handles_composite_keys():
    # class_levels har sammensat nøgle (class, level) — kollision kræver begge.
    base = [{"class": "fighter", "level": 1}]
    private = [{"class": "fighter", "level": 2}, {"class": "fighter", "level": 1}]
    assert importer._overridden(base, private, ["class", "level"]) == ["fighter:1"]
