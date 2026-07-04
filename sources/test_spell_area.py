"""Unit-tests for kategori E (område/save) — skade-skalering + udledning.

Kør: python -m pytest test_spell_area.py   (fra sources/)

Kategori E rammer FJENDER med en save-DC frem for et til-hit-rul (Fireball, Sleep).
Skaden skalerer ANTAL terninger pr. casterniveau (1d6/niveau, cappet), modsat
kategori B's flade +bonus. Rene save-effekter (Sleep/Web) har ingen skade.
"""
import db
from spells import spell_area_damage, spell_shots
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


def test_spell_shots_scaling():
    # Magic Missile: 1 + 1 pr. 2 niveauer over 1., max 5
    mm = {"shots": 1, "shots_from": 1, "shots_div": 2, "shots_max": 5}
    assert [spell_shots(mm, c) for c in (1, 3, 5, 9, 11)] == [1, 2, 3, 5, 5]
    # Scorching Ray: 1 + 1 pr. 4 niveauer over 3., max 3
    sr = {"shots": 1, "shots_from": 3, "shots_div": 4, "shots_max": 3}
    assert [spell_shots(sr, c) for c in (3, 7, 11, 20)] == [1, 2, 3, 3]
    # uden shots-felter → enkelt angreb
    assert spell_shots({"base_damage": "1d6"}, 10) == 1


def test_magic_missile_auto_hit_and_shots():
    c = load_character("defaults/tjorn.yaml")  # level 3
    c.spells_prepared = {1: ["magic_missile"]}
    c.spells_active = {1: [0]}
    out = derive_spell_attacks(c, db)
    assert len(out) == 1
    assert out[0]["auto_hit"] is True
    assert out[0]["shots"] == 2                 # CL3 → 2 missiler
    assert out[0]["attack"].fixed_damage == "1d4+1"


def test_e_rows_excluded_from_attacks():
    # Fireball må IKKE dukke op som et til-hit-angreb i angrebstabellen
    out = derive_spell_attacks(_mk(), db)
    assert all("Fireball" not in d["attack"].name for d in out)
