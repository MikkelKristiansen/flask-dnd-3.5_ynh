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

Almindelig DM-note med @npc[bram] og handout @brev[testbrev]. En @monster[goblin] lurer, ledet af @npc[testskurk]. En @faelde[basic-arrow-trap] i gulvet. Bag den knirker en @dør[iron-door].

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


def test_statblock_endpoint_magic_weapon(client):
    # @magisk[longsword+1] → base-våben (srd35.db) + enhancement-overlay
    html = client.get("/dm/api/statblock/Test/magisk/longsword+1").get_data(as_text=True)
    assert "+1 Longsword" in html and "Magisk våben" in html
    assert "2315 gp" in html                   # SRD-pris: 15 + masterwork 300 + 2.000


def test_statblock_endpoint_magic_unknown_base_graceful(client):
    html = client.get("/dm/api/statblock/Test/magisk/findes-ej+1").get_data(as_text=True)
    assert "Ingen statblok endnu" in html


def test_statblock_endpoint_magic_invalid_bonus_graceful(client):
    # bonus uden for 1-5 → magic_gear rejser ValueError → fanges → graceful
    html = client.get("/dm/api/statblock/Test/magisk/longsword+9").get_data(as_text=True)
    assert "Ingen statblok endnu" in html


# ── Giv loot til spiller (trin 2) ────────────────────────────────────────────
def test_give_loot_unknown_base_404(client):
    r = client.post("/dm/api/give-loot",
                    data={"char": "tjorn", "base_ref": "weapons/findes-ej", "bonus": "1"})
    assert r.status_code == 404


def test_give_loot_invalid_bonus_400(client):
    # base findes, men bonus 9 er ugyldig → 400 (ingen skrivning)
    r = client.post("/dm/api/give-loot",
                    data={"char": "tjorn", "base_ref": "weapons/longsword", "bonus": "9"})
    assert r.status_code == 400


def test_give_loot_adds_item_to_character(client, tmp_path, monkeypatch):
    # Isoleret: kopiér fixtur-karakteren til tmp og patch CHARACTERS_DIR, så
    # rigtige spillerdata ALDRIG røres.
    import shutil
    import app as app_module
    import dm_scene
    import character as char_module
    chars = tmp_path / "characters"
    chars.mkdir()
    shutil.copy("defaults/tjorn.yaml", chars / "tjorn.yaml")
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", chars)
    monkeypatch.setattr(dm_scene, "CHARACTERS_DIR", chars)

    r = client.post("/dm/api/give-loot",
                    data={"char": "tjorn", "base_ref": "weapons/longsword", "bonus": "1"})
    assert r.status_code == 200 and "+1 Longsword" in r.get_data(as_text=True)

    inv = char_module.load_character(str(chars / "tjorn.yaml")).inventory
    assert any(i.ref == "weapons/longsword" and i.enhancement == 1 and i.bonus == 1
               for i in inv)


# ── Monster-token-upload (browser-UI, v2) ────────────────────────────────────
import base64 as _b64
import io as _io

_PNG_1x1 = _b64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    b"+M8AAAMBAQBQm4CQAAAAAElFTkSuQmCC")


def _patch_tokens_dir(monkeypatch, tmp_path):
    import monster_tokens
    d = tmp_path / "monster_tokens"
    monkeypatch.setattr(monster_tokens, "MONSTER_TOKENS_DIR", d)
    return d


def test_monster_tokens_page_empty(client, tmp_path, monkeypatch):
    _patch_tokens_dir(monkeypatch, tmp_path)
    html = client.get("/dm/monster-tokens").get_data(as_text=True)
    assert "Monster-tokens" in html and "Ingen tokens endnu" in html


