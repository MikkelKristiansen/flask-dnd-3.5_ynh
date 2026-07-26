"""Tests for adgangskontrollen (auth.py): to delte kodeord, spiller og DM."""
import pytest
from werkzeug.security import generate_password_hash

import auth
import dm_session as ds
from app import app

SPILLER_KODE = "spiller-hemmelighed"
DM_KODE = "dm-hemmelighed"

# scrypt-hashing tager ~0,1 s pr. kald — én gang for hele modulet er rigeligt.
SPILLER_HASH = generate_password_hash(SPILLER_KODE)
DM_HASH = generate_password_hash(DM_KODE)


def _sæt_op(monkeypatch, tmp_path, spiller=True, dm=True):
    """Tænd adgangskontrollen og giv DM-området et tomt eventyr-bibliotek."""
    for navn, hash_, tændt in ((auth.PLAYER_HASH_ENV, SPILLER_HASH, spiller),
                               (auth.DM_HASH_ENV, DM_HASH, dm)):
        if tændt:
            monkeypatch.setenv(navn, hash_)
        else:
            monkeypatch.delenv(navn, raising=False)
    monkeypatch.setattr(ds, "ADVENTURES_DIR", tmp_path / "adventures")
    monkeypatch.setattr(ds, "SESSIONS_DIR", tmp_path / "sessions")
    # init_app() kørte ved import uden kodeord i miljøet, så nøglen mangler.
    app.secret_key = "test-nøgle"
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def client(monkeypatch, tmp_path):
    return _sæt_op(monkeypatch, tmp_path)


def _login(client, kode):
    return client.post("/login", data={"kodeord": kode})


def test_uden_kodeord_i_miljoeet_er_appen_aaben(monkeypatch, tmp_path):
    """Baseline: de øvrige ~680 tests kører uden at logge ind."""
    c = _sæt_op(monkeypatch, tmp_path, spiller=False, dm=False)
    assert c.get("/").status_code == 200


def test_login_siden_kan_naas_uden_at_vaere_logget_ind(client):
    assert client.get("/login").status_code == 200


def test_ulogget_bliver_sendt_til_login(client):
    r = client.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_ulogget_api_kald_giver_401_json_ikke_redirect(client):
    """JS'en skal have en forståelig fejl, ikke en login-side med status 200."""
    r = client.get("/api/catalog")
    assert r.status_code == 401
    assert r.is_json and "error" in r.get_json()


def test_forkert_kodeord_giver_ikke_adgang(client):
    assert _login(client, "gæt").status_code == 401
    assert client.get("/").status_code == 302


def test_spiller_kommer_ind_til_karakterarkene(client):
    _login(client, SPILLER_KODE)
    assert client.get("/").status_code == 200


def test_spiller_afvises_paa_dm_omraadet(client):
    _login(client, SPILLER_KODE)
    r = client.get("/dm/")
    assert r.status_code == 403
    # Login-siden igen, så man kan skrive DM-kodeordet uden først at logge ud.
    assert b"Kodeord" in r.data


def test_spiller_afvises_paa_dm_api(client):
    _login(client, SPILLER_KODE)
    r = client.get("/dm/api/entity-ids")
    assert r.status_code == 403 and r.is_json


def test_dm_kan_baade_dm_omraadet_og_karakterarkene(client):
    _login(client, DM_KODE)
    assert client.get("/dm/").status_code == 200
    assert client.get("/").status_code == 200


def test_logud_lukker_adgangen_igen(client):
    _login(client, SPILLER_KODE)
    client.get("/logout")
    assert client.get("/").status_code == 302


def test_login_sender_ikke_videre_til_fremmed_domaene(client):
    """next må kun være en intern sti — ellers er login en open redirect."""
    r = client.post("/login", data={"kodeord": SPILLER_KODE,
                                    "next": "//ondt-domæne.dk/"})
    assert "ondt-dom" not in r.headers["Location"]


def test_next_foerer_tilbage_til_den_oenskede_side(client):
    r = client.post("/login", data={"kodeord": SPILLER_KODE,
                                    "next": "/karakter/tjorn"})
    assert r.headers["Location"].endswith("/karakter/tjorn")


def test_oedelagt_hash_giver_afvisning_ikke_500(client, monkeypatch):
    """En $-mast hash må ikke vælte requesten — den skal bare aldrig matche."""
    monkeypatch.setenv(auth.PLAYER_HASH_ENV, "scrypt:32768:8:1")
    assert _login(client, SPILLER_KODE).status_code == 401


def test_kun_dm_hash_laaser_kun_dm_omraadet(monkeypatch, tmp_path):
    """Mellemform: spillerne slipper for kodeord, eventyret er stadig lukket."""
    c = _sæt_op(monkeypatch, tmp_path, spiller=False, dm=True)
    assert c.get("/").status_code == 200
    assert c.get("/dm/").status_code == 403
