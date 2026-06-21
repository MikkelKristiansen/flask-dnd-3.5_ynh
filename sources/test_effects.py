"""Unit-tests for den mekaniske effekt-motor (resolve_modifiers + cascade).

Kør: python -m pytest test_effects.py   (fra sources/)

Stacking er det fiddly sted hvor det går galt hvis man sjusker — derfor er den
isoleret i resolve_modifiers og dækket grundigt her.
"""
from character import (AbilityScores, effective_ability_scores,
                       resolve_modifiers, save_total, attack_total, Attack,
                       grapple_total, resolve_ac_bonuses, save_effect_bonus,
                       skill_effect_bonus, conditional_modifiers)


def m(target, type, value, **extra):
    return {"target": target, "type": type, "value": value, **extra}


# ── resolve_modifiers: stacking-regler ──────────────────────────────────────

def test_empty():
    assert resolve_modifiers([]) == {}


def test_single():
    assert resolve_modifiers([m("str", "enhancement", 4)]) == {"str": 4}


def test_same_type_does_not_stack_takes_highest():
    # To Bull's Strength = +4, ikke +8 (samme enhancement-type).
    assert resolve_modifiers([
        m("str", "enhancement", 4),
        m("str", "enhancement", 4),
    ]) == {"str": 4}
    # Forskellig størrelse, samme type → den højeste gælder.
    assert resolve_modifiers([
        m("str", "enhancement", 2),
        m("str", "enhancement", 4),
    ]) == {"str": 4}


def test_different_types_stack():
    # Barkskin (natural +2) + Shield of Faith (deflection +2) = +4 på AC.
    assert resolve_modifiers([
        m("ac", "natural", 2),
        m("ac", "deflection", 2),
    ]) == {"ac": 4}


def test_two_dodge_stack():
    assert resolve_modifiers([
        m("ac", "dodge", 1),
        m("ac", "dodge", 1),
    ]) == {"ac": 2}


def test_penalties_stack():
    # Shaken (-2) + en anden straf (-2) = -4 (utypede straffe lægges sammen).
    assert resolve_modifiers([
        m("attack", "penalty", -2),
        m("attack", "penalty", -2),
    ]) == {"attack": -4}


def test_bonus_and_penalty_same_named_type_both_apply():
    # En enhancement-bonus og en enhancement-straf tælles hver for sig.
    assert resolve_modifiers([
        m("str", "enhancement", 4),
        m("str", "enhancement", -2),
    ]) == {"str": 2}


def test_worst_penalty_same_named_type():
    # Samme navngivne type → værste straf gælder (ikke summen).
    assert resolve_modifiers([
        m("dex", "size", -2),
        m("dex", "size", -4),
    ]) == {"dex": -4}


def test_only_vs_excluded():
    # Betingede (only_vs) ryger ikke i overskriftstallet.
    assert resolve_modifiers([
        m("save_will", "morale", 1, only_vs="fear"),
    ]) == {}


def test_zero_and_missing_ignored():
    assert resolve_modifiers([
        m("str", "enhancement", 0),
        {"type": "enhancement", "value": 4},   # mangler target
    ]) == {}


# ── effective_ability_scores: cascade ───────────────────────────────────────

def test_no_modifiers_is_identity():
    base = AbilityScores(str=14, dex=12, con=13, int=10, wis=15, cha=8)
    eff = effective_ability_scores(base, [])
    assert (eff.str, eff.dex, eff.con, eff.int, eff.wis, eff.cha) == (14, 12, 13, 10, 15, 8)


def test_bulls_strength_raises_str():
    base = AbilityScores(str=14)
    eff = effective_ability_scores(base, [m("str", "enhancement", 4)])
    assert eff.str == 18
    assert eff.modifier("str") == 4   # 14→18 = +2 → +4


def test_ability_damage_lowers_and_clamps():
    base = AbilityScores(str=3)
    eff = effective_ability_scores(base, [m("str", "penalty", -6)])
    assert eff.str == 0   # klampet til 0


def test_cascade_into_attack_and_grapple():
    # Bull's Strength skal kaskadere ud i både til-hit, skade og grapple.
    base = AbilityScores(str=14)
    eff = effective_ability_scores(base, [m("str", "enhancement", 4)])  # +2 mod
    weapon = Attack(name="Mace", base_damage="1d8", str_damage_mult=1.0)
    base_atk = attack_total(weapon, base, bab=3, size="medium")
    eff_atk = attack_total(weapon, eff, bab=3, size="medium")
    assert eff_atk["to_hit"] == base_atk["to_hit"] + 2
    assert base_atk["damage"] == "1d8+2"
    assert eff_atk["damage"] == "1d8+4"
    assert grapple_total(3, eff.str, "medium") == grapple_total(3, base.str, "medium") + 2