def test_monster_token_upload_saves_by_slug_and_lists(client, tmp_path, monkeypatch):
    import monster_tokens
    d = _patch_tokens_dir(monkeypatch, tmp_path)
    r = client.post("/dm/monster-tokens/upload",
                    data={"images": (_io.BytesIO(_PNG_1x1), "Goblin.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    assert (d / "goblin.png").exists()                 # filnavn → slug (lowercase)
    assert "goblin" in monster_tokens.list_tokens()
    assert "goblin" in client.get("/dm/monster-tokens").get_data(as_text=True)


def test_monster_token_upload_rejects_non_png(client, tmp_path, monkeypatch):
    d = _patch_tokens_dir(monkeypatch, tmp_path)
    jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20   # gyldigt billede, men JPG
    r = client.post("/dm/monster-tokens/upload",
                    data={"images": (_io.BytesIO(jpg), "goblin.jpg")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    assert not (d / "goblin.png").exists()             # ikke-PNG gemmes ikke


def test_monster_token_delete(client, tmp_path, monkeypatch):
    d = _patch_tokens_dir(monkeypatch, tmp_path)
    d.mkdir(parents=True)
    (d / "ogre.png").write_bytes(_PNG_1x1)
    r = client.post("/dm/monster-tokens/ogre/delete")
    assert r.status_code == 302
    assert not (d / "ogre.png").exists()


# ── Editor-brugervenlighed (Fase A) ──────────────────────────────────────────
def test_edit_page_wires_editor_script_and_draft(client):
    html = client.get("/dm/adventures/Test/edit").get_data(as_text=True)
    assert "dm-editor.js" in html                 # brugervenligheds-JS indlæst
    assert 'id="restore"' in html                 # kladde-gendannelses-banner
    assert 'data-ref="Test"' in html              # localStorage-nøgle pr. eventyr
    assert "Ctrl/Cmd-S" in html                   # gem-genvej annonceret
    assert "codemirror.min.js" in html            # Fase B: CM5 self-hosted
    assert "simple.min.js" in html
    assert "codemirror.min.css" in html
    # Fase C: indsæt-værktøjslinje + billed-vælger
    assert 'data-insert="scene"' in html and 'data-insert="readaloud"' in html
    assert 'id="img-insert"' in html


def test_edit_media_picker_lists_uploaded_images(client):
    # Billed-vælgeren fodres af eventyrets media-mappe (samme kilde som billed-siden).
    (ds.ADVENTURES_DIR / "Test" / "media" / "kort.png").write_bytes(_PNG_1x1)
    html = client.get("/dm/adventures/Test/edit").get_data(as_text=True)
    assert '<option value="kort.png">kort.png</option>' in html


# ── @-autocomplete (Fase D) ──────────────────────────────────────────────────
def test_entity_ids_endpoint(client):
    mons = client.get("/dm/api/entity-ids?type=monster").get_json()
    assert isinstance(mons, list) and mons and all("id" in m for m in mons)
    assert any(m["id"] == "goblin" for m in mons)                      # fra srd35.db
    assert all("cr" in m for m in mons)                                # cr til opslagsværkets filter
    traps = client.get("/dm/api/entity-ids?type=faelde").get_json()
    assert any(t["id"] == "basic-arrow-trap" for t in traps)
    assert client.get("/dm/api/entity-ids?type=door").get_json()       # 6 SRD-døre
    assert client.get("/dm/api/entity-ids?type=bogus").get_json() == []


def test_edit_page_wires_autocomplete(client):
    html = client.get("/dm/adventures/Test/edit").get_data(as_text=True)
    assert "show-hint.min.js" in html and "dm-editor-hint.js" in html
    assert "data-entity-api" in html


def test_edit_page_wires_content_browser(client):
    html = client.get("/dm/adventures/Test/edit").get_data(as_text=True)
    assert "dm-content-browser.js" in html                 # opslagsværk-JS indlæst
    assert 'id="browse-panel"' in html and 'id="browse-toggle"' in html
    assert "dm-statblock.css" in html                      # statblok-styling til preview


# ── "Start kamp fra denne scene" kun på relevante scener ─────────────────────
def test_start_button_hidden_on_narrative_scene(client):
    ref = "Fortael"
    (ds.ADVENTURES_DIR / ref).mkdir()
    (ds.ADVENTURES_DIR / ref / "adventure.md").write_text(
        "---\ntitle: Fortael\n---\n# Kro-scene\nBare hyggesnak, ingen kamp.\n",
        encoding="utf-8")
    slug = _new(client, name="F", adventure=ref)
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "Start kamp fra denne scene" not in html      # gated væk
    assert "Ingen kamp-elementer" in html                # forklarende hint i stedet


def test_start_button_shown_on_combat_scene(client):
    slug = _new(client, name="K")                        # MINI: monster + fælde i scenen
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "Start kamp fra denne scene" in html


def test_scene_combat_relevance_helper():
    import dm_parser
    import dm_scene
    def scene0(body):
        return dm_parser.parse_adventure("---\ntitle: x\n---\n" + body).scenes[0]
    assert dm_scene.scene_is_combat_relevant(scene0("# S\nBare prosa.\n")) is False
    assert dm_scene.scene_is_combat_relevant(scene0("# S\nEn bro.\n\n@kort[bro]\n")) is True


# ── Bræt-palette: kun party når åbnet fra en session ─────────────────────────
def test_board_palette_shows_only_party_when_given():
    import dm_parser, dm_scene
    adv = dm_parser.parse_adventure("---\ntitle: x\n---\n# S\nProsa.\n")
    pcs = dm_scene._board_palette(adv, party=["tjorn", "zhartain"])["pcs"]
    assert [p["ref"] for p in pcs] == ["tjorn", "zhartain"]     # kun party, i rækkefølge
    assert all(p["kind"] == "pc" for p in pcs)


def test_board_from_session_shows_party_in_palette(client):
    slug = _new(client, name="Bs", party=["tjorn"])
    r = client.get(f"/dm/board/Test/testkort?from={slug}")
    assert r.status_code == 200
    assert '"ref": "tjorn"' in r.get_data(as_text=True)         # party-PC i palette-JSON


# ── Redigér session-party (Lag 2) ────────────────────────────────────────────
def test_edit_party_remove(client):
    slug = _new(client, name="Pr", party=["tjorn", "zhartain"])
    r = client.post(f"/dm/api/party/{slug}", data={"action": "remove", "pc": "tjorn"})
    assert r.status_code == 302
    assert ds.load_session(slug).party == ["zhartain"]         # slår igennem i sessionen


def test_edit_party_add(client, tmp_path, monkeypatch):
    import dm_scene
    chars = tmp_path / "chars"
    chars.mkdir()
    (chars / "tjorn.yaml").write_text("x")
    (chars / "bram.yaml").write_text("x")
    monkeypatch.setattr(dm_scene, "CHARACTERS_DIR", chars)
    slug = _new(client, name="Pa", party=["tjorn"])
    r = client.post(f"/dm/api/party/{slug}", data={"action": "add", "pc": "bram"})
    assert r.status_code == 302
    assert set(ds.load_session(slug).party) == {"tjorn", "bram"}
    # ukendt karakter tilføjes ikke
    client.post(f"/dm/api/party/{slug}", data={"action": "add", "pc": "findes-ej"})
    assert "findes-ej" not in ds.load_session(slug).party


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
    assert "Varg" in html                               # Tjørns companion med i kampen
    assert "Runde 1" in html
    enc = ds.load_session(slug).encounter
    # 2 goblins + Tjørn (PC) + Varg (companion)
    assert enc["active"] and len(enc["combatants"]) == 4


def test_encounter_includes_party_companion(enc_client):
    slug, _ = _start(enc_client)
    combs = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    varg = combs["tjorn-companion"]
    assert varg["kind"] == "companion" and varg["name"] == "Varg"
    assert varg["initiative"] is not None              # companion auto-rulles (ikke blank som PC)
    assert varg["current_hp"] == varg["hp_max"] > 0    # egen HP-pulje


def test_encounter_shows_statblock_cards(enc_client):
    slug, html = _start(enc_client)
    assert "Statblokke" in html                    # statblok-sektion i konsollen
    assert "Morgenstjerne" in html                 # goblinens angreb vises direkte
    # dedup pr. type: 2 goblins i kampen, men kun ÉT statblok-kort
    assert html.count('class="sbk-name"') == 1


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


def test_encounter_board_shows_live_combat_positions(enc_client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 80}, "tokens": [
        {"kind": "monster", "ref": "goblin", "label": "A", "col": 4, "row": 2},
        {"kind": "monster", "ref": "goblin", "label": "B", "col": 5, "row": 2},
        {"kind": "pc", "ref": "tjorn", "col": 1, "row": 6}]})
    slug, _ = _start(enc_client)                        # seeder positioner fra opstillingen
    # combatants fik startposition fra opstillingen
    by = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    assert (by["goblin-a"]["col"], by["goblin-a"]["row"]) == (4, 2)
    assert (by["tjorn"]["col"], by["tjorn"]["row"]) == (1, 6)
    # bræt-fragmentet viser dem som combatant-tokens m/ HP-badge + kamp-markering
    frag = enc_client.get(f"/dm/api/encounter/{slug}/board").get_data(as_text=True)
    assert 'data-cid="goblin-a"' in frag and 'data-cid="goblin-b"' in frag
    assert 'class="tok-hp"' in frag and "⚔ kamp" in frag
    # play-viewet viser kamp-brættet direkte i #board-slot
    html = enc_client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert 'id="board-slot"' in html and 'data-combat="1"' in html


def test_encounter_move_updates_live_position(enc_client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 80},
        "tokens": [{"kind": "monster", "ref": "goblin", "label": "A", "col": 4, "row": 2}]})
    slug, _ = _start(enc_client)
    r = enc_client.post(f"/dm/api/encounter/{slug}/move",
                        data={"cid": "goblin-a", "col": "9", "row": "7"})
    assert r.status_code == 204
    c = next(x for x in ds.load_session(slug).encounter["combatants"]
             if x["id"] == "goblin-a")
    assert (c["col"], c["row"]) == (9, 7)              # live-position flyttet
    # play indlæser combat-drag-modulet
    html = enc_client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "dm-combat-board.js" in html


def test_encounter_board_falls_back_to_setup_when_no_combat(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 80},
        "tokens": [{"kind": "monster", "ref": "goblin", "col": 2, "row": 2}]})
    slug = _new(client, name="NB")
    frag = client.get(f"/dm/api/encounter/{slug}/board").get_data(as_text=True)
    assert 'class="board"' in frag and "⚔ kamp" not in frag   # opstilling, ingen kamp


