"""Tests for Handy Haversack-tilstanden — indhold uden for bærevægten.

Tilstanden "haversack" fjerner vægt fra encumbrance-regnskabet, så den skal
kunne modsiges: ligger der ting i den uden at en haversack faktisk bæres, er
tallet på arket forkert, og `owned` skal afsløre det.
Kør: python -m pytest test_haversack.py
"""
import db as db_module
import items
from models import InventoryItem as I

SACK = "magic_items/handy_haversack"
TENT = "items/tent"          # 20 lb (Medium)


def _sack(state="backpack"):
    return I(ref=SACK, state=state)


def test_indhold_taeller_ikke_i_baaret_vaegt():
    baaret = [_sack(), I(ref=TENT, state="backpack")]
    i_sack = [_sack(), I(ref=TENT, state="haversack")]
    assert items.carried_weight(i_sack, db_module) < items.carried_weight(baaret, db_module)


def test_haversacken_selv_taeller_med():
    """Beholderen vejer altid sine 5 lb — det er hele prisen for rabatten."""
    tom = items.carried_weight([_sack()], db_module)
    assert tom == 5.0


def test_vaegten_er_uafhaengig_af_indholdet():
    """SRD: 'the backpack always weighs only 5 pounds' uanset hvad der er i."""
    lidt = items.carried_weight([_sack(), I(ref=TENT, state="haversack")], db_module)
    meget = items.carried_weight([_sack(), I(ref=TENT, state="haversack", qty=20)], db_module)
    assert lidt == meget == 5.0


def test_owned_er_falsk_uden_baaret_haversack():
    st = items.haversack_status([I(ref=TENT, state="haversack")], db_module)
    assert st["owned"] is False and st["count"] == 1


def test_droppet_haversack_taeller_ikke_som_baaret():
    st = items.haversack_status(
        [_sack("dropped"), I(ref=TENT, state="haversack")], db_module)
    assert st["owned"] is False


def test_over_kapacitet():
    under = items.haversack_status([_sack(), I(ref=TENT, state="haversack", qty=5)], db_module)
    over = items.haversack_status([_sack(), I(ref=TENT, state="haversack", qty=7)], db_module)
    assert under["over"] is False        # 100 lb
    assert over["over"] is True          # 140 lb > 120


def test_tilstanden_overlever_gem_og_laes(tmp_path):
    import character as cm
    import persistence
    p = tmp_path / "t.yaml"
    p.write_bytes(open("defaults/tjorn.yaml", "rb").read())
    ch = cm.load_character(str(p))
    inv = list(ch.inventory) + [_sack(), I(ref=TENT, state="haversack")]
    persistence.save_character(str(p), {"inventory": inv})
    genlaest = cm.load_character(str(p))
    assert any(i.state == "haversack" for i in genlaest.inventory)
