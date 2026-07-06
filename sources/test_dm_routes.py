"""Tests for dm-blueprintet via Flask-testklienten (hermetisk: tmp-dirs)."""
import pytest

import dm_session as ds
from app import app

MINI = """---
title: Testeventyr
party: [tjorn]
---
# Første scene
> Læses højt.

Almindelig DM-note med @npc[bram].

## Monstre
* 2x @monster[goblin]

# Anden scene
Tekst to.
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    adv = tmp_path / "adventures"
    adv.mkdir()
    (adv / "Test.md").write_text(MINI, encoding="utf-8")
    monkeypatch.setattr(ds, "ADVENTURES_DIR", adv)
    monkeypatch.setattr(ds, "SESSIONS_DIR", tmp_path / "sessions")
    app.config.update(TESTING=True)
    return app.test_client()


def _new(client, name="Min", adventure="Test", party=None):
    client.post("/dm/sessions",
                data={"name": name, "adventure": adventure, "party": party or []})
    return ds.list_sessions()[0]["slug"]


def test_index_lists_adventures(client):
    r = client.get("/dm/")
    assert r.status_code == 200 and b"Test" in r.data


def test_create_redirects_to_play(client):
    r = client.post("/dm/sessions",
                    data={"name": "Min", "adventure": "Test", "party": ["tjorn"]})
    assert r.status_code == 302 and "/dm/play/" in r.headers["Location"]


def test_play_renders_active_scene_and_readaloud(client):
    slug = _new(client)
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "Første scene" in html            # aktiv scene (første)
    assert "Læses højt" in html              # read-aloud renderet
    assert "2× goblin" in html               # roster


def test_navigation_persists(client):
    slug = _new(client, name="Nav")
    client.get(f"/dm/play/{slug}?scene=anden-scene")
    assert ds.load_session(slug).active_scene == "anden-scene"


def test_entities_rendered_as_span(client):
    slug = _new(client, name="E")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert '<span class="ent ent-npc">bram</span>' in html


def test_delete_session(client):
    slug = _new(client, name="Slet")
    r = client.post(f"/dm/sessions/{slug}/delete")
    assert r.status_code == 302 and ds.list_sessions() == []


def test_create_requires_adventure(client):
    assert client.post("/dm/sessions", data={"name": "X"}).status_code == 400


def test_play_unknown_slug_404(client):
    assert client.get("/dm/play/findes-ikke").status_code == 404


def test_party_sidebar_shows_statblock(client, monkeypatch):
    import dm_party
    monkeypatch.setattr(dm_party, "CHARACTERS_DIR", __import__("pathlib").Path("defaults"))
    slug = _new(client, name="Party", party=["tjorn"])
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "❤ 24/24" in html                 # HP fra build_character_view
    assert "AC 15" in html                    # AC-total
    assert "For +5" in html                   # save (Fortitude, forkortet)


def test_party_sidebar_broken_pc_is_marked(client):
    # En PC-slug der ikke resolver må ikke crashe siden — den vises som "broken".
    slug = _new(client, name="Broken", party=["findes-ej"])
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "findes-ej" in html and "Kunne ikke indlæses" in html