def test_encounter_hp_damage_and_next_turn(enc_client):
    slug, _ = _start(enc_client)
    enc_client.post(f"/dm/api/encounter/{slug}/hp",
                    data={"cid": "goblin-a", "delta": "-3"})
    combs = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    assert combs["goblin-a"]["current_hp"] == 2        # goblin har 5 HP → 2
    enc_client.post(f"/dm/api/encounter/{slug}/next")
    assert ds.load_session(slug).encounter["turn_index"] == 1


def test_board_view_renders_tokens(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 100},
        "tokens": [{"kind": "monster", "ref": "goblin", "label": "A", "col": 2, "row": 2},
                   {"kind": "trap", "ref": "faelde", "col": 1, "row": 1, "note": "DC15"}]})
    html = client.get("/dm/board/Test/testkort").get_data(as_text=True)
    assert 'class="board"' in html and 'data-cell="100"' in html
    assert 'data-col="2"' in html                      # token placeret
    assert "🪤" in html                                 # trap-markør
    # kortets billede fra ## Kort: Testkort
    assert "/dm/media/Test/media/testkort.png" in html


def test_board_unknown_adventure_404(client):
    assert client.get("/dm/board/Nope/testkort").status_code == 404


def test_board_grid_calibration_persists(client):
    import dm_setups
    r = client.post("/dm/board/Test/testkort/grid",
                    data={"cell": "142.5", "x": "8", "y": "-3"})
    assert r.status_code == 204
    grid = dm_setups.load_setup("Test", "testkort")["grid"]
    assert grid == {"cell": 142.5, "x": 8, "y": -3}
    # kalibreringen slår igennem i vis-tilstand
    html = client.get("/dm/board/Test/testkort").get_data(as_text=True)
    assert 'data-cell="142.5"' in html


