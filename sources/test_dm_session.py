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
