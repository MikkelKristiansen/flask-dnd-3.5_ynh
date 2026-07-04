"""Unit-tests for kategori E (område/save) — skade-skalering + udledning.

Kør: python -m pytest test_spell_area.py   (fra sources/)

Kategori E rammer FJENDER med en save-DC frem for et til-hit-rul (Fireball, Sleep).
Skaden skalerer ANTAL terninger pr. casterniveau (1d6/niveau, cappet), modsat
kategori B's flade +bonus. Rene save-effekter (Sleep/Web) har ingen skade.
"""
import db
from rules import spell_area_damage
from character import load_character, derive_spell_effects, derive_spell_attacks


# ── ren skade-skalering (ingen db/char nødvendig) ──────────────────────────
def test_dice_scaling_caps():
    fb = {"base_damage": "1d6", "dice_per_level": 1, "dice_per_level_max": 10}
    assert spell_area_damage(fb, 5) == "5d6"
    assert spell_area_damage(fb, 10) == "10d6"
    assert spell_area_damage(fb, 12) == "10d6"          # cappet ved 10 terninger
    cold = {"base_damage": "1d6", "dice_per_level": 1, "dice_per_level_max": 15}
    assert spell_area_damage(cold, 9) == "9d6"
    assert spell_area_damage(cold, 20) == "15d6"


def test_no_damage_effect_returns_empty():
    assert spell_area_damage({"base_damage": None}, 10) == ""
    assert spell_area_damage({"base_damage": ""}, 10) == ""


def test_flat_bonus_fallback_when_no_dice_scaling():
    # uden dice_per_level → falder tilbage til flad-bonus-motoren (Produce Flame-stil)
    row = {"base_damage": "1d6", "dmg_per_level": 1, "dmg_per_level_max": 5}
    assert spell_area_damage(row, 2) == "1d6+2"


# ── data-integritet (kræver rebuildet db) ──────────────────────────────────
def test_fireball_data_present():
    rows = db.get_spell_attacks("fireball")
    assert len(rows) == 1
    r = rows[0]
    assert r["kind"] == "save"
    assert r["save_type"] == "reflex" and r["save_effect"] == "half"
    assert spell_area_damage(r, 5) == "5d6"


# ── udledning fra en karakter med E-spell "I brug" ─────────────────────────
def _mk(**over):
    """Default-karakter med fireball forberedt på L3 idx 0 — muteret pr. test."""
    c = load_character("defaults/tjorn.yaml")
    c.spells_prepared = {3: ["fireball"]}
    c.spells_active = {3: [0]}
    for k, v in over.items():
        setattr(c, k, v)
    return c


def test_derive_effects_surfaces_fireball():
    out = derive_spell_effects(_mk(), db)
    assert len(out) == 1
    e = out[0]
    assert e["label"] == "Fireball"
    assert e["save_type"] == "reflex" and e["save_effect"] == "half"
    assert e["range"]                    # hentet fra spells-tabellen
    assert e["damage"].endswith("d6")


def test_save_only_spell_has_no_damage():
    out = derive_spell_effects(_mk(spells_prepared={1: ["web"]},
                                   spells_active={1: [0]}), db)
    assert out[0]["damage"] == ""
    assert out[0]["save_type"] == "reflex"


def test_e_rows_excluded_from_attacks():
    # Fireball må IKKE dukke op som et til-hit-angreb i angrebstabellen
    out = derive_spell_attacks(_mk(), db)
    assert all("Fireball" not in d["attack"].name for d in out)