def test_board_tokens_save_persists_and_sanitizes(client):
    import dm_setups
    # Sæt et grid først, så vi kan se at token-gem lader det være urørt.
    client.post("/dm/board/Test/testkort/grid", data={"cell": "100", "x": "0", "y": "0"})
    r = client.post("/dm/board/Test/testkort/tokens", json=[
        {"kind": "pc", "ref": "tjorn", "col": "2", "row": 3},          # col som streng → int
        {"kind": "monster", "ref": "goblin", "label": "A", "col": 5, "row": 5, "hidden": True},
        {"kind": "note", "note": "kig her", "col": 1, "row": 1},
        {"kind": "gremlin", "col": 0, "row": 0},                       # ukendt kind → droppet
    ])
    assert r.status_code == 204
    setup = dm_setups.load_setup("Test", "testkort")
    assert setup["grid"]["cell"] == 100                               # grid urørt
    kinds = [t["kind"] for t in setup["tokens"]]
    assert kinds == ["pc", "monster", "note"]                        # gremlin sorteret fra
    assert setup["tokens"][0]["col"] == 2 and isinstance(setup["tokens"][0]["col"], int)
    assert setup["tokens"][1]["hidden"] is True


def test_play_board_markers_are_clickable_with_note(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 80}, "tokens": [
        {"kind": "trap", "ref": "spyd", "col": 3, "row": 3, "note": "DC 15 Reflex"}]})
    slug = _new(client, name="MK")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert 'data-marker="1"' in html and 'data-mkind="trap"' in html
    assert 'DC 15 Reflex' in html                       # noten bæres ud til klik-detalje


