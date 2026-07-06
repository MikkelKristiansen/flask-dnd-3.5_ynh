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

Almindelig DM-note med @npc[bram] og handout @brev[testbrev]. En @monster[goblin] lurer, ledet af @npc[testskurk].

![Oversigt](media/oversigt.png)

@kort[testkort]

## Monstre
* 2x @monster[goblin]

# Anden scene
Tekst to.

# Dokumenter

## Kort: Testkort
![Testkort](media/testkort.png)

## Brev: Testbrev
> Kære helte, kom straks.

## Statblok: Testskurk
```yaml
type: humanoid
hp_max: 18
ac: 15
attacks:
  - {name: Kårde, bonus: "+3", damage: 1d6+1}
feats: [Dodge]
```
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    adv = tmp_path / "adventures"
    (adv / "Test" / "media").mkdir(parents=True)
    (adv / "Test" / "adventure.md").write_text(MINI, encoding="utf-8")
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
    # Et @-token der hverken er handout eller monster/npc forbliver ren tekst.
    raw = ("---\ntitle: T\n---\n# S\nEn @genstand[amulet] uden opslag.\n")
    (ds.ADVENTURES_DIR / "Plain").mkdir()
    (ds.ADVENTURES_DIR / "Plain" / "adventure.md").write_text(raw, encoding="utf-8")
    slug = _new(client, name="E", adventure="Plain")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert '<span class="ent ent-genstand">amulet</span>' in html


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


def test_inline_image_renders_as_img(client):
    slug = _new(client, name="Img")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert '<img class="scene-img"' in html
    # url_for('dm.media', adventure='Test', filename='media/oversigt.png')
    assert "/dm/media/Test/media/oversigt.png" in html


def test_kort_embed_resolves_to_map_inline(client):
    slug = _new(client, name="Kort")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "Testkort" in html                             # dokument-titel som caption
    assert "/dm/media/Test/media/testkort.png" in html    # kort renderet inline


def test_media_route_serves_file(client, tmp_path):
    # Fixturen har allerede adventures/Test/media/ under ADVENTURES_DIR.
    (tmp_path / "adventures" / "Test" / "media" / "x.png").write_bytes(
        b"\x89PNG\r\n\x1a\n")
    assert client.get("/dm/media/Test/media/x.png").status_code == 200


def test_media_route_blocks_traversal(client):
    r = client.get("/dm/media/Test/../../dm_session.py")
    assert r.status_code in (403, 404)               # send_from_directory afviser


def test_inline_doc_ref_is_clickable(client):
    slug = _new(client, name="Ref")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    # @brev[testbrev] resolver til et dokument → handout-link (lightbox), titel som tekst
    assert 'class="ent ent-brev ent-link" data-doc="brev:testbrev">Testbrev</a>' in html
    # @npc[bram] er ikke et handout → statblok-link (fetch), IKKE lightbox
    assert 'class="ent ent-npc ent-stat" data-stat="npc/bram">bram</a>' in html


def test_handout_container_rendered_for_lightbox(client):
    slug = _new(client, name="LB")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert 'id="doc-brev-testbrev"' in html          # skjult handout til lightbox
    assert "Kære helte, kom straks." in html         # brevets indhold


# ── Billed-administration (upload/slet) ──────────────────────────────────────
import io

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def test_adventure_page_lists_and_index_links(client):
    assert client.get("/dm/adventures/Test").status_code == 200
    # DM-forsiden linker til billed-siden
    assert "/dm/adventures/Test" in client.get("/dm/").get_data(as_text=True)


def test_adventure_page_unknown_404(client):
    assert client.get("/dm/adventures/Findes-ej").status_code == 404


