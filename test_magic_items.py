"""Tests for magic_items (Del B1: bårne wondrous items → modifiers via effekt-motoren).

Bruger den seedede srd35.db (get_magic_item). Verificerer at et BÅRET item bidrager
sine modifiers, at backpack ikke gør, at stacking følger typereglen, og at ability-
forstærkere kaskaderer.
"""
import shutil

import pytest

import db
import effects
import items as items_module
from models import Character, AbilityScores, InventoryItem


def _char(inv):
    return Character(name="T", race="Human", cls="Fighter", level=1,
                     hp_current=10, hp_max=10,
                     ability_scores=AbilityScores(14, 12, 13, 10, 8, 11),
                     inventory=inv)


def test_catalog_row_decodes_modifiers():
    mi = db.get_magic_item("cloak_of_resistance_1")
    assert mi["name"] == "Cloak of Resistance +1"
    assert mi["modifiers"] == [{"target": "save_all", "type": "resistance", "value": 1}]
    assert mi["price_cp"] == 100000


def test_worn_item_contributes_backpack_does_not():
    worn = [InventoryItem(ref="magic_items/cloak_of_resistance_1", state="worn")]
    back = [InventoryItem(ref="magic_items/cloak_of_resistance_1", state="backpack")]
    mods_w, src = effects.magic_item_modifiers(worn, db)
    mods_b, _ = effects.magic_item_modifiers(back, db)
    assert mods_w == [{"target": "save_all", "type": "resistance", "value": 1}]
    assert src[0]["name"] == "Cloak of Resistance +1"
    assert mods_b == []