def test_board_tokens_unknown_adventure_404(client):
    assert client.post("/dm/board/Nope/testkort/tokens", json=[]).status_code == 404


def test_board_serves_palette_and_editor(client):
    html = client.get("/dm/board/Test/testkort").get_data(as_text=True)
    assert "dm-board-editor.js" in html and 'id="ed-palette"' in html
    assert "DmBoardEditor.init" in html


def test_edit_adventure_get_shows_source_and_summary(client):
    html = client.get("/dm/adventures/Test/edit").get_data(as_text=True)
    assert "<textarea" in html and "Første scene" in html      # rå kilde i boksen
    assert "2 scener" in html                                   # parse-resumé (MINI har 2)


def test_edit_adventure_post_saves_and_reparses(client):
    import dm_session as ds
    r = client.post("/dm/adventures/Test/edit",
                    data={"source": "---\ntitle: Ændret\n---\n# Ny scene\nTekst.\n"})
    assert r.status_code == 302                                 # redirect m/ saved=1
    assert ds.read_adventure_source("Test").startswith("---\ntitle: Ændret")
    assert ds.load_adventure("Test").scenes[0].title == "Ny scene"   # slår igennem


def test_edit_adventure_unknown_404(client):
    assert client.get("/dm/adventures/Nope/edit").status_code == 404


def test_new_adventure_creates_and_redirects_to_editor(client):
    r = client.post("/dm/adventures", data={"name": "Ulvevinter"})
    assert r.status_code == 302 and "/adventures/Ulvevinter/edit" in r.headers["Location"]
    assert "Ulvevinter" in ds.list_adventures()
    assert ds.load_adventure("Ulvevinter").scenes         # startskelet parser


