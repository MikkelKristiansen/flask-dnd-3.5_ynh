"""Unit-tests for summon-motoren (summon.py).

Kør: python -m pytest test_summon.py   (fra sources/)

To ting verificeres: (1) at de FASTE statblokke matcher SRD for hver væsen-type
(animal ¾ BAB, magical_beast fuld BAB, fey ½ BAB, elementaler/dire-saves, d10/d6
hit-die, Toughness-HP), og (2) at Augment Summoning kaskaderer korrekt (+4 Str/Con
→ HP og skade stiger). Bruger det rigtige katalog (srd35.db) som kilde.
"""
import pathlib
import shutil

import character as char_module
import db
import summon


def stat(creature_id, **ref):
    return summon.build_summon({"creature": creature_id, **ref}, db)


def primary(s):
    return s["attacks"][0]


# ── Faste statblokke pr. væsen-type (matcher SRD-printet) ───────────────────

def test_dire_wolf_animal():
    # Animal: ¾ BAB. Dire-dyr har god Will. Weapon Focus (Bite).
    s = stat("dire_wolf")
    assert s["hp_max"] == 45
    assert s["ac"]["ac"] == 14
    assert primary(s)["to_hit"] == 11          # bab4 −1 size +7 str +1 focus
    assert primary(s)["damage"] == "1d8+10"    # eneste primære → ×1,5 str
    assert s["saves"] == {"fort": 8, "ref": 7, "will": 6}


def test_hippogriff_magical_beast_full_bab():
    # Magical beast: BAB = HD (fuld), hit_die d10.
    s = stat("hippogriff")
    assert s["hp_max"] == 25
    assert s["ac"]["ac"] == 15
    assert primary(s)["to_hit"] == 6           # bab3 −1 size +4 str
    assert s["saves"] == {"fort": 6, "ref": 5, "will": 2}


def test_satyr_fey_half_bab():
    # Fey: BAB = ½·HD, hit_die d6, god Ref+Will.
    s = stat("satyr")
    assert s["hp_max"] == 22
    assert primary(s)["to_hit"] == 2           # bab2 (5//2) +0 str
    assert s["saves"] == {"fort": 2, "ref": 5, "will": 5}


def test_outsider_full_bab():
    # Outsider: BAB = HD (fuld), som magical_beast. Fey ½, animal/elemental ¾.
    assert summon._bab("outsider", 8) == 8
    assert summon._bab("magical_beast", 8) == 8
    assert summon._bab("animal", 8) == 6
    assert summon._bab("fey", 8) == 4


def test_iron_will_adds_to_save():
    # Save-boostende feat: Dire Boar har Iron Will → +2 Will oven på god Will.
    # God Will (7 HD) = 5 + Wis1 = 6; +2 Iron Will = 8 (matcher SRD).
    s = stat("dire_boar")
    assert s["saves"] == {"fort": 8, "ref": 5, "will": 8}


def test_fire_elemental_save_profile():
    # Elemental med eksplicit good_saves ["ref"]: Ref god, Fort+Will dårlige.
    s = stat("elemental_fire_small")
    assert s["hp_max"] == 9
    assert s["ac"]["ac"] == 15
    assert primary(s)["to_hit"] == 3           # bab1 +1 size +1 dex (finesse)
    assert s["saves"] == {"fort": 0, "ref": 4, "will": 0}


def test_huge_air_elemental_finesse():
    # Huge Air (16 HD): Weapon Finesse → til-hit bruger Dex. ¾ BAB, good Ref.
    s = stat("elemental_air_huge")
    assert s["hp_max"] == 136                    # avg 4.5×16 + Con4×16
    assert primary(s)["to_hit"] == 19            # bab12 −2 size +9 dex (finesse)
    assert primary(s)["damage"] == "2d8+4"       # 2 slams → fuld Str4
    assert s["saves"] == {"fort": 9, "ref": 19, "will": 5}


def test_elder_water_elemental():
    # Elder Water (24 HD): ingen finesse → Str-til-hit; Iron Will + good Fort.
    s = stat("elemental_water_elder")
    assert s["hp_max"] == 228                    # avg 4.5×24 + Con5×24
    assert primary(s)["to_hit"] == 25            # bab18 −2 size +9 str
    assert primary(s)["damage"] == "2d10+9"
    assert s["saves"] == {"fort": 19, "ref": 16, "will": 10}


