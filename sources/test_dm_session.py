"""Tests for dm_session — session-persistens + eventyr-adgang. Hermetisk:
ADVENTURES_DIR/SESSIONS_DIR peges mod tmp_path."""
import pytest

import dm_session as S

MINI = """---
title: Testeventyr
party: [tjorn]
---
# Første scene
Tekst.
# Anden scene
Mere tekst.
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    adv = tmp_path / "adventures"
    (adv / "Test-Eventyr").mkdir(parents=True)
    (adv / "Test-Eventyr" / "adventure.md").write_text(MINI, encoding="utf-8")
    (adv / "_TEMPLATE").mkdir()
    (adv / "_TEMPLATE" / "adventure.md").write_text("# X\n", encoding="utf-8")
    monkeypatch.setattr(S, "ADVENTURES_DIR", adv)
    monkeypatch.setattr(S, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path


def test_list_adventures_hides_template(env):
    assert S.list_adventures() == ["Test-Eventyr"]


def test_load_adventure(env):
    adv = S.load_adventure("Test-Eventyr")
    assert [s.id for s in adv.scenes] == ["foerste-scene", "anden-scene"]


def test_load_adventure_missing(env):
    with pytest.raises(FileNotFoundError):
        S.load_adventure("findes-ikke")


def test_create_defaults_to_first_scene(env):
    s = S.create_session("Min kampagne", "Test-Eventyr", ["tjorn", "faelyn"])
    assert s.adventure == "Test-Eventyr"
    assert s.party == ["tjorn", "faelyn"]
    assert s.active_scene == "foerste-scene"
    assert s.slug == "min-kampagne"


def test_create_missing_adventure_raises(env):
    with pytest.raises(FileNotFoundError):
        S.create_session("K", "findes-ikke")


def test_roundtrip_persists_only_mutable_state(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    assert S.load_session(s.slug).to_dict() == s.to_dict()
    raw = (env / "sessions" / f"{s.slug}.yaml").read_text(encoding="utf-8")
    # kun mutabel tilstand — INTET parset eventyr
    assert "active_scene" in raw and "adventure" in raw
    assert "scenes" not in raw and "blocks" not in raw


def test_create_adventure_writes_starter(env):
    ref = S.create_adventure("Ny Kampagne")
    assert ref == "Ny-Kampagne"                            # mellemrum → bindestreg
    assert "title: Ny Kampagne" in S.read_adventure_source(ref)
    assert S.load_adventure(ref).scenes                    # skelettet parser
    with pytest.raises(FileExistsError):
        S.create_adventure("Ny Kampagne")                  # dublet afvises
    with pytest.raises(ValueError):
        S.create_adventure("   ")                          # tomt navn afvises


def test_create_adventure_keeps_danish_letters(env):
    ref = S.create_adventure("Ødemarken")
    assert ref == "Ødemarken"                              # æøå bevares i mappenavnet
    assert ref in S.list_adventures()


def test_unique_slug(env):
    a = S.create_session("Samme navn", "Test-Eventyr")
    b = S.create_session("Samme navn", "Test-Eventyr")
    assert {a.slug, b.slug} == {"samme-navn", "samme-navn-2"}


def test_list_sessions(env):
    S.create_session("Alpha", "Test-Eventyr")
    S.create_session("Beta", "Test-Eventyr")
    assert {r["name"] for r in S.list_sessions()} == {"Alpha", "Beta"}


def test_goto_scene(env):
    s = S.create_session("K", "Test-Eventyr")
    S.goto_scene(s.slug, "anden-scene")
    assert S.load_session(s.slug).active_scene == "anden-scene"


def test_goto_scene_invalid(env):
    s = S.create_session("K", "Test-Eventyr")
    with pytest.raises(ValueError):
        S.goto_scene(s.slug, "findes-ikke")


def test_delete_session(env):
    s = S.create_session("K", "Test-Eventyr")
    S.delete_session(s.slug)
    with pytest.raises(FileNotFoundError):
        S.load_session(s.slug)
    assert S.list_sessions() == []


# ── Encounter-tilstand ───────────────────────────────────────────────────────
import dm_encounter as E


def _combatants():
    c = E.build_combatants([
        {"name": "Kriger", "count": 2, "ref": "kriger", "kind": "monster",
         "init_mod": 1, "hp_max": 8},
        {"name": "Tjørn", "count": 1, "ref": "tjorn", "kind": "pc",
         "init_mod": 3, "hp_max": 24},
    ])
    E.roll_initiative(c, roller=lambda mod: 10 + mod)   # deterministisk
    return c


def test_begin_encounter_persists_and_orders(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    S.begin_encounter(s.slug, _combatants())
    enc = S.load_session(s.slug).encounter
    assert enc["active"] and enc["round"] == 1 and enc["turn_index"] == 0
    # Tjørn (init 13) før krigerne (init 11) i rækkefølgen
    assert enc["turn_order"][0] == "tjorn"
    assert set(enc["turn_order"]) == {"tjorn", "kriger-a", "kriger-b"}


def test_next_turn_advances_and_wraps(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    S.begin_encounter(s.slug, _combatants())
    S.next_turn(s.slug); S.next_turn(s.slug)
    e = S.load_session(s.slug).encounter
    assert e["round"] == 1 and e["turn_index"] == 2
    S.next_turn(s.slug)                                  # 3 combatants → wrap
    e = S.load_session(s.slug).encounter
    assert e["round"] == 2 and e["turn_index"] == 0


def test_set_hp_and_toggle_condition_persist(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    S.begin_encounter(s.slug, _combatants())
    S.set_combatant_hp(s.slug, "kriger-a", 3)
    S.toggle_condition(s.slug, "kriger-a", "prone")
    c = next(x for x in S.load_session(s.slug).encounter["combatants"]
             if x["id"] == "kriger-a")
    assert c["current_hp"] == 3 and c["conditions"] == ["prone"]
    S.toggle_condition(s.slug, "kriger-a", "prone")      # slår fra igen
    c = next(x for x in S.load_session(s.slug).encounter["combatants"]
             if x["id"] == "kriger-a")
    assert c["conditions"] == []


def test_end_encounter_clears(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    S.begin_encounter(s.slug, _combatants())
    S.end_encounter(s.slug)
    assert S.load_session(s.slug).encounter == {}


def test_begin_encounter_seeds_positions_from_setup(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    tokens = [{"kind": "monster", "ref": "kriger", "label": "A", "col": 6, "row": 3},
              {"kind": "pc", "ref": "tjorn", "col": 2, "row": 8}]
    S.begin_encounter(s.slug, _combatants(), tokens)
    by = {c["id"]: c for c in S.load_session(s.slug).encounter["combatants"]}
    assert (by["kriger-a"]["col"], by["kriger-a"]["row"]) == (6, 3)
    assert (by["tjorn"]["col"], by["tjorn"]["row"]) == (2, 8)


def test_set_combatant_position_persists_and_is_live_only(env):
    s = S.create_session("K", "Test-Eventyr", ["tjorn"])
    S.begin_encounter(s.slug, _combatants())
    S.set_combatant_position(s.slug, "kriger-a", 9, 4)
    c = next(x for x in S.load_session(s.slug).encounter["combatants"]
             if x["id"] == "kriger-a")
    assert (c["col"], c["row"]) == (9, 4)
    # uden aktiv kamp gør flyt intet
    S.end_encounter(s.slug)
    S.set_combatant_position(s.slug, "kriger-a", 1, 1)
    assert S.load_session(s.slug).encounter == {}
