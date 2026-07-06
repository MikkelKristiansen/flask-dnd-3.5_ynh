"""Tests for dm_preview.check — validering af @-referencer."""
import os

import dm_parser as P
import dm_preview as V

FIXTURE = os.path.join(os.path.dirname(__file__),
                       "adventures", "Midsommer", "adventure.md")


def test_fixture_has_no_dead_refs():
    with open(FIXTURE, encoding="utf-8") as f:
        adv = P.parse_adventure(f.read())
    r = V.check(adv)
    assert r["dead"] == []
    # monster/npc/faelde er eksterne (ikke i appendiks → fra DB i R2)
    ext_types = {e.type for e, _ in r["external"]}
    assert {"monster", "npc", "faelde"} <= ext_types


def test_dead_reference_detected():
    raw = (
        "# Scene\n@kort[kaeldern]\n\n"        # stavefejl: mangler 'e'
        "# Dokumenter\n## Kort: Kælderen\n![k](media/k.png)\n"
    )
    r = V.check(P.parse_adventure(raw))
    dead_ids = {e.id for e, _ in r["dead"]}
    assert "kaeldern" in dead_ids            # fanget som død reference
    assert r["external"] == []               # kort ER en doc-lokal type her


def test_external_reference_not_flagged_dead():
    raw = "# Scene\n## Monstre\n* 2x @monster[goblin]\n"
    r = V.check(P.parse_adventure(raw))
    assert r["dead"] == []
    assert ("monster", "goblin") in {(e.type, e.id) for e, _ in r["external"]}


def test_unused_definition_detected():
    raw = (
        "# Scene\nEn tom scene uden referencer.\n\n"
        "# Dokumenter\n## Brev: Ubrugt brev\n> Ingen læser mig.\n"
    )
    r = V.check(P.parse_adventure(raw))
    assert [d.id for d in r["unused"]] == ["ubrugt-brev"]


def test_report_exit_code():
    good = P.parse_adventure("# S\n## Monstre\n* 1x @monster[ulv]\n")
    assert V.report(good) == 0
    bad = P.parse_adventure("# S\n@brev[xyz]\n\n# Dokumenter\n## Brev: Et\n> hej\n")
    assert V.report(bad) == 1
