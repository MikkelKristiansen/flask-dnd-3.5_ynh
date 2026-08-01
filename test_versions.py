"""Tests for versions.py: navngivne snapshots og den skånsomme rotation.

Kør: python -m pytest test_versions.py   (fra repo-roden)

Arbejder mod tmp_path og rører hverken srd35.db eller rigtige karakterfiler.
Layoutet efterlignes: <root>/characters/<navn>.yaml + <root>/backups/<navn>/.
"""
import pytest

import versions


@pytest.fixture
def char(tmp_path):
    """En karakterfil i et minimalt data_dir-layout."""
    chars = tmp_path / "characters"
    chars.mkdir()
    p = chars / "tjorn.yaml"
    p.write_text("name: Tjorn\n", encoding="utf-8")
    return p


# ── Sanitering ─────────────────────────────────────────────────────────────

def test_sanitize_replaces_spaces_with_dashes():
    assert versions.sanitize_label("efter session 12") == "efter-session-12"


def test_sanitize_keeps_danish_letters():
    assert versions.sanitize_label("Tjørn på Åsen") == "Tjørn-på-Åsen"


def test_sanitize_strips_path_separators_and_control_chars():
    assert versions.sanitize_label("../../etc/passwd") == "etcpasswd"
    assert versions.sanitize_label("a\x00b\nc") == "ab-c"


def test_sanitize_strips_leading_dot_so_file_is_not_hidden():
    assert not versions.sanitize_label(".skjult").startswith(".")


def test_sanitize_truncates_long_names():
    assert len(versions.sanitize_label("x" * 200)) == versions.LABEL_MAXLEN


def test_sanitize_empty_input_is_empty():
    assert versions.sanitize_label("   ") == ""
    assert versions.sanitize_label("") == ""


# ── Parsing af filnavne ────────────────────────────────────────────────────

def test_split_named_snapshot():
    ts, label = versions.split_snapshot_name("20260801-084500-123456__Session-12.yaml")
    assert ts == "20260801-084500-123456"
    assert label == "Session-12"


def test_split_unnamed_snapshot_has_no_label():
    ts, label = versions.split_snapshot_name("20260801-084500-123456.yaml")
    assert ts == "20260801-084500-123456"
    assert label == ""


def test_snapshot_label_shorthand():
    assert versions.snapshot_label("20260801-084500-123456__Level-7.yaml") == "Level-7"
    assert versions.snapshot_label("20260801-084500-123456.yaml") == ""


# ── Gem navngiven version ──────────────────────────────────────────────────

def test_save_named_snapshot_writes_current_state(char):
    dest = versions.save_named_snapshot(char, "Session 12")
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "name: Tjorn\n"
    assert versions.snapshot_label(dest) == "Session-12"


def test_save_named_snapshot_skips_dedupe(char):
    """Et navngivet snapshot skal kunne tages selv om intet er ændret."""
    versions.write_snapshot(char)                    # automatisk snapshot først
    versions.save_named_snapshot(char, "Uændret")    # samme indhold — skal alligevel gemmes
    labels = [versions.snapshot_label(s) for s in versions.list_snapshots(char)]
    assert "Uændret" in labels
    assert len(labels) == 2


def test_save_named_snapshot_requires_a_name(char):
    with pytest.raises(ValueError):
        versions.save_named_snapshot(char, "   ")


# ── Omdøb / afmærk ─────────────────────────────────────────────────────────

def test_rename_labels_an_existing_snapshot(char):
    versions.write_snapshot(char)
    old = versions.list_snapshots(char)[0]
    new_name = versions.rename_snapshot(char, old.name, "Efter session 3")
    assert versions.snapshot_label(new_name) == "Efter-session-3"
    # Tidsstemplet bevares, så versionen bliver stående i historikken.
    assert versions.split_snapshot_name(new_name)[0] == versions.split_snapshot_name(old)[0]
    assert not old.exists()


def test_rename_with_empty_name_removes_the_label(char):
    named = versions.save_named_snapshot(char, "Fortryd mig")
    plain = versions.rename_snapshot(char, named.name, "")
    assert versions.snapshot_label(plain) == ""
    assert (versions.snapshot_dir(char) / plain).exists()


def test_rename_unknown_snapshot_raises(char):
    with pytest.raises(FileNotFoundError):
        versions.rename_snapshot(char, "findes-ikke.yaml", "Navn")


# ── Rotation ───────────────────────────────────────────────────────────────

def _fill(char, count, keep_named=()):
    """Læg `count` unavngivne snapshots + evt. navngivne direkte i backups-mappen."""
    d = versions.snapshot_dir(char)
    d.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (d / f"20260101-000000-{i:06d}.yaml").write_text(f"nr: {i}\n", encoding="utf-8")
    for i, name in enumerate(keep_named):
        (d / f"20260101-000000-9{i:05d}__{name}.yaml").write_text("x\n", encoding="utf-8")