def test_upload_stores_image_and_serves_it(client):
    r = client.post("/dm/adventures/Test/media",
                    data={"images": (io.BytesIO(_PNG), "Heltenes hus.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    # filnavnet saneres (mellemrum → bindestreg), bevarer .png
    page = client.get("/dm/adventures/Test").get_data(as_text=True)
    assert "Heltenes-hus.png" in page
    assert client.get("/dm/media/Test/media/Heltenes-hus.png").status_code == 200


def test_upload_rejects_non_image(client):
    r = client.post("/dm/adventures/Test/media",
                    data={"images": (io.BytesIO(b"ikke et billede"), "ondt.txt")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "ondt" in r.get_data(as_text=True)         # fejl vises
    assert client.get("/dm/media/Test/media/ondt.txt").status_code == 404


def test_delete_media(client):
    client.post("/dm/adventures/Test/media",
                data={"images": (io.BytesIO(_PNG), "kort.png")},
                content_type="multipart/form-data")
    assert client.get("/dm/media/Test/media/kort.png").status_code == 200
    client.post("/dm/adventures/Test/media/kort.png/delete")
    assert client.get("/dm/media/Test/media/kort.png").status_code == 404


# ── Statblok-inspector (R2 commit 3) ─────────────────────────────────────────
def test_monster_ref_is_clickable_stat(client):
    slug = _new(client, name="Stat")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    # @monster[goblin] i MINI → klikbart statblok-link (fetch), ikke plain span
    assert 'class="ent ent-monster ent-stat" data-stat="monster/goblin"' in html


def test_statblock_endpoint_bestiary_monster(client):
    # goblin findes i det seedede bestiar (kræver srd35.db)
    html = client.get("/dm/api/statblock/Test/monster/goblin").get_data(as_text=True)
    assert "Goblin" in html and "Bestiar" in html
    assert "Morgenstjerne" in html            # angreb renderet


def test_statblock_endpoint_adventure_local(client):
    # MINI's # Dokumenter har ## Statblok: Testskurk → adventure-lokalt vinder
    html = client.get("/dm/api/statblock/Test/npc/testskurk").get_data(as_text=True)
    assert "Testskurk" in html and "Eventyr" in html


def test_statblock_endpoint_unknown_is_graceful(client):
    html = client.get("/dm/api/statblock/Test/monster/findes-ej").get_data(as_text=True)
    assert "Ingen statblok endnu" in html


def test_statblock_endpoint_unknown_adventure_404(client):
    assert client.get("/dm/api/statblock/Nope/monster/goblin").status_code == 404


# ── Encounter-tracker (R3 commit 3) ──────────────────────────────────────────
from pathlib import Path


@pytest.fixture
def enc_client(client, monkeypatch):
    # Lad party-PC'er (tjorn) resolve fra defaults/, så de kommer med i kampen.
    import dm_party
    monkeypatch.setattr(dm_party, "CHARACTERS_DIR", Path("defaults"))
    return client


def _start(enc_client):
    slug = _new(enc_client, name="Kamp", party=["tjorn"])   # scene 1: 2x goblin
    html = enc_client.post(f"/dm/api/encounter/{slug}/start").get_data(as_text=True)
    return slug, html


def test_encounter_start_builds_labeled_combatants(enc_client):
    slug, html = _start(enc_client)
    # per-instans-labels (bestiar-navnet er "Goblin (kriger)")
    assert "Goblin (kriger) A" in html and "Goblin (kriger) B" in html
    assert "Tjørn" in html                              # PC med i kampen
    assert "Runde 1" in html
    enc = ds.load_session(slug).encounter
    assert enc["active"] and len(enc["combatants"]) == 3


def test_encounter_pc_initiative_blank_monsters_rolled(enc_client):
    slug, _ = _start(enc_client)
    combs = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    assert combs["tjorn"]["initiative"] is None        # PC tastes af DM
    assert combs["goblin-a"]["initiative"] is not None  # monster auto-rullet


def test_encounter_set_pc_initiative_reorders(enc_client):
    slug, _ = _start(enc_client)
    enc_client.post(f"/dm/api/encounter/{slug}/initiative",
                    data={"cid": "tjorn", "value": "25"})
    enc = ds.load_session(slug).encounter
    assert enc["turn_order"][0] == "tjorn"             # højeste initiativ → først


def test_encounter_hp_damage_and_next_turn(enc_client):
    slug, _ = _start(enc_client)
    enc_client.post(f"/dm/api/encounter/{slug}/hp",
                    data={"cid": "goblin-a", "delta": "-3"})
    combs = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    assert combs["goblin-a"]["current_hp"] == 2        # goblin har 5 HP → 2
    enc_client.post(f"/dm/api/encounter/{slug}/next")
    assert ds.load_session(slug).encounter["turn_index"] == 1


def test_encounter_condition_toggle_and_end(enc_client):
    slug, _ = _start(enc_client)
    enc_client.post(f"/dm/api/encounter/{slug}/condition",
                    data={"cid": "goblin-b", "condition": "prone"})
    combs = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    assert combs["goblin-b"]["conditions"] == ["prone"]
    enc_client.post(f"/dm/api/encounter/{slug}/end")
    assert ds.load_session(slug).encounter == {}