def test_new_adventure_duplicate_and_empty_are_rejected(client):
    client.post("/dm/adventures", data={"name": "Dobbelt"})
    dup = client.post("/dm/adventures", data={"name": "Dobbelt"})
    assert "adv_error" in dup.headers["Location"]           # findes allerede
    empty = client.post("/dm/adventures", data={"name": "   "})
    assert "adv_error" in empty.headers["Location"]         # tomt navn


def test_play_has_board_link(client):
    slug = _new(client, name="BL")                     # scene 1 har @kort[testkort]
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "/dm/board/Test/testkort" in html and "Åbn bræt" in html


def test_play_renders_board_with_setup_tokens(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 80},
        "tokens": [{"kind": "monster", "ref": "goblin", "label": "A", "col": 3, "row": 2}]})
    slug = _new(client, name="BM")                     # aktiv scene har @kort[testkort]
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    # Selve brættet (kort+grid+token) vises inline i kamp-overblikket, ikke bare billedet.
    assert 'class="board"' in html and "dm-board.css" in html
    assert 'class="tok tok-monster"' in html and 'data-cell="80"' in html
    # + link tilbage til brættet med session-kontekst (?from=)
    assert f"from={slug}" in html


def test_board_back_link_needs_valid_from(client):
    slug = _new(client, name="BK")
    with_from = client.get(f"/dm/board/Test/testkort?from={slug}").get_data(as_text=True)
    assert "Tilbage til kampen" in with_from and f"/dm/play/{slug}" in with_from
    # ugyldig session ignoreres (intet dødt tilbage-link)
    bad = client.get("/dm/board/Test/testkort?from=findes-ikke").get_data(as_text=True)
    assert "Tilbage til kampen" not in bad


def test_play_gets_combat_class_when_encounter_active(enc_client):
    slug, _ = _start(enc_client)
    html = enc_client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert 'class="layout combat"' in html         # kamp-tilstand → bred konsol
    enc_client.post(f"/dm/api/encounter/{slug}/end")
    html = enc_client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert 'class="layout"' in html                 # ingen kamp → normal


def test_encounter_condition_toggle_and_end(enc_client):
    slug, _ = _start(enc_client)
    enc_client.post(f"/dm/api/encounter/{slug}/condition",
                    data={"cid": "goblin-b", "condition": "prone"})
    combs = {c["id"]: c for c in ds.load_session(slug).encounter["combatants"]}
    assert combs["goblin-b"]["conditions"] == ["prone"]
    enc_client.post(f"/dm/api/encounter/{slug}/end")
    assert ds.load_session(slug).encounter == {}


# ── Rum-scopet kamp (Midsommer/Kælderen har flere rum m/ egne rostre) ───────
import shutil
from pathlib import Path as _Path


@pytest.fixture
def midsommer_client(client, monkeypatch):
    """Kopiér det rigtige Midsommer-eventyr ind i den hermetiske ADVENTURES_DIR,
    så rum-scopet kamp kan testes mod dets Kælderen-scene (flere rum m/ egne
    rostre: Opbevaringsrum = tyv+kriger, Mordekains kammer = mordekain+skelet)."""
    src = _Path(__file__).parent / "adventures" / "Midsommer"
    shutil.copytree(src, ds.ADVENTURES_DIR / "Midsommer")
    import dm_party
    monkeypatch.setattr(dm_party, "CHARACTERS_DIR", _Path("defaults"))
    return client


