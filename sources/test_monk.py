"""Tests for Monk-features: Flurry of Blows, Ki Strike, Fast Movement, Evasion,
unarmed skade-skalering og AC-bonus (refdata-helpers + app-integration).

Kør: python -m pytest test_monk.py   (fra sources/)
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import refdata
import rules as rules_module
import app as app_module

YAML_RW = YAML()
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


# ── Unarmed skade-skalering (refdata) ──────────────────────────────────────

@pytest.mark.parametrize("level,size,expected", [
    (1,  "medium", "1d6"),
    (3,  "medium", "1d6"),
    (4,  "medium", "1d8"),
    (7,  "medium", "1d8"),
    (8,  "medium", "1d10"),
    (11, "medium", "1d10"),
    (12, "medium", "2d6"),
    (15, "medium", "2d6"),
    (16, "medium", "2d8"),
    (19, "medium", "2d8"),
    (20, "medium", "2d10"),
    # Small-tabel
    (1,  "small",  "1d4"),
    (4,  "small",  "1d6"),
    (8,  "small",  "1d8"),
    (12, "small",  "1d10"),
    (16, "small",  "2d6"),
    (20, "small",  "2d8"),
])
def test_unarmed_damage(level, size, expected):
    assert refdata.monk_unarmed_damage(level, size) == expected


# ── Flurry-straf (refdata) ─────────────────────────────────────────────────

@pytest.mark.parametrize("level,expected", [
    (1, -2), (4, -2),    # 1-4: −2
    (5, -1), (8, -1),    # 5-8: −1
    (9,  0), (11,  0), (20, 0),   # 9+: 0
])
def test_flurry_penalty(level, expected):
    assert refdata.monk_flurry_penalty(level) == expected


# ── Greater Flurry (refdata) ───────────────────────────────────────────────

@pytest.mark.parametrize("level,expected", [
    (10, False), (11, True), (20, True),
])
def test_greater_flurry(level, expected):
    assert refdata.monk_greater_flurry(level) == expected


# ── Fast Movement (refdata) ───────────────────────────────────────────────

@pytest.mark.parametrize("level,expected", [
    (1,  0),   # ingen bonus under level 3
    (2,  0),
    (3,  10),
    (6,  20),
    (9,  30),
    (12, 40),
    (15, 50),
    (18, 60),
    (20, 60),  # cap 60
])
def test_fast_movement(level, expected):
    assert refdata.monk_fast_movement(level) == expected


# ── AC-bonus skalering (refdata) ──────────────────────────────────────────

@pytest.mark.parametrize("level,expected", [
    (1,  0),
    (4,  0),
    (5,  1),
    (9,  1),
    (10, 2),
    (15, 3),
    (20, 4),
])
def test_ac_bonus(level, expected):
    assert refdata.monk_ac_bonus(level) == expected


# ── Ki Strike (refdata) ───────────────────────────────────────────────────

@pytest.mark.parametrize("level,expected", [
    (1,  ""),
    (3,  ""),
    (4,  "magisk"),
    (9,  "magisk"),
    (10, "magisk, lovlig"),
    (15, "magisk, lovlig"),
    (16, "magisk, lovlig, adamant"),
    (20, "magisk, lovlig, adamant"),
])
def test_ki_strike(level, expected):
    assert refdata.monk_ki_strike(level) == expected


# ── Evasion / Improved Evasion (refdata) ──────────────────────────────────

@pytest.mark.parametrize("level,expected", [
    (1, ""),
    (2, "Evasion"),
    (8, "Evasion"),
    (9, "Improved Evasion"),
    (20, "Improved Evasion"),
])
def test_evasion(level, expected):
    assert refdata.monk_evasion(level) == expected


# ── monk_unarmed_attacks (rules) ──────────────────────────────────────────

def test_unarmed_attacks_no_flurry():
    """Uden flurry: kun ét primært angreb."""
    atks = rules_module.monk_unarmed_attacks(
        level=5, size="medium", flurry_penalty=-1,
        greater_flurry=False, flurry_active=False, base_damage="1d8"
    )
    assert len(atks) == 1
    assert atks[0].name == "Unarmed strike"
    assert atks[0].bonus == 0
    assert atks[0].base_damage == "1d8"
    assert atks[0].finesse is True
    assert atks[0].type == "bludgeoning"


def test_unarmed_attacks_with_flurry():
    """Med flurry: primær + 1 ekstra (level 5, straf −1)."""
    atks = rules_module.monk_unarmed_attacks(
        level=5, size="medium", flurry_penalty=-1,
        greater_flurry=False, flurry_active=True, base_damage="1d8"
    )
    assert len(atks) == 2
    assert atks[0].name == "Unarmed strike"
    assert atks[0].bonus == 0        # primær: fuld bonus (Mulighed A)
    assert atks[1].name == "Unarmed strike (flurry)"
    assert atks[1].bonus == -1       # ekstra: straffen


def test_unarmed_attacks_greater_flurry():
    """Greater Flurry (level 11+): primær + 2 ekstra angreb."""
    atks = rules_module.monk_unarmed_attacks(
        level=11, size="medium", flurry_penalty=0,
        greater_flurry=True, flurry_active=True, base_damage="1d10"
    )
    assert len(atks) == 3
    assert atks[0].name == "Unarmed strike"
    assert atks[1].name == "Unarmed strike (flurry)"
    assert atks[2].name == "Unarmed strike (flurry 2)"


# ── App-integration (HTTP-test) ───────────────────────────────────────────

def _write(dst_dir, slug, mutate):
    data = YAML_RW.load((DEFAULTS / "aelred.yaml").read_text())
    mutate(data)
    with (dst_dir / f"{slug}.yaml").open("w") as f:
        YAML_RW.dump(data, f)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Monk (lvl 6, med rustning → flurry inaktiv) + en ikke-monk (cleric) i tmp.

    Vi bevarer aelreds inventory (rustning + skjold) for at undgå ruamel.yaml
    round-trip-problemer med CommentedSeq-kommentarer. Flurry er dermed inaktiv,
    men monk-panel, unarmed strike, Ki Strike og Evasion vises stadig.
    """
    def monk(d):
        d["class"] = "Monk"
        d["level"] = 6
        d["combat"]["bab"] = 4
        # inventory bevares (aelreds rustning/skjold) → flurry inaktiv
    _write(tmp_path, "monk", monk)
    _write(tmp_path, "cleric", lambda d: None)
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_monk_panel_shows(client):
    """Monk-sektionen vises for en monk-karakter."""
    h = client.get("/karakter/monk").get_data(as_text=True)
    assert "Flurry of Blows" in h


def test_monk_panel_not_for_cleric(client):
    """Monk-sektionen vises IKKE for en ikke-monk."""
    h = client.get("/karakter/cleric").get_data(as_text=True)
    assert "Flurry of Blows" not in h


def test_monk_unarmed_attack_shown(client):
    """Unarmed strike vises i angrebssektionen for monken (uanset rustning)."""
    h = client.get("/karakter/monk").get_data(as_text=True)
    assert "Unarmed strike" in h


def test_monk_flurry_inactive_with_armor(client):
    """Flurry vises som inaktiv når monken bærer rustning."""
    h = client.get("/karakter/monk").get_data(as_text=True)
    assert "inaktiv" in h


def test_monk_ki_strike_at_level6(client):
    """Ki Strike er magisk ved level 6 → vises i monk-sektionen."""
    h = client.get("/karakter/monk").get_data(as_text=True)
    assert "magisk" in h and "Ki Strike" in h


def test_monk_evasion_at_level6(client):
    """Evasion (ikke Improved) vises ved level 6."""
    h = client.get("/karakter/monk").get_data(as_text=True)
    assert "Evasion" in h
