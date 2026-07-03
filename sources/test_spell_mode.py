"""Unit-tests for spell-angrebs-tilstande (mode_group).

Kør: python -m pytest test_spell_mode.py   (fra sources/)

Produce Flame har to katalog-rækker med samme mode_group ("touch"): nærkamp-touch
og kastet ranged-touch. De er gensidigt udelukkende tilstande af ÉT angreb — arket
viser kun den valgte + en ⇄-knap, ikke to samtidige rækker (som fejlagtigt lignede
en two-weapon-straf). Valget gemmes pr. (level,index) i char.spell_modes.
"""
import db
from rules import _spell_attack_rows_to_show
from character import load_character, derive_spell_attacks


def _mk(**over):
    """Tjørn (druid) med produce_flame forberedt på L1 idx 0 — muteret pr. test."""
    c = load_character("defaults/tjorn.yaml")
    c.spells_active = {1: [0]}   # produce_flame "I brug"
    c.spell_modes = {}
    for k, v in over.items():
        setattr(c, k, v)
    return c


def test_grouped_rows_collapse_to_one():
    rows = db.get_spell_attacks("produce_flame")
    shown = _spell_attack_rows_to_show(rows, selected=0)
    assert len(shown) == 1
    row, mode = shown[0]
    assert row["kind"] == "melee_touch"
    assert mode["count"] == 2 and mode["current"] == 0


def test_selected_index_picks_other_mode():
    rows = db.get_spell_attacks("produce_flame")
    row, mode = _spell_attack_rows_to_show(rows, selected=1)[0]
    assert row["kind"] == "ranged_touch"
    assert mode["current"] == 1


def test_out_of_range_selection_clamps():
    rows = db.get_spell_attacks("produce_flame")
    row, mode = _spell_attack_rows_to_show(rows, selected=99)[0]
    assert row["kind"] == "ranged_touch"   # klamper til sidste tilstand
    assert mode["current"] == 1


def test_ungrouped_spell_unaffected():
    rows = db.get_spell_attacks("magic_stone")   # ingen mode_group
    shown = _spell_attack_rows_to_show(rows, selected=0)
    assert len(shown) == 1
    _, mode = shown[0]
    assert mode is None


def test_derive_shows_single_produce_flame_row():
    out = derive_spell_attacks(_mk(), db)
    names = [d["attack"].name for d in out]
    assert names == ["Produce Flame (nærkamp)"]   # kun ÉN række, ikke to
    assert out[0]["mode"]["options"] == [
        "Produce Flame (nærkamp)", "Produce Flame (kastet)"]


def test_derive_respects_saved_mode():
    out = derive_spell_attacks(_mk(spell_modes={"1-0": 1}), db)
    assert [d["attack"].name for d in out] == ["Produce Flame (kastet)"]
    assert out[0]["attack"].kind == "ranged_touch"
