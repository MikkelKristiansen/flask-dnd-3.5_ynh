"""Unit-tests for spell_cast_info — ⚡ Kast-knappens data.

Kør: python -m pytest test_spell_cast_info.py   (fra sources/)

Øjeblikkelige angrebsspells (Magic Missile o.l.) har ingen "I brug"-tilstand, så de
kastes direkte via Kast-knappen: rul skade + brug slot. spell_cast_info() leverer
skade-udtrykket (skaleret med antal missiler) knappen sætter i terningefeltet.
Save/område-spells og self_duration/summon-spells får INGEN Kast-knap (None).
"""
import db
from spells import multiply_damage, spell_cast_info, spell_save_cast_info


def test_multiply_damage_scales_dice_and_bonus():
    assert multiply_damage("1d4+1", 3) == "3d4+3"   # Magic Missile CL5: 3 missiler
    assert multiply_damage("4d6", 2) == "8d6"        # Scorching Ray CL7: 2 stråler
    assert multiply_damage("1d4+1", 1) == "1d4+1"    # ét skud → uændret
    assert multiply_damage("", 2) == ""              # tom → uændret


def test_magic_missile_level_1():
    info = spell_cast_info("magic_missile", 1, db)
    assert info["kind"] == "attack"
    assert info["auto_hit"] is True
    assert info["shots"] == 1
    assert info["damage"] == "1d4+1"
    assert info["roll_expr"] == "1d4+1"


def test_magic_missile_level_3_two_missiles():
    info = spell_cast_info("magic_missile", 3, db)
    assert info["shots"] == 2
    assert info["roll_expr"] == "2d4+2"


def test_scorching_ray_not_auto_hit():
    info = spell_cast_info("scorching_ray", 3, db)
    assert info is not None
    assert info["auto_hit"] is False


def test_non_attack_spell_has_no_cast_button():
    # Mage Armor er en self_duration-buff uden angrebs-række → ingen Kast-knap.
    assert spell_cast_info("mage_armor", 1, db) is None


# ── Kategori E: område/save-spells (Fireball, Sleep) ────────────────────────

def test_fireball_save_cast_scales_dice():
    # spell_cast_info (kategori B) rører ikke save-spells.
    assert spell_cast_info("fireball", 5, db) is None
    info = spell_save_cast_info("fireball", 5, db)
    assert info["kind"] == "save"
    assert info["damage"] == "5d6"          # 1d6/niveau, cappet ved 10
    assert info["save_type"] == "reflex"
    assert info["save_effect"] == "half"
    # DC lægges IKKE på her (kræver caster-mod + focus fra view-laget).
    assert "dc" not in info


def test_fireball_damage_caps_at_ten_dice():
    assert spell_save_cast_info("fireball", 12, db)["damage"] == "10d6"


def test_sleep_is_save_only_no_damage():
    info = spell_save_cast_info("sleep", 5, db)
    assert info["kind"] == "save"
    assert info["damage"] == ""             # ren save-effekt → intet at rulle
    assert info["save_type"] == "will"
    assert info["save_effect"] == "negates"


def test_attack_spell_has_no_save_cast():
    # Magic Missile er kategori B, ikke E.
    assert spell_save_cast_info("magic_missile", 1, db) is None
