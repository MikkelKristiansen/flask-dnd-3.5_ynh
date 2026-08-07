"""Tests for dyreledsagerens inventar: bæreevne, barding-AC og barding-priser.

To SRD-regler gælder KUN dyr og findes derfor ikke i items.py:
  - firbenede bærer ×1,5 (monsters-intro-a.md:85)
  - rustning til et nonhumanoid dyr følger en anden pris/vægt-kolonne end den
    humanoide (equipment.md:419)
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import app as app_module
import catalog
import character as char_module
import companion as companion_module
import companion_inventory
import db
from models import InventoryItem

YAML_SAFE = YAML(typ="safe")
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


@pytest.fixture
def varg_client(tmp_path, monkeypatch):
    """Tjørn (druide 3) med Varg (ulv). Returnerer (client, sti)."""
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    data = YAML_SAFE.load((DEFAULTS / "tjorn.yaml").read_text())
    with (tmp_path / "tjorn.yaml").open("w") as f:
        YAML_SAFE.dump(data, f)
    return app_module.app.test_client(), tmp_path


def _post(client, **body):
    return client.post("/api/companion_inventory",
                       json={"char": "tjorn", **body}).get_json()


def _varg(tmp_path):
    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    return companion_module.build_companion(char, db)


# ── Bæreevne ────────────────────────────────────────────────────────────────

def test_firbenet_baerer_halvanden_gang_saa_meget():
    """SRD: 'Quadrupeds can carry heavier loads than bipeds can.' Varg har Str 14
    som en gennemsnitlig kriger, men bærer 87 lb let last mod dennes 58."""
    biped = companion_inventory.carry_limits(14, "medium", "hawk")
    firbenet = companion_inventory.carry_limits(14, "medium", "wolf")
    assert biped["light"] == 58.0
    assert firbenet["light"] == 87.0
    assert firbenet["heavy"] == biped["heavy"] * 1.5


def test_tobenede_dyr_faar_ikke_bonussen():
    """En høg har to ben og bærer som en tobenet — undtagelseslisten i modulet."""
    assert not companion_inventory.is_quadruped("hawk")
    assert companion_inventory.is_quadruped("wolf")
    assert companion_inventory.is_quadruped("ukendt_dyr")   # default: firbenet


# ── Barding-priser og -vægt ─────────────────────────────────────────────────

def test_barding_koster_dobbelt_for_medium_dyr():
    """SRD's nonhumanoid-kolonne: Medium ×2 pris, ×1 vægt. En chain shirt til
    100 gp / 25 lb bliver 200 gp / 25 lb som barding til Varg."""
    kat = catalog.build_catalog(db, companion_size="medium",
                                companion_animal="wolf", str_score=14)
    cs = next(i for i in kat["items"] if i["name"] == "Chain Shirt Barding")
    assert cs["cost_cp"] == 20000 and cs["weight"] == 25.0
    assert db.get_armor("chain_shirt")["cost_cp"] == 10000    # uændret for mennesker


def test_barding_til_stort_dyr_koster_fire_gange():
    """Large nonhumanoid: ×4 pris, ×2 vægt."""
    kat = catalog.build_catalog(db, companion_size="large", companion_animal="bear_black")
    cs = next(i for i in kat["items"] if i["name"] == "Chain Shirt Barding")
    assert cs["cost_cp"] == 40000 and cs["weight"] == 50.0


def test_dyrebutik_har_hverken_vaaben_eller_skjolde():
    """Et dyr kæmper med tænder og kløer og kan ikke holde et skjold. En liste
    man ikke kan bruge er værre end ingen liste."""
    kat = catalog.build_catalog(db, companion_size="medium", companion_animal="wolf")
    assert not [i for i in kat["items"] if i["category"] == "weapons"]
    assert not [i for i in kat["items"] if i["group"] == "Shields"]
    assert [i for i in kat["items"] if i["group"] == "Barding"]


def test_dyrebutikkens_baeregraenser_er_dyrets():
    kat = catalog.build_catalog(db, companion_size="medium",
                                companion_animal="wolf", str_score=14)
    assert kat["enc_limits"]["light"] == 87.0


# ── Barding i AC'en ─────────────────────────────────────────────────────────

def test_barding_taeller_i_companion_ac(varg_client):
    """Vargs AC er 17 (10 + Dex 3 + naturlig 4). Chain shirt barding giver +4."""
    client, tmp_path = varg_client
    assert _varg(tmp_path)["ac"]["ac"] == 17
    r = _post(client, action="add", ref="armor/chain_shirt", state="worn")
    assert r["ac"]["ac"] == 21
    assert any(p["label"] == "rustning" and p["value"] == 4
               for p in r["ac"]["parts"])


def test_tung_barding_capper_dex_som_hos_en_karakter(varg_client):
    """Full plate har max Dex +1. Varg har Dex-bonus +3, så to af dem ryger —
    armor_class() i rules.py håndterer det allerede, den fik bare aldrig rustning."""
    client, tmp_path = varg_client
    r = _post(client, action="add", ref="armor/full_plate", state="worn")
    dex = next(p["value"] for p in r["ac"]["parts"] if p["label"] == "Dex")
    assert dex == 1
    assert r["ac"]["ac"] == 23          # 10 + 8 rustning + 1 Dex + 4 naturlig


def test_kun_en_barding_ad_gangen(varg_client):
    """Som _enforce_armor_slots for spillerkarakterer: ny barding på skubber den
    gamle i rygsækken, så der aldrig opstår en ulovlig tilstand med to."""
    client, tmp_path = varg_client
    _post(client, action="add", ref="armor/chain_shirt", state="worn")
    r = _post(client, action="add", ref="armor/full_plate", state="worn")
    worn = [row for row in r["rows"] if row["state"] == "worn"]
    assert len(worn) == 1 and worn[0]["name"] == "Full Plate"


# ── Vægt, advarsler og persistering ─────────────────────────────────────────

def test_barding_vejer_efter_dyrets_stoerrelse(varg_client):
    """Vægten skal IKKE gå gennem items.resolve_item, som bruger den humanoide
    tabel. For en Medium nonhumanoid er faktoren ×1, ikke ×½ eller ×2."""
    client, _ = varg_client
    r = _post(client, action="add", ref="armor/chain_shirt", state="worn")
    assert r["weight"] == 25.0
    assert r["enc"] == "Light"          # 25 af 87 lb


def test_advarsel_naar_barded_dyr_baerer_last(varg_client):
    """SRD equipment.md:613 — et dyr i barding må kun bære rytter og saddeltasker.
    Vi advarer frem for at spærre: hvor grænsen for 'saddeltasker' går er et
    bordvalg, ikke et regnestykke."""
    client, _ = varg_client
    r = _post(client, action="add", ref="armor/chain_shirt", state="worn")
    assert not r["warnings"]                    # kun barding = ingen last
    r = _post(client, action="add", ref="items/blanket_winter", state="backpack")
    assert any("saddeltasker" in w for w in r["warnings"])


def test_ingen_advarsel_uden_barding(varg_client):
    """Bærer Varg bare oppakning uden barding, er der ingenting at advare om."""
    client, _ = varg_client
    r = _post(client, action="add", ref="items/blanket_winter", state="backpack")
    assert not r["warnings"] and r["weight"] == 3.0


def test_overbelastning_advarer(varg_client):
    client, _ = varg_client
    for _ in range(10):
        _post(client, action="add", ref="items/chest_empty", state="backpack")
    r = _post(client, action="add", ref="items/chest_empty", state="backpack")
    assert r["weight"] == 275.0                 # 11 × 25 lb
    assert r["enc"] == "Overloaded"             # over 261 lb
    assert any("Belastning" in w for w in r["warnings"])


def test_ukendt_ref_afvises(varg_client):
    """Ellers bliver den til en navnløs 0-lb-række der ikke kan fjernes igen."""
    client, _ = varg_client
    assert _post(client, action="add", ref="items/findes_ikke")["error"]
    assert _post(client, action="add", ref="armor/findes_ikke")["error"]


def test_udstyret_overlever_genindlaesning(varg_client):
    """Inventaret gemmes i companion-dicten, samme tynde mønster som tricks."""
    client, tmp_path = varg_client
    _post(client, action="add", ref="armor/chain_shirt", state="worn")
    _post(client, action="add", ref="items/blanket_winter", state="backpack")
    char = char_module.load_character(str(tmp_path / "tjorn.yaml"))
    gemt = char.companion["inventory"]
    assert len(gemt) == 2
    assert gemt[0]["ref"] == "armor/chain_shirt" and gemt[0]["state"] == "worn"
    # og AC'en er stadig med barding efter en frisk indlæsning
    assert companion_module.build_companion(char, db)["ac"]["ac"] == 21


def test_fjern_barding_saenker_ac_igen(varg_client):
    client, _ = varg_client
    _post(client, action="add", ref="armor/chain_shirt", state="worn")
    r = _post(client, action="update", index=0, state="backpack")
    assert r["ac"]["ac"] == 17
    assert r["weight"] == 25.0          # den ligger der stadig, bare ikke på
    r = _post(client, action="remove", index=0)
    assert r["weight"] == 0.0 and not r["rows"]


# ── Overførsel mellem ejer og dyr ───────────────────────────────────────────

def _tjorn(tmp_path):
    return char_module.load_character(str(tmp_path / "tjorn.yaml"))


def _find(inv, brudstykke):
    return next(n for n, i in enumerate(inv) if brudstykke in (i.ref or ""))


def test_giv_til_varg_flytter_genstanden(varg_client):
    client, tmp_path = varg_client
    før = _tjorn(tmp_path).inventory
    idx = _find(før, "blanket_winter")
    r = _post(client, action="transfer", index=idx, to_companion=True)

    efter = _tjorn(tmp_path)
    assert len(efter.inventory) == len(før) - 1
    assert not [i for i in efter.inventory if "blanket_winter" in (i.ref or "")]
    assert r["weight"] == 3.0
    assert [row["name"] for row in r["rows"]] == ["Blanket, winter"]


def test_tag_tilbage_fra_varg(varg_client):
    client, tmp_path = varg_client
    idx = _find(_tjorn(tmp_path).inventory, "blanket_winter")
    _post(client, action="transfer", index=idx, to_companion=True)
    antal = len(_tjorn(tmp_path).inventory)

    r = _post(client, action="transfer", index=0, to_companion=False)
    assert r["weight"] == 0.0 and not r["rows"]
    assert len(_tjorn(tmp_path).inventory) == antal + 1


def test_overfoersel_bevarer_genstandens_egenskaber(varg_client):
    """Det er den SAMME ting der skifter hænder — ladninger, noter og magisk
    bonus må ikke gå tabt undervejs."""
    client, tmp_path = varg_client
    client.post("/api/inventory", json={
        "char": "tjorn", "action": "add",
        "ref": "magic_items/wand_of_cure_light_wounds", "notes": "Vargs nødhjælp"})
    idx = _find(_tjorn(tmp_path).inventory, "wand_of_cure_light_wounds")
    client.post("/api/inventory", json={"char": "tjorn", "action": "use", "index": idx})

    _post(client, action="transfer", index=idx, to_companion=True)
    hos_varg = _tjorn(tmp_path).companion["inventory"][0]
    assert hos_varg["ref"] == "magic_items/wand_of_cure_light_wounds"
    assert hos_varg["charges"] == 49            # den brugte ladning fulgte med
    assert hos_varg["notes"] == "Vargs nødhjælp"


def test_overfoersel_nulstiller_tilstanden(varg_client):
    """De to sider har ikke de samme tilstande: et dyr svinger ikke et våben, og
    'haversack' er ejerens taske. Alt lander i 'backpack' hos modtageren."""
    client, tmp_path = varg_client
    inv = _tjorn(tmp_path).inventory
    idx = _find(inv, "healer_s_kit")
    client.post("/api/inventory", json={"char": "tjorn", "action": "update",
                                        "index": idx, "state": "haversack"})
    r = _post(client, action="transfer", index=idx, to_companion=True)
    assert r["rows"][0]["state"] == "backpack"


def test_delvis_afgivelse_lader_giveren_beholde_resten(varg_client):
    """Tjørn har 4 rationer og giver Varg 2 — han beholder selv de 2 sidste."""
    client, tmp_path = varg_client
    idx = _find(_tjorn(tmp_path).inventory, "rations_trail_per_day")
    assert _tjorn(tmp_path).inventory[idx].qty == 4

    r = _post(client, action="transfer", index=idx, to_companion=True, qty=2)
    assert r["rows"][0]["qty"] == 2
    hos_tjorn = _tjorn(tmp_path).inventory[idx]
    assert hos_tjorn.ref.endswith("rations_trail_per_day") and hos_tjorn.qty == 2


def test_delvis_tilbagelevering(varg_client):
    client, tmp_path = varg_client
    idx = _find(_tjorn(tmp_path).inventory, "rations_trail_per_day")
    _post(client, action="transfer", index=idx, to_companion=True)      # alle 4

    r = _post(client, action="transfer", index=0, to_companion=False, qty=3)
    assert r["rows"][0]["qty"] == 1          # Varg beholder den sidste
    tilbage = [i for i in _tjorn(tmp_path).inventory
               if (i.ref or "").endswith("rations_trail_per_day")]
    assert [i.qty for i in tilbage] == [3]


def test_fortrudt_afgivelse_samler_stakken_igen(varg_client):
    """Giv 2 af 4 og fortryd: Tjørn skal have ÉN række med 4 igen — ikke to à 2."""
    client, tmp_path = varg_client
    idx = _find(_tjorn(tmp_path).inventory, "rations_trail_per_day")
    _post(client, action="transfer", index=idx, to_companion=True, qty=2)
    _post(client, action="transfer", index=0, to_companion=False)

    rationer = [i for i in _tjorn(tmp_path).inventory
                if (i.ref or "").endswith("rations_trail_per_day")]
    assert [i.qty for i in rationer] == [4]


def test_stakke_med_forskellige_noter_slaas_ikke_sammen(varg_client):
    """Sammenlægning må kun ske når ALT andet end antallet er ens."""
    client, tmp_path = varg_client
    idx = _find(_tjorn(tmp_path).inventory, "rations_trail_per_day")
    _post(client, action="transfer", index=idx, to_companion=True, qty=2)
    _post(client, action="update", index=0, notes="Vargs nødration")
    _post(client, action="transfer", index=_find(_tjorn(tmp_path).inventory,
                                                 "rations_trail_per_day"),
          to_companion=True, qty=1)

    r = _post(client, action="add", ref="items/torch")   # tvinger et frisk build
    stakke = sorted(row["qty"] for row in r["rows"]
                    if (row["ref"] or "").endswith("rations_trail_per_day"))
    assert stakke == [1, 2]


def test_forbrugsvare_med_ladninger_deles_aldrig(varg_client):
    """En wand med 42 ladninger må ikke blive til to rækker à 42."""
    client, tmp_path = varg_client
    client.post("/api/inventory", json={
        "char": "tjorn", "action": "add", "qty": 2,
        "ref": "magic_items/wand_of_cure_light_wounds"})
    idx = _find(_tjorn(tmp_path).inventory, "wand_of_cure_light_wounds")
    client.post("/api/inventory", json={"char": "tjorn", "action": "use", "index": idx})

    r = _post(client, action="transfer", index=idx, to_companion=True, qty=1)
    assert r["rows"][0]["qty"] == 2 and r["rows"][0]["splittable"] is False
    assert not any((i.ref or "").endswith("wand_of_cure_light_wounds")
                   for i in _tjorn(tmp_path).inventory)


def test_afgivelse_uden_antal_flytter_hele_stakken(varg_client):
    """Bagudkompatibilitet: gamle kald uden qty opfører sig som før."""
    client, tmp_path = varg_client
    idx = _find(_tjorn(tmp_path).inventory, "rations_trail_per_day")
    r = _post(client, action="transfer", index=idx, to_companion=True)
    assert r["rows"][0]["qty"] == 4
    assert not any((i.ref or "").endswith("rations_trail_per_day")
                   for i in _tjorn(tmp_path).inventory)


def test_overfoersel_af_ugyldigt_indeks_afvises(varg_client):
    client, _ = varg_client
    assert _post(client, action="transfer", index=999, to_companion=True)["error"]
    assert _post(client, action="transfer", index=0, to_companion=False)["error"]


def test_genstanden_ligger_praecis_et_sted(varg_client):
    """Begge inventarer skrives i ét save_character-kald. Var det to, kunne en
    fejl midtvejs efterlade genstanden begge steder — eller ingen af dem."""
    client, tmp_path = varg_client
    før = _tjorn(tmp_path)
    i_alt = len(før.inventory) + len((før.companion or {}).get("inventory") or [])
    _post(client, action="transfer", index=_find(før.inventory, "blanket_winter"),
          to_companion=True)
    efter = _tjorn(tmp_path)
    assert len(efter.inventory) + len(efter.companion["inventory"]) == i_alt