def test_encounter_start_room_scoped_excludes_other_rooms(midsommer_client):
    slug = _new(midsommer_client, name="Kælder", adventure="Midsommer", party=["tjorn"])
    midsommer_client.get(f"/dm/play/{slug}?scene=kaelderen")   # naviger til Kælderen
    midsommer_client.post(f"/dm/api/encounter/{slug}/start",
                          data={"room": "opbevaringsrum"})
    enc = ds.load_session(slug).encounter
    refs = {c["ref"] for c in enc["combatants"]}
    assert {"tyv", "kriger"} <= refs
    assert "mordekain" not in refs and "skelet" not in refs
    assert enc["room"] == "opbevaringsrum"


def test_encounter_start_without_room_includes_all_rooms(midsommer_client):
    # Bagudkompatibilitet: den gamle scene-brede "Start kamp" (ingen room-felt)
    # samler stadig ALLE rums monstre i én kamp.
    slug = _new(midsommer_client, name="Kælder2", adventure="Midsommer", party=["tjorn"])
    midsommer_client.get(f"/dm/play/{slug}?scene=kaelderen")
    midsommer_client.post(f"/dm/api/encounter/{slug}/start")
    enc = ds.load_session(slug).encounter
    refs = {c["ref"] for c in enc["combatants"]}
    assert {"tyv", "kriger", "mordekain", "skelet"} <= refs
    assert enc["room"] is None


def test_play_shows_room_start_buttons_for_rooms_with_monsters(midsommer_client):
    slug = _new(midsommer_client, name="Kælder3", adventure="Midsommer", party=["tjorn"])
    html = midsommer_client.get(f"/dm/play/{slug}?scene=kaelderen").get_data(as_text=True)
    assert 'class="enc-f room-start"' in html
    assert 'name="room" value="opbevaringsrum"' in html
    assert 'name="room" value="mordekains-kammer"' in html
    assert "⚔ Start kamp fra dette rum" in html
    # Skeletreste-rum har hverken monstre eller fælder (kun beskrivelse) →
    # ingen start-knap for det rum.
    assert 'value="skeletreste-rum"' not in html
    # Indgang har KUN en fælde (@faelde), ingen væsener → ingen start-knap
    # (fælde-kun-rum gater knappen fra; fælder-i-kamp er en separat opgave).
    assert 'value="indgang"' not in html


# ── Bestiarie-fane ──────────────────────────────────────────────────────────
def test_bestiary_lists_adventure_monsters(client):
    html = client.get("/dm/bestiary/Test").get_data(as_text=True)
    assert "📖 Bestiar" in html
    assert "Goblin (kriger)" in html          # roster-monster resolvet fra bestiar
    assert "2× i eventyret" in html           # 2x @monster[goblin] i scenens roster
    assert "Bestiar" in html                  # origin-badge (delt bestiar, ikke eventyr-lokal)


def test_bestiary_lists_adventure_traps(client):
    html = client.get("/dm/bestiary/Test").get_data(as_text=True)
    assert "🪤 Fælder" in html
    assert "Basic Arrow Trap" in html         # @faelde[basic-arrow-trap] i prosaen → opløst statblok
    assert "+10 ranged" in html               # fælde-statblokkens angrebslinje


def test_bestiary_includes_board_trap_markers_and_marks_unknown(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {}, "tokens": [
        {"kind": "trap", "col": 1, "row": 1, "ref": "ukendt-faelde"}]})
    html = client.get("/dm/bestiary/Test").get_data(as_text=True)
    assert "ukendt-faelde" in html                    # ref-bundet bræt-markør samlet op
    assert "findes ikke i kataloget" in html          # uopslåelig ref → markeret som hul


def test_bestiary_lists_adventure_doors(client):
    html = client.get("/dm/bestiary/Test").get_data(as_text=True)
    assert "🚪 Døre" in html
    assert "Jerndør" in html                  # @dør[iron-door] i prosaen → opløst statblok
    assert "Hardness" in html                 # dør-statblokkens felter


def test_bestiary_includes_board_door_markers_and_marks_unknown(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {}, "tokens": [
        {"kind": "door", "col": 1, "row": 1, "ref": "ukendt-dor"}]})
    html = client.get("/dm/bestiary/Test").get_data(as_text=True)
    assert "ukendt-dor" in html                       # ref-bundet bræt-markør samlet op
    assert "findes ikke i kataloget" in html          # uopslåelig ref → markeret som hul


