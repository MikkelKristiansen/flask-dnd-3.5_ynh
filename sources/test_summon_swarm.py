"""Unit-tests for Summon Swarm (BRIEF-summon-swarm.md).

Kør: python -m pytest test_summon_swarm.py   (fra sources/)

Summon Swarm er en selvstændig lille feature: ét fast spell (niveau 2, ikke
niveau-skaleret), valg mellem 3 faste væsner, og en varighed (Concentration + 2
rounds) der IKKE følger SNA/SM's "1 runde/casterniveau"-mønster.
"""
import db
import refdata
import summon


def test_summon_swarm_recognized_as_its_own_family():
    assert refdata.summon_family("summon_swarm") == "swarm"


def test_swarm_tiers_offer_exactly_three_choices_no_weaker_tiers():
    tiers = refdata.summon_tiers("swarm", 2)
    assert len(tiers) == 1                      # ingen 1d3/1d4+1-spor (ikke niveau-skaleret)
    entries = tiers[0]["entries"]
    assert {e["base"] for e in entries} == {"bat_swarm", "rat_swarm", "spider_swarm"}
    assert tiers[0]["count"] == "1"


def test_bat_swarm_matches_srd():
    s = summon.build_summon_stat(db.get_animal("bat_swarm"), db)
    assert s["hp_max"] == 13
    assert s["bab"] == 2
    assert s["saves"] == {"fort": 3, "ref": 7, "will": 3}   # Ref +2 fra Lightning Reflexes
    assert s["ac"]["ac"] == 16
    assert s["attacks"] == []                    # intet til-hit-rul — skade er i special_attacks


def test_rat_swarm_matches_srd_bab_and_saves():
    # SRD's printede "(13 hp)" er internt inkonsistent med egne HD/BAB/saves
    # (4d8 giver gennemsnit 18, og BAB/alle tre saves matcher KUN ved HD=4) —
    # base_hd=4 er verificeret via BAB+saves, ikke gættet.
    s = summon.build_summon_stat(db.get_animal("rat_swarm"), db)
    assert s["bab"] == 3
    assert s["saves"] == {"fort": 4, "ref": 6, "will": 2}
    assert s["ac"]["ac"] == 14


def test_spider_swarm_uses_vermin_good_fort_only():
    # Vermin har god Fort/dårlig Ref/dårlig Will — modsat animal-defaulten
    # (god Fort+Ref) — kræver eksplicit good_saves-override i data.
    s = summon.build_summon_stat(db.get_animal("spider_swarm"), db)
    assert s["saves"] == {"fort": 3, "ref": 3, "will": 0}
    assert s["bab"] == 1
    assert s["ac"]["ac"] == 17


def test_swarms_are_not_companion_eligible():
    for sid in ("bat_swarm", "rat_swarm", "spider_swarm"):
        assert db.get_animal(sid).get("companion_ok") == 0
