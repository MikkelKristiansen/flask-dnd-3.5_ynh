"""Tests for dm_board (ren visningsmodel) + dm_setups (hermetisk load/save)."""
import dm_board as B
import dm_session as S
import dm_setups


class _Adv:
    """Minimal adventure-stub: kun statblock()-opslag bruges af board_view."""
    def __init__(self, stat=None):
        self._stat = stat or {}
    def statblock(self, ref):
        return self._stat.get(ref)


def _setup():
    return {"grid": {"cell": 100, "x": 5, "y": 5}, "tokens": [
        {"kind": "pc", "ref": "tjorn", "col": 1, "row": 2},
        {"kind": "monster", "ref": "goblin", "label": "A", "col": 3, "row": 3},
        {"kind": "monster", "ref": "goblin", "label": "B", "col": 4, "row": 3},
        {"kind": "trap", "ref": "spyd", "col": 0, "row": 0, "note": "DC15"},
        {"kind": "npc", "ref": "skurk", "col": 9, "row": 1, "hidden": True},
    ]}


def test_board_view_resolves_kinds():
    adv = _Adv({"goblin": {"name": "Goblin"}, "skurk": {"name": "Skurken"}})
    bv = B.board_view(_setup(), adv, db=None, audience="dm")
    by = {t["name"]: t for t in bv["tokens"]}
    assert bv["grid"] == {"cell": 100, "x": 5, "y": 5}
    assert by["tjorn"]["portrait"] == "tjorn" and by["tjorn"]["kind"] == "pc"
    assert by["Goblin A"]["label"] == "A" and "color" in by["Goblin A"]
    assert by["DC15"]["icon"] == "🪤"                 # trap-markør


def test_same_monster_type_shares_color():
    adv = _Adv({"goblin": {"name": "Goblin"}})
    toks = B.board_view(_setup(), adv)["tokens"]
    ga = next(t for t in toks if t["name"] == "Goblin A")
    gb = next(t for t in toks if t["name"] == "Goblin B")
    assert ga["color"] == gb["color"]                 # stabil farve pr. type


def test_player_audience_hides_hidden_tokens():
    dm = B.board_view(_setup(), _Adv(), audience="dm")["tokens"]
    pl = B.board_view(_setup(), _Adv(), audience="player")["tokens"]
    assert any(t.get("hidden") for t in dm)           # DM ser den skjulte npc
    assert all(not t.get("hidden") for t in pl)       # player ser den ikke
    assert len(pl) == len(dm) - 1


def test_setup_load_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "ADVENTURES_DIR", tmp_path / "adventures")
    assert dm_setups.load_setup("Ukendt", "kort") == {"grid": {}, "tokens": []}


def test_sanitize_tokens_drops_bad_and_coerces():
    raw = [
        {"kind": "pc", "ref": "tjorn", "col": "3", "row": 4},         # streng-col → int
        {"kind": "monster", "ref": "goblin", "label": "A", "col": 1, "row": 1, "hidden": True},
        {"kind": "note", "note": " kig ", "col": 0, "row": 0},         # trimmes
        {"kind": "ukendt", "col": 0, "row": 0},                        # ukendt kind → væk
        "ikke en dict",                                                # ignoreres
        {"kind": "trap", "col": "x", "row": None},                     # dårlig col/row → 0
    ]
    out = dm_setups.sanitize_tokens(raw)
    assert [t["kind"] for t in out] == ["pc", "monster", "note", "trap"]
    assert out[0]["col"] == 3 and isinstance(out[0]["col"], int)
    assert out[1]["hidden"] is True
    assert out[2]["note"] == "kig" and "ref" not in out[2]            # tom ref udeladt
    assert out[3]["col"] == 0 and out[3]["row"] == 0


def test_board_view_carries_ref_and_note():
    setup = {"grid": {}, "tokens": [
        {"kind": "trap", "ref": "spyd", "col": 0, "row": 0, "note": "DC15"}]}
    t = B.board_view(setup)["tokens"][0]
    assert t["ref"] == "spyd" and t["note"] == "DC15"    # editoren kan gemme dem igen


def test_setup_save_roundtrip(tmp_path, monkeypatch):
    adv = tmp_path / "adventures"
    (adv / "Test").mkdir(parents=True)
    monkeypatch.setattr(S, "ADVENTURES_DIR", adv)
    dm_setups.save_setup("Test", "kaelder", _setup())
    back = dm_setups.load_setup("Test", "kaelder")
    assert back["grid"] == {"cell": 100, "x": 5, "y": 5}
    assert len(back["tokens"]) == 5