def test_bestiary_back_link_to_session(client):
    slug = _new(client, name="Kamp")
    html = client.get(f"/dm/bestiary/Test?from={slug}").get_data(as_text=True)
    assert "Tilbage til kampen" in html and f"/dm/play/{slug}" in html


def test_bestiary_unknown_adventure_404(client):
    assert client.get("/dm/bestiary/FindesIkke").status_code == 404


def test_play_nav_links_to_bestiary(client):
    slug = _new(client, name="Nav")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    assert "/dm/bestiary/Test" in html and "📖 Bestiar" in html


# ── Fælder (@faelde → statblok-inspector) ────────────────────────────────────
def test_faelde_reference_is_clickable_statblok(client):
    slug = _new(client, name="Fælde")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    # @faelde[...] rendres som klikbar ent-stat (som @monster), ikke ren tekst.
    assert 'ent-stat" data-stat="faelde/basic-arrow-trap"' in html


def test_statblock_endpoint_resolves_trap(client):
    html = client.get("/dm/api/statblock/Test/faelde/basic-arrow-trap").get_data(as_text=True)
    assert "Basic Arrow Trap" in html
    assert "Fælde" in html                          # origin-badge
    assert "Search DC" in html and "20" in html
    assert "+10 ranged" in html                     # angrebs-linjen


def test_statblock_endpoint_unknown_trap_is_graceful(client):
    r = client.get("/dm/api/statblock/Test/faelde/findes-ikke")
    assert r.status_code == 200                      # ingen 500 — pæn "ingen data"
    assert "findes-ikke" in r.get_data(as_text=True)


def test_board_binds_trap_marker_to_statblock(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 50}, "tokens": [
        {"kind": "trap", "col": 1, "row": 1, "ref": "basic-arrow-trap", "note": "klik!"}]})
    html = client.get("/dm/board/Test/testkort").get_data(as_text=True)
    assert 'data-mref="basic-arrow-trap"' in html      # markøren bærer sin fælde-ref
    assert "Basic Arrow Trap" in html                   # fælde-katalog sendt til editoren


# ── Døre (@dør/@door → statblok-inspector) ───────────────────────────────────
def test_dor_reference_is_clickable_statblok(client):
    slug = _new(client, name="Dør")
    html = client.get(f"/dm/play/{slug}").get_data(as_text=True)
    # @dør[...] rendres som klikbar ent-stat, med KANONISK ascii data-stat ("door"),
    # selvom forfatteren skrev dansk "dør".
    assert 'ent-stat" data-stat="door/iron-door"' in html


def test_statblock_endpoint_resolves_door(client):
    html = client.get("/dm/api/statblock/Test/door/iron-door").get_data(as_text=True)
    assert "Jerndør" in html
    assert "Dør" in html                              # origin-badge
    assert "Hardness" in html and "10" in html
    assert "Break DC" in html


def test_statblock_endpoint_unknown_door_is_graceful(client):
    r = client.get("/dm/api/statblock/Test/door/findes-ikke")
    assert r.status_code == 200                        # ingen 500 — pæn "ingen data"
    assert "findes-ikke" in r.get_data(as_text=True)


def test_board_binds_door_marker_to_statblock(client):
    import dm_setups
    dm_setups.save_setup("Test", "testkort", {"grid": {"cell": 50}, "tokens": [
        {"kind": "door", "col": 1, "row": 1, "ref": "iron-door", "note": "knirker"}]})
    html = client.get("/dm/board/Test/testkort").get_data(as_text=True)
    assert 'data-mref="iron-door"' in html              # markøren bærer sin dør-ref
    assert '"id": "iron-door"' in html                  # dør-katalog sendt til editoren (JS-config)
