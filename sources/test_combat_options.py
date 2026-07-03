"""Unit-tests for Kampindstillinger (Lag A + Lag B): combat_options.py.

Kør: python -m pytest test_combat_options.py   (fra sources/)

Dækker: feat-gating af aktive toggles, panel-synlighed, at de scope'ede
targets (attack_melee/ranged, damage_melee/ranged) rammer det rigtige angreb
uden at blande sig (Lag A) — og de redigerbare options Power Attack/Combat
Expertise: talinput, parrede modifiers, BAB-cap, tohånds-dobling (Lag B).
Se test_effects.py for stil/fixtures.
"""
from types import SimpleNamespace

import combat_options
from character import Attack, AbilityScores, attack_total, resolve_modifiers
from persistence import load_character


def _char(**opts):
    return SimpleNamespace(combat_options=opts)


_MIN_YAML = """
name: Test
hp: {current: 10, max: 10}
ability_scores: {str: 14, dex: 12, con: 12, int: 10, wis: 10, cha: 10}
combat_options:
  power_attack: 3
  power_attack.two_handed: true
  dodge: true
"""


def test_load_character_preserves_editable_int_value(tmp_path):
    # Regression: persistence.load_character coercede TIDLIGERE alle
    # combat_options-værdier til bool ved indlæsning — det ville nulstille
    # Power Attacks gemte N til True ved hvert side-load. N (heltal) og bool
    # skal begge overleve rundturen uændret.
    p = tmp_path / "char.yaml"
    p.write_text(_MIN_YAML)
    char = load_character(str(p))
    assert char.combat_options["power_attack"] == 3
    assert char.combat_options["power_attack"] is not True
    assert char.combat_options["power_attack.two_handed"] is True
    assert char.combat_options["dodge"] is True


# ── active_modifiers: feat-gate ─────────────────────────────────────────────

def test_feat_gated_option_excluded_without_feat():
    char = _char(point_blank_shot=True)
    assert combat_options.active_modifiers(char, []) == []


def test_feat_gated_option_included_with_feat():
    char = _char(point_blank_shot=True)
    mods = combat_options.active_modifiers(char, ["point_blank_shot"])
    targets = {m["target"] for m in mods}
    assert targets == {"attack_ranged", "damage_ranged"}
    assert all(m["value"] == 1 for m in mods)


def test_dodge_feat_gated():
    char = _char(dodge=True)
    assert combat_options.active_modifiers(char, []) == []
    mods = combat_options.active_modifiers(char, ["dodge"])
    assert mods == [{"target": "ac", "type": "dodge", "value": 1}]


def test_generic_option_always_included_regardless_of_feats():
    # Charge/Fighting Defensively er ikke feat-gated — alle kan bruge dem.
    char = _char(charge=True)
    mods = combat_options.active_modifiers(char, [])
    assert {m["target"]: m["value"] for m in mods} == {"attack": 2, "ac": -2}


def test_fighting_defensively_generic():
    char = _char(fighting_defensively=True)
    mods = combat_options.active_modifiers(char, [])
    assert {m["target"]: m["value"] for m in mods} == {"attack": -4, "ac": 2}


def test_inactive_toggle_contributes_nothing():
    char = _char(point_blank_shot=False)
    assert combat_options.active_modifiers(char, ["point_blank_shot"]) == []


def test_unknown_option_id_ignored():
    # Fx en gammel/fjernet option-id liggende i en karakterfil — skal ikke crashe.
    char = _char(some_removed_option=True)
    assert combat_options.active_modifiers(char, []) == []


# ── panel: synlighed ────────────────────────────────────────────────────────

def test_panel_hides_feat_gated_option_without_feat():
    char = _char()
    rows = combat_options.panel(char, [])
    ids = {r["id"] for r in rows}
    assert "point_blank_shot" not in ids
    assert "dodge" not in ids
    # Generiske handlinger vises altid.
    assert {"charge", "fighting_defensively"} <= ids


def test_panel_shows_feat_gated_option_with_feat_and_reflects_on_state():
    char = _char(point_blank_shot=True)
    rows = combat_options.panel(char, ["point_blank_shot"])
    row = next(r for r in rows if r["id"] == "point_blank_shot")
    assert row["on"] is True
    assert row["label"]
    assert row["note"]


def test_panel_off_when_not_toggled():
    char = _char()
    rows = combat_options.panel(char, ["dodge"])
    row = next(r for r in rows if r["id"] == "dodge")
    assert row["on"] is False


# ── resolve_modifiers: scoped targets holdes adskilt ────────────────────────

def test_resolve_modifiers_keeps_melee_and_ranged_separate():
    net = resolve_modifiers([
        {"target": "attack_melee", "type": "untyped", "value": 2},
        {"target": "attack_ranged", "type": "untyped", "value": 1},
        {"target": "damage_melee", "type": "untyped", "value": 3},
    ])
    assert net == {"attack_melee": 2, "attack_ranged": 1, "damage_melee": 3}
    assert "attack" not in net   # den globale nøgle må ikke opstå af sig selv


# ── Scope-mekanik: en ranged-scoped bonus rammer kun ranged-angreb ──────────