def test_toughness_adds_hp():
    # Constrictor snake har Toughness → +3 HP over rå gennemsnit.
    s = stat("snake_constrictor")
    assert s["hp_max"] == 19                    # 13 (avg) + 3 (con) + 3 (toughness)


def test_multiattack_primary_and_secondary():
    # Black bear: 2 claws (primær, fuld str) + bite (sekundær, −5, ½ str).
    s = stat("black_bear")
    claw, bite = s["attacks"]
    assert claw["to_hit"] == 6 and claw["count"] == 2 and claw["damage"] == "1d4+4"
    assert bite["to_hit"] == 1 and bite["group"] == "secondary"
    assert bite["damage"] == "1d6+2"           # ½ × str4 = +2


# ── Augment Summoning: +4 Str/Con kaskaderer ────────────────────────────────

def test_augment_raises_hp_and_damage():
    base = stat("dire_wolf")
    aug = stat("dire_wolf", augment=True)
    # Con 17(+3) → 21(+5): +2 mod × 6 HD = +12 HP.
    assert aug["hp_max"] == base["hp_max"] + 12 == 57
    # Str 25(+7) → 29(+9): til-hit +2, skade ×1,5 → +13.
    assert primary(aug)["to_hit"] == primary(base)["to_hit"] + 2 == 13
    assert primary(aug)["damage"] == "1d8+13"
    assert aug["abilities"]["str"] == 29 and aug["abilities"]["con"] == 21


def test_no_augment_is_raw_creature():
    # Uden augment er statblokket bit-identisk med det rå væsen (ingen effekter).
    assert stat("dire_wolf", augment=False)["abilities"]["str"] == 25


# ── Tynd reference: antal + HP-liste ────────────────────────────────────────

def test_count_and_hp_clamping():
    s = stat("wolf", count=3, hp_current=[5, None, 999])
    assert s["count"] == 3
    # 5 bevares; None → fuld; 999 klampes til hp_max.
    assert s["hp_current"] == [5, s["hp_max"], s["hp_max"]]


def test_unknown_creature_returns_none():
    assert summon.build_summon({"creature": "nonexistent"}, db) is None
    assert summon.build_summon({}, db) is None


def test_build_summons_filters_empty():
    out = summon.build_summons(
        [{"creature": "wolf"}, {"creature": "bad"}, {}], db)
    assert len(out) == 1 and out[0]["creature_id"] == "wolf"


# ── Persistens: summons-listen gemmes/genindlæses (Fase 2) ──────────────────

def test_summons_persist_round_trip(tmp_path):
    p = tmp_path / "c.yaml"
    shutil.copy(pathlib.Path(__file__).parent / "defaults" / "faelyn.yaml", p)
    refs = [
        {"creature": "dire_wolf", "spell_level": 3, "spell_index": 0,
         "count": 1, "augment": True, "hp_current": [40]},
        {"creature": "wolf", "spell_level": 1, "spell_index": 2,
         "count": 3, "hp_current": [13, 8, 2], "conditions": ["shaken"]},
    ]
    char_module.save_character(str(p), {"summons": refs})
    c = char_module.load_character(str(p))
    assert len(c.summons) == 2
    a, b = c.summons
    assert a["creature"] == "dire_wolf" and a["augment"] is True
    assert b["hp_current"] == [13, 8, 2] and b["conditions"] == ["shaken"]
    # Det beregnede statblok afspejler den persisterede ref (augment slår igennem).
    stats = summon.build_summons(c.summons, db)
    assert stats[0]["hp_max"] == 57 and stats[1]["count"] == 3
    # Tom liste rydder feltet.
    char_module.save_character(str(p), {"summons": []})
    assert char_module.load_character(str(p)).summons == []


# ── Del B: SNA IV-IX nye statblokke (Fase 6) ────────────────────────────────

def test_dire_bear_all_three_good_saves():
    # Dire Bear (12 HD animal) har good_saves: alle tre — SRD Fort+12/Ref+9/Will+9.
    s = stat("dire_bear")
    assert s["hp_max"] == 105                       # 12×4.5 + 12×4 (Con) + 3 (Toughness)
    assert s["ac"]["ac"] == 17
    assert s["saves"] == {"fort": 12, "ref": 9, "will": 9}
    clw = s["attacks"][0]
    assert clw["to_hit"] == 19 and clw["damage"] == "2d4+10"   # SRD: Claw +19 (2d4+10)