def test_cascade_into_save():
    # Bear's Endurance (+4 Con) hæver Fortitude-save med +2.
    base = AbilityScores(con=12)
    eff = effective_ability_scores(base, [m("con", "enhancement", 4)])
    assert save_total(2, eff.con) == save_total(2, base.con) + 2


def test_removing_buff_returns_to_base():
    base = AbilityScores(wis=16)
    with_buff = effective_ability_scores(base, [m("wis", "enhancement", 4)])
    without = effective_ability_scores(base, [])
    assert with_buff.wis == 20
    assert without.wis == base.wis == 16


# ── Fase 2: direkte bonusser ────────────────────────────────────────────────

def test_save_effect_bonus_param():
    # Resistance (+1 alle) lægges oveni; uden bonus er det uændret.
    assert save_total(2, 14, 0) == 4
    assert save_total(2, 14, 0, effect_bonus=1) == 5


def test_save_effect_bonus_combines_all_and_specific():
    net = {"save_all": 1, "save_will": 1}
    assert save_effect_bonus(net, "will") == 2
    assert save_effect_bonus(net, "fortitude") == 1


def test_skill_effect_bonus_combines():
    net = {"skill_all": -2, "skill:hide": 5}
    assert skill_effect_bonus(net, "hide") == 3
    assert skill_effect_bonus(net, "spot") == -2


def test_attack_extra_bonus_and_damage():
    s = AbilityScores(str=14)  # +2
    w = Attack(name="Sword", base_damage="1d8", str_damage_mult=1.0)
    # Bless +1 attack, Magic Fang +1 damage → to-hit +1, skade +1 oveni Str.
    r = attack_total(w, s, bab=2, size="medium", extra_bonus=1, extra_damage=1)
    assert r["to_hit"] == 2 + 2 + 0 + 0 + 1          # bab + str + size + bonus + extra
    assert r["damage"] == "1d8+3"                    # +2 Str +1 extra


def test_attack_extra_damage_skips_fixed():
    # Spell-angreb (fixed_damage) får ikke våben-skade-bonus.
    s = AbilityScores(str=14)
    spell = Attack(name="Flame", fixed_damage="1d6+2", str_damage_mult=0, source="spell")
    r = attack_total(spell, s, bab=2, size="medium", extra_bonus=1, extra_damage=2)
    assert r["damage"] == "1d6+2"                     # uændret
    assert r["to_hit"] == 2 + 2 + 1                   # to-hit får dog extra_bonus


def test_resolve_ac_natural_and_deflection_stack():
    # Barkskin (natural +2) + Shield of Faith (deflection +2) = begge tæller.
    combat = {"natural": 0, "deflection": 0, "dodge": 0, "misc": 0}
    mods = [{"target": "ac", "type": "natural", "value": 2},
            {"target": "ac", "type": "deflection", "value": 2}]
    out = resolve_ac_bonuses(combat, mods)
    assert out["natural"] == 2 and out["deflection"] == 2


def test_resolve_ac_same_deflection_does_not_stack():
    # Et deflection-item (combat) + Shield of Faith (deflection) → kun den højeste.
    combat = {"natural": 0, "deflection": 3, "dodge": 0, "misc": 0}
    mods = [{"target": "ac", "type": "deflection", "value": 2}]
    out = resolve_ac_bonuses(combat, mods)
    assert out["deflection"] == 3


def test_resolve_ac_dodge_stacks():
    combat = {"natural": 0, "deflection": 0, "dodge": 1, "misc": 0}
    mods = [{"target": "ac", "type": "dodge", "value": 1}]
    out = resolve_ac_bonuses(combat, mods)
    assert out["dodge"] == 2


def test_resolve_ac_unknown_type_goes_to_misc():
    combat = {"natural": 0, "deflection": 0, "dodge": 0, "misc": 1}
    mods = [{"target": "ac", "type": "luck", "value": 2}]
    out = resolve_ac_bonuses(combat, mods)
    assert out["misc"] == 3   # untyped 1 + luck 2 (forskellige typer stacker)


def test_conditional_modifiers_extracted():
    mods = [m("attack", "morale", 1),
            m("save_will", "morale", 1, only_vs="fear")]
    cond = conditional_modifiers(mods)
    assert len(cond) == 1 and cond[0]["only_vs"] == "fear"
    # …og den betingede ryger IKKE i nettotallet.
    assert resolve_modifiers(mods) == {"attack": 1}
