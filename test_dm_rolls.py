"""Tests for dm_rolls — condition-straffe foldet ind i en monster-combatants rul.

db er injiceret som en fake (get_effect), så testene er deterministiske og ikke
afhænger af data/effects.yaml's indhold — samme mønster som dm_encounter's
injicerede terning."""
import dm_rolls as R


class FakeDB:
    """Minimalt effekt-katalog: id → {name, kind, modifiers}."""
    def __init__(self, effects):
        self._e = effects

    def get_effect(self, eid):
        return self._e.get(eid)


# Ét statblok-view (bestiary.monster_view-form): Str 14 (+2), Dex 12 (+1).
def _mob():
    return {
        "abilities": [{"key": "str", "score": 14}, {"key": "dex", "score": 12},
                      {"key": "con", "score": 13}, {"key": "wis", "score": 10}],
        "attacks": [
            {"name": "Sværd", "bonus": "+3", "damage": "1d8+2", "crit": "19-20",
             "notes": "nærkamp"},
            {"name": "Bue", "bonus": "+2", "damage": "1d6", "notes": "afstand"},
        ],
        "saves": {"fort": 4, "ref": 1, "will": 0},
    }


def test_no_conditions_leaves_everything_unchanged():
    r = R.combatant_rolls(_mob(), [], FakeDB({}))
    assert r["modified"] is False and r["sources"] == []
    assert r["attacks"][0]["hit_expr"] == "1d20+3"
    assert r["attacks"][0]["dmg_expr"] == "1d8+2"
    assert r["saves"]["fort"]["expr"] == "1d20+4"


def test_shaken_folds_attack_and_saves_not_damage():
    db = FakeDB({"shaken": {"name": "Shaken", "kind": "condition", "modifiers": [
        {"target": "attack", "type": "penalty", "value": -2},
        {"target": "save_all", "type": "penalty", "value": -2}]}})
    r = R.combatant_rolls(_mob(), ["shaken"], db)
    assert r["modified"] is True and r["sources"] == ["Shaken"]
    assert r["attacks"][0]["hit_expr"] == "1d20+1"      # +3 − 2
    assert r["attacks"][0]["dmg_expr"] == "1d8+2"       # skade urørt
    assert r["saves"]["ref"]["expr"] == "1d20-1"        # +1 − 2


def test_sickened_also_folds_damage():
    db = FakeDB({"sickened": {"name": "Sickened", "kind": "condition", "modifiers": [
        {"target": "attack", "type": "penalty", "value": -2},
        {"target": "damage", "type": "penalty", "value": -2}]}})
    r = R.combatant_rolls(_mob(), ["sickened"], db)
    assert r["attacks"][0]["dmg_expr"] == "1d8"         # +2 − 2 = 0 → led udeladt


def test_ability_penalty_translates_via_monster_scores():
    # Str 14 (+2) − 2 = Str 12 (+1) → −1 på nærkamp-hit OG -skade; ranged urørt af Str.
    db = FakeDB({"fatigued": {"name": "Fatigued", "kind": "condition", "modifiers": [
        {"target": "str", "type": "penalty", "value": -2}]}})
    r = R.combatant_rolls(_mob(), ["fatigued"], db)
    assert r["attacks"][0]["hit_expr"] == "1d20+2"      # nærkamp +3 − 1
    assert r["attacks"][0]["dmg_expr"] == "1d8+1"       # skade +2 − 1
    assert r["attacks"][1]["hit_expr"] == "1d20+2"      # bue: Str rører ikke ranged


def test_melee_only_penalty_skips_ranged():
    db = FakeDB({"prone": {"name": "Prone", "kind": "condition", "modifiers": [
        {"target": "attack_melee", "type": "penalty", "value": -4}]}})
    r = R.combatant_rolls(_mob(), ["prone"], db)
    assert r["attacks"][0]["hit_expr"] == "1d20-1"      # nærkamp +3 − 4
    assert r["attacks"][1]["hit_expr"] == "1d20+2"      # bue uændret


def test_ac_only_condition_is_not_marked_modified():
    db = FakeDB({"blinded": {"name": "Blinded", "kind": "condition", "modifiers": [
        {"target": "ac", "type": "penalty", "value": -2}]}})
    r = R.combatant_rolls(_mob(), ["blinded"], db)
    assert r["modified"] is False and r["sources"] == []
    assert r["attacks"][0]["hit_expr"] == "1d20+3"      # rul urørt


def test_penalties_stack():
    db = FakeDB({
        "shaken": {"name": "Shaken", "kind": "condition", "modifiers": [
            {"target": "attack", "type": "penalty", "value": -2}]},
        "dazzled": {"name": "Dazzled", "kind": "condition", "modifiers": [
            {"target": "attack", "type": "penalty", "value": -1}]}})
    r = R.combatant_rolls(_mob(), ["shaken", "dazzled"], db)
    assert r["attacks"][0]["hit_expr"] == "1d20+0"      # +3 − 2 − 1 (utypede stakker)
    assert set(r["sources"]) == {"Shaken", "Dazzled"}