def test_tyrannosaurus_huge_animal():
    # Tyrannosaurus (18 HD Huge animal, sole primary, ×1.5 Str=+9).
    s = stat("tyrannosaurus")
    assert s["hp_max"] == 180                       # 18×4.5 + 18×5 (Con) + 9 (Toughness×3)
    assert s["saves"] == {"fort": 16, "ref": 12, "will": 8}
    bite = s["attacks"][0]
    assert bite["to_hit"] == 20 and bite["damage"] == "3d6+13"  # SRD: Bite +20 (3d6+13)


def test_invisible_stalker_elemental_ref_only():
    # Invisible Stalker (8 HD elemental, good_saves: ["ref"], ¾ BAB).
    s = stat("invisible_stalker")
    assert s["hp_max"] == 52                        # 8×4.5 + 8×2 (Con) = 36+16=52
    assert s["saves"] == {"fort": 4, "ref": 10, "will": 4}
    slam = s["attacks"][0]
    assert slam["to_hit"] == 10 and slam["count"] == 2          # SRD: 2 slams +10


def test_djinni_outsider_all_three_good_saves():
    # Djinni (7 HD outsider, fuld BAB, alle tre gode saves).
    s = stat("djinni")
    assert s["hp_max"] == 45                        # 7×4.5 + 7×2 (Con) = 31+14=45
    assert s["saves"] == {"fort": 7, "ref": 9, "will": 7}
    assert s["bab"] == 7


def test_arrowhawk_elder_str_over_dex():
    # Elder Arrowhawk: Weapon Finesse men Str(+6) > Dex(+5) → Str bruges til-hit.
    s = stat("arrowhawk_elder")
    assert s["hp_max"] == 112                       # 15×4.5 + 15×3 (Con) = 67+45=112
    assert s["saves"] == {"fort": 12, "ref": 14, "will": 10}
    bite = s["attacks"][0]
    assert bite["to_hit"] == 20                     # bab15 + Str6 − size1 = 20


def test_pixie_fey_half_bab():
    # Pixie (1 HD fey, ½ BAB=0, god Ref+Will, dårlig Fort).
    s = stat("pixie")
    assert s["bab"] == 0
    assert s["saves"]["fort"] == 0 and s["saves"]["ref"] == 6 and s["saves"]["will"] == 4


def test_grig_half_hd_fey():
    # Grig (base_hd=1, hit_die=2 → ½ HD): F=1, R=6, W=3.
    s = stat("grig")
    assert s["hp_max"] == 2                         # 1×avg(d2=1.5) + Con1 = 1+1=2
    assert s["saves"] == {"fort": 1, "ref": 6, "will": 3}


def test_unicorn_magical_beast_saves():
    # Unicorn (4 HD magical_beast): god Fort+Ref, dårlig Will — SRD Fort+9/Ref+7/Will+6.
    s = stat("unicorn")
    assert s["hp_max"] == 42                        # 4×4.5 + 4×5 (Con) = 18+20=... wait
    assert s["saves"] == {"fort": 9, "ref": 7, "will": 6}


# ── Multi-tier summon: 1 væsen (top-liste) / 1d3 (én ned) / 1d4+1 (to ned) ──

def test_summon_tiers_offsets_and_counts():
    import refdata
    tiers = refdata.summon_tiers("sna", 3)
    assert [(t["offset"], t["list_level"], t["count"]) for t in tiers] == [
        (0, 3, "1"), (1, 2, "1d3"), (2, 1, "1d4+1")]


def test_summon_tiers_level1_only_top():
    import refdata
    tiers = refdata.summon_tiers("sna", 1)
    assert [t["offset"] for t in tiers] == [0]      # ingen lavere lister


def test_summon_count_expr_by_tier():
    import refdata
    # black_bear er på liste 2: top-spor ved SNA II, ét-ned-spor (1d3) ved SNA III.
    assert refdata.summon_count_expr("sna", 2, "black_bear", None) == "1"
    assert refdata.summon_count_expr("sna", 3, "black_bear", None) == "1d3"
    # wolf er på liste 1: to ned ved SNA III → 1d4+1.
    assert refdata.summon_count_expr("sna", 3, "wolf", None) == "1d4+1"
    # ukendt/uden for sporene → None (afvises af app-laget).
    assert refdata.summon_count_expr("sna", 2, "tarrasque", None) is None
