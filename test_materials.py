"""Tests for adamantine og dragonhide (SRD special materials).

Adamantine: kun emner der normalt er af metal; altid masterwork; rustning giver
DR 1/2/3 efter kategori (BEREGNES ikke — appen har ingen karakter-DR).
Dragonhide: kun rustning og skjolde; altid masterwork; ikke metal, så en druide
kan bære den uden straf — det er hele pointen med materialet.
Kør: python -m pytest test_materials.py
"""
import catalog
import db as db_module
import items
import rules
from models import InventoryItem as I


def _keys(record, table):
    return {m["key"] for m in items.material_modifiers(record, table)}


def _delta(record, table, key):
    return next(m["delta_cp"] for m in items.material_modifiers(record, table) if m["key"] == key)


# ── Adamantine: pris ────────────────────────────────────────────────────────

def test_adamantine_faste_tillaeg_pr_kategori():
    """SRD's tabel: light +5.000, medium +10.000, heavy +15.000, våben +3.000.
    Tillæggene er FASTE og inkluderer masterwork — ikke deltaer oven i den."""
    for oid, gp in (("chain_shirt", 5000), ("breastplate", 10000), ("full_plate", 15000)):
        assert _delta(db_module.get_armor(oid), "armor", "adamantine") == gp * 100, oid
    assert _delta(db_module.get_weapon("longsword"), "weapons", "adamantine") == 300000


# ── Adamantine: tilgængelighed ──────────────────────────────────────────────

def test_adamantine_kun_paa_metal_rustning():
    for oid in ("chain_shirt", "full_plate", "heavy_steel_shield"):
        assert "adamantine" in _keys(db_module.get_armor(oid), "armor"), oid
    for oid in ("leather", "hide", "light_wooden_shield"):
        assert "adamantine" not in _keys(db_module.get_armor(oid), "armor"), oid


def test_studded_leather_er_ikke_adamantine_egnet():
    """druid_ok=0 (metalnitter) er IKKE det samme som 'normally made of metal'."""
    rec = db_module.get_armor("studded_leather")
    assert rec["druid_ok"] == 0                       # forbudt for druider …
    assert "adamantine" not in _keys(rec, "armor")    # … men stadig læder


def test_adamantine_ikke_paa_traevaaben():
    """SRD: 'An arrow could be made of adamantine, but a quarterstaff could not.'
    Buer har metal=NULL i data, så `metal` alene ville have sluppet dem igennem."""
    for oid in ("quarterstaff", "longbow", "shortbow"):
        assert "adamantine" not in _keys(db_module.get_weapon(oid), "weapons"), oid


def test_adamantine_paa_metalvaaben():
    for oid in ("longsword", "battleaxe", "dagger"):
        assert "adamantine" in _keys(db_module.get_weapon(oid), "weapons"), oid


# ── Adamantine: effekt ──────────────────────────────────────────────────────

def test_adamantine_dr_pr_kategori():
    assert (items.adamantine_dr("light"), items.adamantine_dr("medium"),
            items.adamantine_dr("heavy")) == (1, 2, 3)
    assert items.adamantine_dr("shield") == 0


def test_adamantine_er_masterwork():
    rec = db_module.get_armor("full_plate")           # ordinær ACP -6
    eff = items._effective_armor_row(rec, I(ref="armor/full_plate", material="adamantine"))
    assert eff["armor_check"] == int(rec["armor_check"]) + 1


def test_adamantine_ophaever_ikke_druideforbud():
    """Adamantine er metal — en druide må stadig ikke bære den."""
    rec = db_module.get_armor("full_plate")
    eff = items._effective_armor_row(rec, I(ref="armor/full_plate", material="adamantine"))
    assert rules.druid_armor_violations("Druid", eff, None)


# ── Dragonhide ──────────────────────────────────────────────────────────────

def test_dragonhide_koster_dobbelt_masterwork():
    """full plate 1.500 → masterwork 1.650 → dragonhide 3.300."""
    rec = db_module.get_armor("full_plate")
    assert (rec["cost_cp"] + _delta(rec, "armor", "dragonhide")) / 100 == 3300


def test_dragonhide_tilbydes_paa_al_rustning_og_skjold():
    for oid in ("full_plate", "leather", "hide", "heavy_steel_shield", "light_wooden_shield"):
        assert "dragonhide" in _keys(db_module.get_armor(oid), "armor"), oid


def test_dragonhide_ikke_paa_vaaben():
    """SRD: armorsmiths laver 'armor or shields' — ikke våben."""
    assert "dragonhide" not in _keys(db_module.get_weapon("longsword"), "weapons")


def test_dragonhide_lader_en_druide_baere_metalrustning():
    """Hele pointen: 'because dragonhide armor isn't made of metal, druids can
    wear it without penalty'."""
    rec = db_module.get_armor("full_plate")
    alm = items._effective_armor_row(rec, I(ref="armor/full_plate"))
    dh = items._effective_armor_row(rec, I(ref="armor/full_plate", material="dragonhide"))
    assert rules.druid_armor_violations("Druid", alm, None) == ["Full Plate"]
    assert rules.druid_armor_violations("Druid", dh, None) == []


def test_dragonhide_er_masterwork():
    rec = db_module.get_armor("full_plate")
    eff = items._effective_armor_row(rec, I(ref="armor/full_plate", material="dragonhide"))
    assert eff["armor_check"] == int(rec["armor_check"]) + 1


# ── Butiks-overlay ──────────────────────────────────────────────────────────

def test_overlay_saetter_materiale_og_masterwork():
    for key in ("adamantine", "dragonhide"):
        ov = catalog.apply_material_overlay(db_module.get_armor("full_plate"), "armor", [key])
        assert ov["material"] == key and ov["masterwork"] is True, key


def test_overlay_afviser_ugyldigt_materiale_for_varen():
    assert catalog.apply_material_overlay(
        db_module.get_armor("leather"), "armor", ["adamantine"]) == {}
    assert catalog.apply_material_overlay(
        db_module.get_weapon("quarterstaff"), "weapons", ["adamantine"]) == {}


def test_kun_eet_materiale_ad_gangen():
    """Et emne er lavet af ÉT materiale — vælges flere, vinder det første."""
    ov = catalog.apply_material_overlay(
        db_module.get_armor("heavy_steel_shield"), "armor", ["adamantine", "dragonhide"])
    assert ov["material"] == "adamantine"
    assert ov["name"].count("(") == 0        # ikke to materiale-mærkater i navnet
