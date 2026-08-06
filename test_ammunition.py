"""Tests for special materials på ammunition (pile, bolte, slyngesten).

SRD prissætter ammunition PER STYK — "The masterwork quality adds 300 gp to the
cost of a normal weapon (or 6 gp to the cost of a single unit of ammunition)" —
mens kataloget opgiver ammunition PER BUNDT (arrows_20 = 1 gp for 20). Satserne
ganges derfor med bundle-størrelsen.
Kør: python -m pytest test_ammunition.py
"""
import catalog
import db as db_module
import items

ARROWS = "arrows_20"
BULLETS = "sling_bullets_10"


def _keys(item_id):
    return {m["key"] for m in items.material_modifiers(db_module.get_item(item_id), "items")}


def _tillaeg_pr_stk(item_id, key):
    """Materialets eget bidrag pr. stykke ammunition, uden basisprisen."""
    rec = db_module.get_item(item_id)
    delta = next(m["delta_cp"] for m in items.material_modifiers(rec, "items") if m["key"] == key)
    return delta / 100 / rec["bundle"]


# ── Pris pr. styk mod SRD ───────────────────────────────────────────────────

def test_masterwork_er_6_gp_pr_stk():
    """SRD: '(or 6 gp to the cost of a single unit of ammunition)'."""
    assert _tillaeg_pr_stk(ARROWS, "masterwork") == 6
    assert _tillaeg_pr_stk(BULLETS, "masterwork") == 6


def test_adamantine_er_60_gp_pr_stk():
    assert _tillaeg_pr_stk(ARROWS, "adamantine") == 60


def test_soelv_er_2_gp_pr_stk():
    assert _tillaeg_pr_stk(ARROWS, "silvered") == 2


def test_cold_iron_fordobler_prisen():
    rec = db_module.get_item(ARROWS)
    delta = next(m["delta_cp"] for m in items.material_modifiers(rec, "items")
                 if m["key"] == "cold_iron")
    assert rec["cost_cp"] + delta == rec["cost_cp"] * 2


def test_satserne_skalerer_med_bundtstoerrelsen():
    """20 pile koster dobbelt så meget at gøre adamantine som 10 bolte."""
    pile = next(m["delta_cp"] for m in items.material_modifiers(db_module.get_item(ARROWS), "items")
                if m["key"] == "adamantine")
    bolte = next(m["delta_cp"] for m in items.material_modifiers(
        db_module.get_item("crossbow_bolts_10"), "items") if m["key"] == "adamantine")
    assert pile == bolte * 2


# ── Tilgængelighed ──────────────────────────────────────────────────────────

def test_pile_kan_vaere_baade_trae_og_metal():
    """Træskaft med metalspids — SRD nævner pile under både darkwood og
    cold iron ('An arrow could be made of cold iron')."""
    assert {"darkwood", "cold_iron", "adamantine", "silvered"} <= _keys(ARROWS)


def test_slyngesten_er_ikke_trae():
    assert "darkwood" not in _keys(BULLETS)
    assert {"cold_iron", "adamantine"} <= _keys(BULLETS)


def test_mithral_tilbydes_ikke_paa_ammunition():
    """Bevidst udeladt: SRD's mithral-tabel har ingen ammunition-række, og halv
    vægt er uden betydning for et projektil."""
    assert "mithral" not in _keys(ARROWS)


def test_almindeligt_gear_har_ingen_materialevalg():
    assert items.material_modifiers(db_module.get_item("torch"), "items") == []


def test_ukendt_raekke_giver_tom_liste():
    assert items.material_modifiers(None, "items") == []
    assert catalog.apply_material_overlay(None, "items", ["masterwork"]) == {}


# ── Butik og overlay ────────────────────────────────────────────────────────

def test_butikken_viser_materialevalg_paa_ammunition():
    """_item_entry havde tidligere hardkodet en tom modifiers-liste."""
    entry = catalog._item_entry(db_module.get_item(ARROWS), recommended=set(), size="medium")
    assert {m["key"] for m in entry["modifiers"]} == _keys(ARROWS)


def test_overlay_saetter_materiale_paa_ammunition():
    ov = catalog.apply_material_overlay(db_module.get_item(ARROWS), "items", ["adamantine"])
    assert ov["material"] == "adamantine" and "Adamantine" in ov["name"]


def test_overlay_afviser_darkwood_paa_slyngesten():
    assert catalog.apply_material_overlay(
        db_module.get_item(BULLETS), "items", ["darkwood"]) == {}


def test_soelv_virker_ikke_sammen_med_cold_iron_paa_ammunition():
    ov = catalog.apply_material_overlay(
        db_module.get_item(ARROWS), "items", ["cold_iron", "silvered"])
    assert ov["material"] == "cold_iron" and "Silver" not in ov["name"]
