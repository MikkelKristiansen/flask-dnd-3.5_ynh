"""Tests for darkwood — det første special material med rigtige regel-effekter.

SRD: darkwood-emner er masterwork, vejer halvt, og et darkwood-SKJOLDS armor
check penalty er 2 bedre end et ordinært skjold af dens type. Prisen er
masterwork-versionen + 10 gp per pund original vægt.
Kør: python -m pytest test_darkwood.py
"""
import catalog
import db as db_module
import items
from models import InventoryItem as I

LWS = "light_wooden_shield"


def _keys(record, table, size="medium"):
    return {m["key"] for m in items.material_modifiers(record, table, size)}


# ── Pris ────────────────────────────────────────────────────────────────────

def test_heavy_wooden_shield_rammer_srds_egen_pris():
    """SRD's tabel over specific shields: 'Darkwood shield' = 257 gp."""
    rec = db_module.get_armor("heavy_wooden_shield")
    dw = next(m for m in items.material_modifiers(rec, "armor") if m["key"] == "darkwood")
    assert (rec["cost_cp"] + dw["delta_cp"]) / 100 == 257


def test_light_wooden_shield_pris():
    rec = db_module.get_armor(LWS)
    dw = next(m for m in items.material_modifiers(rec, "armor") if m["key"] == "darkwood")
    assert (rec["cost_cp"] + dw["delta_cp"]) / 100 == 203


def test_prisen_foelger_stoerrelsen():
    """10 gp/lb regnes af den STØRRELSES-JUSTEREDE vægt, så Small koster mindre."""
    rec = db_module.get_armor(LWS)
    m = next(x for x in items.material_modifiers(rec, "armor", "medium") if x["key"] == "darkwood")
    s = next(x for x in items.material_modifiers(rec, "armor", "small") if x["key"] == "darkwood")
    assert s["delta_cp"] < m["delta_cp"]


# ── Tilgængelighed ──────────────────────────────────────────────────────────

def test_tilbydes_paa_traeskjolde():
    for oid in (LWS, "heavy_wooden_shield", "tower_shield"):
        assert "darkwood" in _keys(db_module.get_armor(oid), "armor"), oid


def test_tilbydes_ikke_paa_metalskjolde():
    """Buckler er metal (SRD-hardness 10), trods 'wooden'-lydende selskab."""
    for oid in ("heavy_steel_shield", "light_steel_shield", "buckler"):
        assert "darkwood" not in _keys(db_module.get_armor(oid), "armor"), oid


def test_tilbydes_ikke_paa_srds_egne_modeksempler():
    """SRD nævner netop battleaxe og mace som emner der IKKE får fordel."""
    for oid in ("battleaxe", "mace_heavy"):
        assert "darkwood" not in _keys(db_module.get_weapon(oid), "weapons"), oid


def test_tilbydes_paa_bue_og_spyd():
    """SRD's egne darkwood-eksempler — de har metal=NULL, så `metal` duer ikke."""
    for oid in ("longbow", "spear", "quarterstaff"):
        assert "darkwood" in _keys(db_module.get_weapon(oid), "weapons"), oid


# ── Vægt ────────────────────────────────────────────────────────────────────

def test_vaegten_halveres():
    alm = items.resolve_item(I(ref=f"armor/{LWS}"), db_module)["unit_weight"]
    dw = items.resolve_item(I(ref=f"armor/{LWS}", material="darkwood"), db_module)["unit_weight"]
    assert dw == alm / 2


def test_vaegt_halveres_oveni_stoerrelse():
    """Small halverer allerede; darkwood halverer igen (5 → 2,5 → 1,25)."""
    dw = items.resolve_item(I(ref=f"armor/{LWS}", material="darkwood"), db_module, "small")
    assert dw["unit_weight"] == 1.25


# ── ACP ─────────────────────────────────────────────────────────────────────

def test_acp_er_2_bedre_end_ordinaer_med_loft_ved_nul():
    rec = db_module.get_armor(LWS)                       # ordinær ACP -1
    eff = items._effective_armor_row(rec, I(ref=f"armor/{LWS}", material="darkwood"))
    assert eff["armor_check"] == 0                       # -1 + 2 = 1 → loft 0


def test_acp_paa_tower_shield():
    rec = db_module.get_armor("tower_shield")            # ordinær ACP -10
    eff = items._effective_armor_row(rec, I(ref="armor/tower_shield", material="darkwood"))
    assert eff["armor_check"] == -8


def test_darkwood_stacker_ikke_med_masterwork():
    """De 2 er målt fra ORDINÆR og erstatter masterworks 1 — ikke -1+1+2."""
    rec = db_module.get_armor("heavy_wooden_shield")     # ordinær ACP -2
    baade = items._effective_armor_row(
        rec, I(ref="armor/heavy_wooden_shield", material="darkwood", masterwork=True))
    assert baade["armor_check"] == 0                     # -2 + 2, ikke -2 + 3


# ── Butiks-overlay og persistering ──────────────────────────────────────────

def test_overlay_saetter_masterwork_implicit():
    """Darkwood ER masterwork i SRD — et våben skal derfor også få +1 til-hit."""
    ov = catalog.apply_material_overlay(db_module.get_weapon("quarterstaff"), "weapons", ["darkwood"])
    assert ov["material"] == "darkwood" and ov["masterwork"] is True and ov["bonus"] == 1


def test_overlay_afviser_darkwood_paa_metal():
    assert catalog.apply_material_overlay(db_module.get_weapon("battleaxe"), "weapons", ["darkwood"]) == {}


def test_material_overlever_gem_og_laes(tmp_path):
    import character as cm
    import persistence
    p = tmp_path / "t.yaml"
    p.write_bytes(open("defaults/tjorn.yaml", "rb").read())
    ch = cm.load_character(str(p))
    inv = list(ch.inventory) + [I(ref=f"armor/{LWS}", state="worn", material="darkwood")]
    persistence.save_character(str(p), {"inventory": inv})
    genlaest = cm.load_character(str(p))
    assert any(i.material == "darkwood" for i in genlaest.inventory)