def test_ranged_scope_hits_ranged_not_melee():
    char = _char(point_blank_shot=True)
    mods = combat_options.active_modifiers(char, ["point_blank_shot"])
    net = resolve_modifiers(mods)

    ab = AbilityScores(str=14, dex=14)
    bow = Attack(name="Longbow", kind="ranged", base_damage="1d8", str_damage_mult=0)
    sword = Attack(name="Longsword", kind="melee", base_damage="1d8", str_damage_mult=1.0)

    r_bow = attack_total(bow, ab, bab=1, size="medium",
                         extra_bonus=net.get("attack_ranged", 0),
                         extra_damage=net.get("damage_ranged", 0))
    base_bow = attack_total(bow, ab, bab=1, size="medium")
    assert r_bow["to_hit"] == base_bow["to_hit"] + 1
    assert r_bow["damage"] == "1d8+1"

    # Samme net brugt på et melee-angreb via de MELEE-nøglerne (som er tomme her)
    # — Point Blank Shot må ikke røre nærkamp.
    r_sword = attack_total(sword, ab, bab=1, size="medium",
                           extra_bonus=net.get("attack_melee", 0),
                           extra_damage=net.get("damage_melee", 0))
    base_sword = attack_total(sword, ab, bab=1, size="medium")
    assert r_sword["to_hit"] == base_sword["to_hit"]
    assert r_sword["damage"] == base_sword["damage"]


def test_melee_scope_does_not_leak_into_ranged():
    # Ren scope-test uden feat-gate: en fiktiv melee-scoped modifier må kun
    # ramme melee-nøglen i net, aldrig ranged.
    net = resolve_modifiers([{"target": "attack_melee", "type": "untyped", "value": 2}])
    ab = AbilityScores(str=14, dex=14)
    bow = Attack(name="Longbow", kind="ranged", base_damage="1d8", str_damage_mult=0)
    r_bow = attack_total(bow, ab, bab=1, size="medium",
                         extra_bonus=net.get("attack_ranged", 0))
    base_bow = attack_total(bow, ab, bab=1, size="medium")
    assert r_bow["to_hit"] == base_bow["to_hit"]   # uændret — melee-bonus lækker ikke


# ── Lag B: Power Attack (editable + paired + tohånds) ───────────────────────

def test_power_attack_n3_basic():
    char = _char(power_attack=3)
    mods = combat_options.active_modifiers(char, ["power_attack"], bab=5)
    net = resolve_modifiers(mods)
    assert net["attack_melee"] == -3
    assert net["damage_melee"] == 3


def test_power_attack_n3_two_handed_doubles_damage():
    char = _char(**{"power_attack": 3, "power_attack.two_handed": True})
    mods = combat_options.active_modifiers(char, ["power_attack"], bab=5)
    net = resolve_modifiers(mods)
    assert net["attack_melee"] == -3   # attack uændret af tohånds
    assert net["damage_melee"] == 6    # 2N: +N fra paired, +N fra toggles.extra


def test_power_attack_caps_to_bab():
    char = _char(power_attack=10)
    mods = combat_options.active_modifiers(char, ["power_attack"], bab=4)
    net = resolve_modifiers(mods)
    assert net["attack_melee"] == -4
    assert net["damage_melee"] == 4


def test_power_attack_two_handed_flag_without_active_power_attack_contributes_nothing():
    # Tohånds-flag'et uden N ≥ 1 (Power Attack slukket) må ikke give noget.
    char = _char(**{"power_attack.two_handed": True})
    mods = combat_options.active_modifiers(char, ["power_attack"], bab=5)
    assert mods == []


def test_power_attack_off_contributes_nothing():
    char = _char(power_attack=0)
    assert combat_options.active_modifiers(char, ["power_attack"], bab=5) == []
    char2 = _char()
    assert combat_options.active_modifiers(char2, ["power_attack"], bab=5) == []


def test_power_attack_feat_gated():
    char = _char(power_attack=3)
    assert combat_options.active_modifiers(char, [], bab=5) == []


# ── Lag B: Combat Expertise (editable + paired, rammer AC ikke skade) ──────

def test_combat_expertise_n2():
    char = _char(combat_expertise=2)
    mods = combat_options.active_modifiers(char, ["combat_expertise"], bab=5)
    net = resolve_modifiers(mods)
    assert net["attack_melee"] == -2
    assert net["ac"] == 2
    assert "damage_melee" not in net


def test_combat_expertise_caps_to_5():
    char = _char(combat_expertise=10)
    mods = combat_options.active_modifiers(char, ["combat_expertise"], bab=20)
    net = resolve_modifiers(mods)
    assert net["attack_melee"] == -5
    assert net["ac"] == 5


def test_combat_expertise_feat_gated():
    char = _char(combat_expertise=3)
    assert combat_options.active_modifiers(char, [], bab=5) == []


# ── Lag B: panel view-model for editable options ────────────────────────────

def test_panel_power_attack_editable_shape():
    char = _char(**{"power_attack": 3, "power_attack.two_handed": True})
    rows = combat_options.panel(char, ["power_attack"], bab=4)
    row = next(r for r in rows if r["id"] == "power_attack")
    assert row["editable"] is True
    assert row["value"] == 3
    assert row["cap"] == 4          # "bab"-sentinel opløst til heltal
    assert row["min"] == 1
    assert row["prompt"]
    toggles = {t["name"]: t["on"] for t in row["toggles"]}
    assert toggles == {"two_handed": True}


def test_panel_combat_expertise_editable_cap_is_fixed_five():
    char = _char(combat_expertise=2)
    rows = combat_options.panel(char, ["combat_expertise"], bab=20)
    row = next(r for r in rows if r["id"] == "combat_expertise")
    assert row["editable"] is True
    assert row["value"] == 2
    assert row["cap"] == 5   # fast tal, ikke bab-sentinel


def test_panel_power_attack_hidden_without_feat():
    char = _char()
    rows = combat_options.panel(char, [], bab=4)
    ids = {r["id"] for r in rows}
    assert "power_attack" not in ids
    assert "combat_expertise" not in ids


def test_panel_namespaced_toggle_key_is_not_its_own_row():
    char = _char(**{"power_attack": 2, "power_attack.two_handed": True})
    rows = combat_options.panel(char, ["power_attack"], bab=5)
    ids = {r["id"] for r in rows}
    assert "power_attack.two_handed" not in ids
