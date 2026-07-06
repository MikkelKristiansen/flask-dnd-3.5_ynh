"""Tests for dm_parser — mod den rigtige fixtur adventures/Midsommer/adventure.md
plus små hermetiske enheds-tests."""
import os

import dm_parser as P

FIXTURE = os.path.join(os.path.dirname(__file__),
                       "adventures", "Midsommer", "adventure.md")


def _adv():
    with open(FIXTURE, encoding="utf-8") as f:
        return P.parse_adventure(f.read())


def _scene(adv, sid):
    return next(s for s in adv.scenes if s.id == sid)


def _only(blocks, kind):
    return next(b for b in blocks if b.kind == kind)


# ── slugify ──────────────────────────────────────────────────────────────────
def test_slugify_danish_chars():
    assert P.slugify("Brev fra Mordekain") == "brev-fra-mordekain"
    assert P.slugify("Besked på døren") == "besked-paa-doeren"
    assert P.slugify("Kælderen") == "kaelderen"
    assert P.slugify("Den gamle bro") == "den-gamle-bro"


# ── frontmatter ──────────────────────────────────────────────────────────────
def test_frontmatter():
    adv = _adv()
    assert adv.title == "Midsommer"
    assert adv.party == ["tjorn", "faelyn", "kaehlen"]
    assert adv.meta["author"] == "Mikkel Kristiansen"
    assert adv.meta["subtitle"].startswith("Et")
    # title/party ligger IKKE dobbelt i meta
    assert "title" not in adv.meta and "party" not in adv.meta


def test_frontmatter_optional():
    adv = P.parse_adventure("# Kun en scene\n\nTekst.\n")
    assert adv.title == "" and adv.party == []
    assert [s.id for s in adv.scenes] == ["kun-en-scene"]


# ── scener ───────────────────────────────────────────────────────────────────
def test_scenes_and_ids():
    ids = [s.id for s in _adv().scenes]
    assert "midsommersaften" in ids
    assert "den-gamle-bro" in ids
    assert "kaelderen" in ids
    # '# Dokumenter' er appendiks, ikke en scene
    assert "dokumenter" not in ids


def test_scene_roster_counts():
    s = _scene(_adv(), "lejren-i-fjeldene")
    entries = {(e.count, e.type, e.id) for e in _only(s.blocks, "roster").entries}
    assert entries == {(1, "monster", "kriger"), (2, "monster", "tyv")}


def test_scene_leading_kort_embed():
    s = _scene(_adv(), "midsommersaften")
    emb = _only(s.blocks, "embed")
    assert emb.entity.type == "kort" and emb.entity.id == "heltenes-hus"


def test_conditional_readaloud_captions():
    s = _scene(_adv(), "midsommersaften")
    caps = {b.caption for b in s.blocks if b.kind == "readaloud" and b.caption}
    assert {"Hvis tjek klares", "Hvis tjek misses"} <= caps


def test_prose_captures_entities():
    s = _scene(_adv(), "advarsel")
    prose = _only(s.blocks, "prose")
    assert "@brev[besked-paa-doeren]" in [e.raw for e in prose.entities]


def test_blockquote_without_leading_space():
    # '>Eventyret…' (uden mellemrum efter >) skal stadig blive read-aloud
    s = _scene(_adv(), "om-eventyret-og-dets-plot")
    ra = [b for b in s.blocks if b.kind == "readaloud"]
    assert ra and ra[0].text.startswith("Eventyret starter i jeres hjemby Birkedal")


def test_named_section_becomes_subheading():
    s = _scene(_adv(), "om-eventyret-og-dets-plot")
    assert any(b.kind == "subheading" and b.text == "Baggrund" for b in s.blocks)


# ── rum (dungeon) ────────────────────────────────────────────────────────────
def test_rooms_parsed():
    s = _scene(_adv(), "kaelderen")
    rooms = [b for b in s.blocks if b.kind == "room"]
    assert [r.title for r in rooms] == \
        ["Indgang", "Skeletreste-rum", "Opbevaringsrum", "Mordekains kammer"]


def test_room_fields():
    s = _scene(_adv(), "kaelderen")
    indgang = next(b for b in s.blocks if b.kind == "room")
    fælde = _only(indgang.blocks, "roster").entries[0]
    assert (fælde.type, fælde.id) == ("faelde", "spydfaelde")
    besk = _only(indgang.blocks, "prose")
    assert besk.label == "Beskrivelse"


# ── dokumenter / resolve ─────────────────────────────────────────────────────
def test_documents_collected():
    docs = _adv().documents
    assert ("brev", "brev-fra-mordekain") in docs
    assert ("brev", "besked-paa-doeren") in docs
    assert ("kort", "kaelderen") in docs
    assert len([k for k in docs if k[0] == "kort"]) == 4


def test_document_local_resolve():
    adv = _adv()
    d = adv.documents[("brev", "brev-fra-mordekain")]
    assert d.type == "brev" and d.title == "Brev fra Mordekain"
    text = " ".join(getattr(b, "text", "") for b in d.blocks)
    assert "lejesvende" in text.lower()
    # @brev[...] refereret 3× resolver til samme definition
    e = P.Entity("brev", "brev-fra-mordekain", "@brev[brev-fra-mordekain]")
    assert adv.resolve(e) is d
    # ekstern entity (monster) har ingen appendiks-def → None
    assert adv.resolve(P.Entity("monster", "kriger", "@monster[kriger]")) is None


def test_kort_definition_is_image():
    d = _adv().documents[("kort", "kaelderen")]
    img = _only(d.blocks, "image")
    assert img.src.endswith(".png")


# ── hermetiske enheds-tests ──────────────────────────────────────────────────
def test_roster_default_count_is_one():
    assert P._roster_entries("@monster[ulv]") == [P.RosterEntry(1, "monster", "ulv")]
    assert P._roster_entries("3x @monster[goblin]") == [P.RosterEntry(3, "monster", "goblin")]


def test_html_comment_stripped():
    raw = "---\ntitle: T\n---\n# Dokumenter\n<!-- skjult -->\n## Brev: Test\n> Hej\n"
    adv = P.parse_adventure(raw)
    assert ("brev", "test") in adv.documents
    assert adv.title == "T"


def test_generic_appendix_type():
    # appendiks-typer er generiske: en '## NPC: …' bliver en npc-definition
    raw = "# Dokumenter\n## NPC: Gamle Bram\n> Kroværten i Birkedal.\n"
    adv = P.parse_adventure(raw)
    assert ("npc", "gamle-bram") in adv.documents


def test_readaloud_caption_split():
    raw = "# S\n## Handling\n> **Hvis låst:** Døren giver sig ikke.\n"
    ra = _only(P.parse_adventure(raw).scenes[0].blocks, "readaloud")
    assert ra.caption == "Hvis låst"
    assert ra.text == "Døren giver sig ikke."