def test_cloak_raises_all_saves():
    c = _char([InventoryItem(ref="magic_items/cloak_of_resistance_2", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    assert all(effects.save_effect_bonus(mods, s) == 2
               for s in ("fortitude", "reflex", "will"))


def test_ring_of_protection_is_deflection_ac():
    c = _char([InventoryItem(ref="magic_items/ring_of_protection_1", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    ac = [m for m in mods if m.get("target") == "ac"]
    assert ac == [{"target": "ac", "type": "deflection", "value": 1}]


def test_ability_booster_cascades():
    c = _char([InventoryItem(ref="magic_items/belt_of_giant_strength_4", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    eff = effects.effective_ability_scores(c.ability_scores, mods)
    assert eff.str == 18                    # 14 base + 4 enhancement


def test_same_type_does_not_stack():
    c = _char([InventoryItem(ref="magic_items/cloak_of_resistance_2", state="worn"),
               InventoryItem(ref="magic_items/cloak_of_resistance_1", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    assert effects.save_effect_bonus(mods, "will") == 2    # kun den højeste resistance


def test_inventory_resolves_name_and_weight_from_catalog():
    it = InventoryItem(ref="magic_items/cloak_of_resistance_2", state="worn")
    r = items_module.resolve_item(it, db)
    assert r["name"] == "Cloak of Resistance +2"
    assert r["source"] == "magic_items"


# ── Kan tilstanden 'worn' overhovedet NÅS? ───────────────────────────────────
# Testene ovenfor bygger state="worn" direkte i Python. Det beviser at motoren
# regner rigtigt, men ikke at nogen brugerhandling kan frembringe tilstanden —
# og i en periode kunne den ikke: både /api/inventory og inventar-UI'en tvang
# alt der ikke var rustning tilbage til "backpack", så ingen magisk genstand
# kunne bæres og ingen af dem virkede. Derfor går disse tests gennem RUTEN.

def _wearable(ref):
    it = InventoryItem(ref=ref)
    return items_module.is_wearable(it, items_module.resolve_item(it, db).get("record"))


def test_is_wearable_daekker_slot_og_slotloese_med_modifiers():
    assert _wearable("magic_items/periapt_of_wisdom_2")      # slot: neck
    assert _wearable("armor/chain_shirt")                    # rustning → AC
    assert not _wearable("magic_items/potion_of_cure_light_wounds")   # hverken slot/mods
    assert not _wearable("weapons/longsword")                # våben wieldes, bæres ikke
    assert not _wearable("items/tent")                       # grej hører i rygsækken


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as app_module
    shutil.copy("defaults/tjorn.yaml", tmp_path / "tjorn.yaml")
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    return app_module.app.test_client()


def _post(client, **kw):
    return client.post("/api/inventory", json={"char": "tjorn", **kw})


def test_ruten_tillader_at_baere_en_magisk_genstand(client, tmp_path):
    """Regression: Periapt of Wisdom kunne ikke sættes til 'worn' gennem ruten,
    så dens +2 Visdom var uopnåelig i praksis."""
    import character as char_module
    r = _post(client, action="add", ref="magic_items/periapt_of_wisdom_2", state="worn")
    assert r.status_code == 200

    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    it = next(i for i in char.inventory if i.ref == "magic_items/periapt_of_wisdom_2")
    assert it.state == "worn"                      # IKKE coercet til backpack

    # …og bonussen når faktisk frem til ability-scoren.
    mods, _ = effects.collect_character_effects(char, db)
    base = char.ability_scores.wis
    assert effects.effective_ability_scores(char.ability_scores, mods).wis == base + 2


def test_ruten_afviser_at_baere_en_potion(client, tmp_path):
    """Modstykket: en potion har hverken slot eller modifiers → hører i rygsækken."""
    import character as char_module
    _post(client, action="add", ref="magic_items/potion_of_cure_light_wounds", state="worn")
    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    it = next(i for i in char.inventory
              if i.ref == "magic_items/potion_of_cure_light_wounds")
    assert it.state == "backpack"


def test_update_bevarer_worn_paa_magisk_genstand(client, tmp_path):
    """Den anden halvdel af fejlen: update-vejen nulstillede worn ved hver
    inventar-redigering, så bonussen forsvandt ved et tilfældigt klik."""
    import character as char_module
    _post(client, action="add", ref="magic_items/periapt_of_wisdom_2", state="worn")
    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    idx = next(i for i, x in enumerate(char.inventory)
               if x.ref == "magic_items/periapt_of_wisdom_2")

    r = _post(client, action="update", index=idx, state="worn", qty=1, notes="")
    assert r.status_code == 200
    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    assert char.inventory[idx].state == "worn"


# ── Butikken: magiske genstande kan købes som hyldevarer ─────────────────────

def test_katalog_indeholder_magiske_genstande():
    """Wands, eliksirer, ringe og wondrous items står i udrustningsbutikken under
    fanen 'Magisk'. Navngivne specifics (Flame Tongue m.fl.) gør IKKE — de er
    unikke fund, ikke hyldevarer, og hører til DM'ens give-loot."""
    import catalog
    poster = catalog.build_catalog(db)["items"]
    mag = [p for p in poster if p["category"] == "magic_items"]
    assert len(mag) == len(db.get_all_magic_items())
    assert {p["group"] for p in mag} == {
        "Wands", "Eliksirer", "Ringe", "Vidunderlige genstande"}
    assert not [p for p in poster if p["ref"].startswith("specifik/")]

    wand = next(p for p in mag if p["ref"] == "magic_items/wand_of_cure_light_wounds")
    assert wand["cost_str"] == "750 gp" and wand["proficient"] is True
    assert "50 ladninger" in wand["detail"]["meta"]


def test_koebt_wand_faar_fulde_ladninger(client, tmp_path):
    """Køb via butikken skal give samme resultat som DM'ens give-loot (dm.py:340):
    fulde ladninger med det samme, ikke en tom tæller indtil første brug."""
    import character as char_module
    _post(client, action="add", ref="magic_items/wand_of_cure_light_wounds")
    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    wand = next(i for i in char.inventory
                if i.ref == "magic_items/wand_of_cure_light_wounds")
    assert wand.charges == 50


def test_detail_ruten_kender_magiske_genstande():
    """Klik på en købt wand i inventaret → detalje-modalen henter stats herfra.
    Uden magic_item i lookup'et fik man 400 og en tom infoboks."""
    import app as app_module
    c = app_module.app.test_client()
    d = c.get("/api/detail/magic_item/wand_of_fireball").get_json()
    assert d["caster_level"] == 5 and d["charges_max"] == 50
    assert d["spell_level"] == 3          # modalen regner save-DC 14 af den
    assert c.get("/api/detail/magic_item/findes_ikke").status_code == 404


def test_generering_faar_katalog_uden_magi():
    """Karaktergenereringen sender magic=0: startguldet rækker aldrig til en wand,
    og butikkens budget er kun vejledende, så listen ville mest være fristelser.
    Karakterarkets butik (default) har dem."""
    import app as app_module
    c = app_module.app.test_client()
    med = c.get("/api/catalog?str=10&size=medium").get_json()["items"]
    uden = c.get("/api/catalog?str=10&size=medium&magic=0").get_json()["items"]
    assert [i for i in med if i["category"] == "magic_items"]
    assert not [i for i in uden if i["category"] == "magic_items"]
    # Resten af butikken er uændret — kun den ene kategori forsvinder.
    assert ({i["ref"] for i in med} - {i["ref"] for i in uden}
            == {i["ref"] for i in med if i["category"] == "magic_items"})