def test_rotation_keeps_only_the_newest_unnamed(char):
    _fill(char, versions.SNAPSHOT_KEEP + 5)
    versions.write_snapshot(char)   # roterer efter skrivning
    unnamed = [s for s in versions.list_snapshots(char) if not versions.snapshot_label(s)]
    assert len(unnamed) == versions.SNAPSHOT_KEEP


def test_rotation_never_deletes_named_snapshots(char):
    _fill(char, versions.SNAPSHOT_KEEP + 20, keep_named=("Session-1", "Level-3"))
    versions.write_snapshot(char)
    labels = {versions.snapshot_label(s) for s in versions.list_snapshots(char)}
    assert {"Session-1", "Level-3"} <= labels


def test_named_snapshots_do_not_use_up_the_quota(char):
    """50 navngivne må ikke presse de unavngivne ud."""
    _fill(char, versions.SNAPSHOT_KEEP, keep_named=[f"v{i}" for i in range(10)])
    versions.write_snapshot(char)
    unnamed = [s for s in versions.list_snapshots(char) if not versions.snapshot_label(s)]
    assert len(unnamed) == versions.SNAPSHOT_KEEP


# ── Restore virker uændret for navngivne ───────────────────────────────────

def test_restore_from_named_snapshot(char):
    versions.save_named_snapshot(char, "Før uheldet")
    char.write_text("name: Ødelagt\n", encoding="utf-8")
    named = [s for s in versions.list_snapshots(char) if versions.snapshot_label(s)][0]
    versions.restore_snapshot(str(char), named.name)
    assert char.read_text(encoding="utf-8") == "name: Tjorn\n"


# ── Ruter (routes_versions.py) ─────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Testklient med CHARACTERS_DIR peget på en tmp-kopi af defaults/tjorn.yaml."""
    import shutil
    import app as app_module

    chars = tmp_path / "characters"
    chars.mkdir()
    shutil.copy("defaults/tjorn.yaml", chars / "tjorn.yaml")
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", chars)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def snap_dir(tmp_path):
    return tmp_path / "backups" / "tjorn"


def _names(snap_dir):
    return sorted(p.name for p in snap_dir.glob("*.yaml"))


def test_route_save_named_version(client, snap_dir):
    r = client.post("/api/version/save", json={"char": "tjorn", "name": "Session 12"})
    assert r.status_code == 200
    assert r.get_json()["name"] == "Session-12"
    assert _names(snap_dir) == [r.get_json()["file"]]


def test_route_save_rejects_empty_name(client, snap_dir):
    r = client.post("/api/version/save", json={"char": "tjorn", "name": "   "})
    assert r.status_code == 400
    assert not snap_dir.exists() or _names(snap_dir) == []


def test_route_save_unknown_character_is_404(client):
    r = client.post("/api/version/save", json={"char": "findes-ikke", "name": "x"})
    assert r.status_code == 404


def test_route_rename(client, snap_dir):
    f = client.post("/api/version/save",
                    json={"char": "tjorn", "name": "Gammel"}).get_json()["file"]
    r = client.post("/api/version/rename",
                    json={"char": "tjorn", "snapshot": f, "name": "Ny"})
    assert r.status_code == 200 and r.get_json()["name"] == "Ny"
    assert _names(snap_dir) == [r.get_json()["file"]]


def test_route_rename_with_empty_name_unlabels(client):
    f = client.post("/api/version/save",
                    json={"char": "tjorn", "name": "Væk med mig"}).get_json()["file"]
    r = client.post("/api/version/rename",
                    json={"char": "tjorn", "snapshot": f, "name": ""})
    assert r.get_json()["name"] == ""


@pytest.mark.parametrize("url", ["/api/version/rename", "/api/restore"])
def test_route_rejects_path_traversal(client, url, tmp_path):
    """Et snapshot-navn fra klienten må kun pege på DENNE karakters snapshots."""
    r = client.post(url, json={"char": "tjorn",
                               "snapshot": "../../characters/tjorn.yaml",
                               "name": "ondt"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "ukendt snapshot"


def test_route_restore_still_works(client, tmp_path):
    """Ruten flyttede fra app.py til blueprintet — den skal opføre sig uændret."""
    char = tmp_path / "characters" / "tjorn.yaml"
    original = char.read_bytes()
    f = client.post("/api/version/save",
                    json={"char": "tjorn", "name": "Før"}).get_json()["file"]
    char.write_bytes(b"name: Bortkommet\n")
    r = client.post("/api/restore", json={"char": "tjorn", "snapshot": f})
    assert r.status_code == 200
    assert char.read_bytes() == original
