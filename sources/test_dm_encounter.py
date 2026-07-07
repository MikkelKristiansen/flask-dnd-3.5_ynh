"""Tests for dm_encounter — ren kamp-logik (ingen I/O, terning injiceret)."""
import dm_encounter as E


def test_excel_col_overflow():
    assert E._excel_col(0) == "A"
    assert E._excel_col(25) == "Z"
    assert E._excel_col(26) == "AA"      # robust ud over 26 ens monstre
    assert E._excel_col(27) == "AB"


def test_single_creature_keeps_plain_name():
    c = E.build_combatants([{"name": "Skelet", "count": 1, "ref": "skelet",
                             "kind": "monster", "init_mod": 5, "hp_max": 6}])
    assert len(c) == 1
    assert c[0]["name"] == "Skelet" and c[0]["id"] == "skelet"


def test_multiple_identical_get_letters():
    c = E.build_combatants([{"name": "Kriger", "count": 3, "ref": "kriger",
                             "kind": "monster", "init_mod": 0, "hp_max": 8}])
    assert [x["name"] for x in c] == ["Kriger A", "Kriger B", "Kriger C"]
    assert [x["id"] for x in c] == ["kriger-a", "kriger-b", "kriger-c"]
    # hver instans har sin egen HP-pulje
    assert all(x["current_hp"] == 8 for x in c)


def test_lettering_counts_across_sources():
    # Én kriger i roster + én kriger i et rum = 2 krigere i alt → skal have bogstaver
    c = E.build_combatants([
        {"name": "Kriger", "count": 1, "ref": "kriger", "init_mod": 0, "hp_max": 8},
        {"name": "Skelet", "count": 1, "ref": "skelet", "init_mod": 5, "hp_max": 6},
        {"name": "Kriger", "count": 1, "ref": "kriger", "init_mod": 0, "hp_max": 8},
    ])
    names = [x["name"] for x in c]
    assert names.count("Kriger A") == 1 and names.count("Kriger B") == 1
    assert "Skelet" in names          # enlig skelet → intet bogstav


def test_roll_initiative_uses_injected_roller():
    c = E.build_combatants([{"name": "Ulv", "count": 2, "ref": "ulv",
                             "init_mod": 2, "hp_max": 13}])
    E.roll_initiative(c, roller=lambda mod: 10 + mod)
    assert all(x["initiative"] == 12 for x in c)


def test_roll_initiative_only_missing_preserves_manual():
    c = E.build_combatants([{"name": "Tjørn", "count": 1, "ref": "tjorn",
                             "kind": "pc", "init_mod": 1, "hp_max": 24}])
    c[0]["initiative"] = 17                      # spiller har selv rullet
    E.roll_initiative(c, roller=lambda mod: 3, only_missing=True)
    assert c[0]["initiative"] == 17              # ikke overskrevet


def test_turn_order_by_initiative_then_mod():
    combs = [
        {"id": "a", "name": "A", "initiative": 15, "init_mod": 1},
        {"id": "b", "name": "B", "initiative": 20, "init_mod": 0},
        {"id": "c", "name": "C", "initiative": 15, "init_mod": 4},   # tie 15 → højere mod først
    ]
    assert E.turn_order(combs) == ["b", "c", "a"]


def test_advance_wraps_to_new_round():
    assert E.advance(1, 0, 3) == (1, 1)
    assert E.advance(1, 2, 3) == (2, 0)          # sidste tur → ny runde
    assert E.advance(5, 0, 0) == (5, 0)          # tom encounter rører ikke tælleren


def test_seed_positions_binds_by_instance_letter():
    combs = E.build_combatants([
        {"name": "Kriger", "count": 2, "ref": "kriger", "kind": "monster",
         "init_mod": 0, "hp_max": 8},
        {"name": "Tjørn", "count": 1, "ref": "tjorn", "kind": "pc",
         "init_mod": 0, "hp_max": 24}])
    tokens = [
        {"kind": "monster", "ref": "kriger", "label": "A", "col": 6, "row": 3},
        {"kind": "monster", "ref": "kriger", "label": "B", "col": 7, "row": 3},
        {"kind": "pc", "ref": "tjorn", "col": 2, "row": 8},
        {"kind": "trap", "ref": "spyd", "col": 5, "row": 1},   # markør ignoreres
    ]
    E.seed_positions(combs, tokens)
    by = {c["id"]: c for c in combs}
    assert (by["kriger-a"]["col"], by["kriger-a"]["row"]) == (6, 3)
    assert (by["kriger-b"]["col"], by["kriger-b"]["row"]) == (7, 3)
    assert (by["tjorn"]["col"], by["tjorn"]["row"]) == (2, 8)


def test_seed_positions_next_free_when_no_letter_match_and_no_token_ok():
    combs = E.build_combatants([
        {"name": "Ulv", "count": 2, "ref": "ulv", "init_mod": 0, "hp_max": 13}])
    # DM placerede kun ÉN ulv-token (uden bogstav) + ingen for kriger
    E.seed_positions(combs, [{"kind": "monster", "ref": "ulv", "col": 4, "row": 4}])
    a, b = combs
    assert (a["col"], a["row"]) == (4, 4)          # første ulv tager den ledige token
    assert "col" not in b                           # anden ulv står uden for brættet
