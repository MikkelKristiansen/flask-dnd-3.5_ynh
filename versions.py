"""Versionering og sikker skrivning af karakterfiler.

Ét klart ansvar: **beskyt live-data på disken**. To lag gør det, og de hører
sammen — derfor bor de i samme modul:

  1. Atomar skrivning — der skrives til en temp-fil i samme mappe og byttes ind
     med ``os.replace()``. Den eksisterende fil er urørt indtil byttet lykkes,
     så en afbrudt eller fejlet skrivning kan aldrig efterlade en halvskrevet
     eller tom karakterfil.
  2. Roterende snapshots — efter hvert gem kopieres tilstanden til
     ``$data_dir/backups/<navn>/<tidsstempel>.yaml``; de seneste
     ``SNAPSHOT_KEEP`` beholdes. Giver historik og mulighed for at rulle tilbage.

Et snapshot kan **navngives** ("efter session 12", "Level 7"). Navnet lever i
filnavnet efter en dobbelt underscore::

    20260801-084500-123456.yaml            ← unavngivet, roteres væk med tiden
    20260801-084500-123456__Session-12.yaml ← navngivet, roteres ALDRIG væk

Tidsstemplet står først, så kronologisk sortering er uændret. Filnavnet er
eneste sandhed — ingen sidecar-fil at holde i sync, og navnene er synlige
direkte i ``backups/``-mappen over SSH.

Modulet kender kun bytes og stier — ikke YAML og ikke Character-dataklassen.
``persistence.py`` bygger oven på det og re-eksporterer navnene, så
``character.py``-façaden og alle ``char_module.*``-kald i app-laget virker
uændret.
"""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

# Antal UNAVNGIVNE versioner der beholdes pr. karakter i backups/<navn>/.
# Navngivne versioner tæller ikke med og roteres aldrig væk.
SNAPSHOT_KEEP = 50

# Skiller tidsstempel fra navn i snapshot-filnavne.
LABEL_SEP = "__"

# Maks. længde på et navn — filnavne har en grænse (255 bytes på ext4), og
# tidsstempel + separator + ".yaml" fylder også.
LABEL_MAXLEN = 60

# Tegn der ikke må stå i et filnavn: kontroltegn og stiseparatorer/Windows-reserverede.
_LABEL_UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def atomic_write_bytes(p: Path, content: bytes) -> None:
    """Skriv bytes til p atomart: temp-fil i samme mappe → os.replace()."""
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def snapshot_dir(char_path: Path) -> Path:
    """backups-mappen for en given karakterfil.

    $data_dir/characters/tjorn.yaml → $data_dir/backups/tjorn/
    (søstermappe til characters/, så den følger med i YunoHost-backup af data_dir).
    """
    return char_path.parent.parent / "backups" / char_path.stem


def list_snapshots(char_path: Path) -> list[Path]:
    """Snapshots for en karakter, ældste først (tidsstempel-navne sorterer kronologisk)."""
    return sorted(snapshot_dir(Path(char_path)).glob("*.yaml"))


# ── Navngivne versioner ────────────────────────────────────────────────────

def sanitize_label(name: str) -> str:
    """Gør et brugerskrevet navn sikkert som del af et filnavn.

    Mellemrum bliver til bindestreger, så navnet er ét ord på kommandolinjen.
    Æøå og andre bogstaver bevares (filsystemet er UTF-8); kun kontroltegn og
    stiseparatorer fjernes. Returnerer "" for et navn der intet indhold har —
    kaldere behandler det som "ingen mærkat".
    """
    s = unicodedata.normalize("NFC", str(name or ""))
    # Whitespace kollapses FØR kontroltegn fjernes, så et linjeskift bliver til
    # en bindestreg i stedet for at klistre to ord sammen.
    s = re.sub(r"\s+", "-", s.strip())
    s = _LABEL_UNSAFE.sub("", s)
    # Ingen ledende/afsluttende prik eller bindestreg: en ledende prik ville
    # skjule filen, og en afsluttende prik forvirrer suffiks-parsing.
    return s.strip(".-")[:LABEL_MAXLEN].strip(".-")


def split_snapshot_name(path: Path | str) -> tuple[str, str]:
    """Snapshot-filnavn → (tidsstempel-del, navn). Navnet er "" hvis unavngivet.

    "20260801-084500-123456__Session-12.yaml" → ("20260801-084500-123456", "Session-12")
    """
    stem = Path(path).stem
    ts, sep, label = stem.partition(LABEL_SEP)
    return (ts, label) if sep else (stem, "")


def snapshot_label(path: Path | str) -> str:
    """Navnet på et snapshot, eller "" hvis det er unavngivet."""
    return split_snapshot_name(path)[1]


def save_named_snapshot(char_path: str | Path, name: str) -> Path:
    """Gem den nuværende tilstand som en navngivet version og returnér stien.

    Til forskel fra ``write_snapshot`` springes dedupe over: brugeren beder
    eksplicit om at mærke DENNE tilstand, og det skal virke også når intet er
    ændret siden sidste gem. Fejl bobler op (i modsætning til det best-effort
    automatiske snapshot), for her venter brugeren på et svar.
    """
    p = Path(char_path)
    label = sanitize_label(name)
    if not label:
        raise ValueError("Versionen skal have et navn.")
    if not p.exists():
        raise FileNotFoundError(f"Karakterfilen findes ikke: {p}")
    snap_dir = snapshot_dir(p)
    snap_dir.mkdir(parents=True, exist_ok=True)
    dest = snap_dir / f"{_timestamp()}{LABEL_SEP}{label}.yaml"
    dest.write_bytes(p.read_bytes())
    return dest


def rename_snapshot(char_path: str | Path, snapshot_name: str, new_name: str) -> str:
    """Omdøb (eller afmærk) et eksisterende snapshot. Returnerer det nye filnavn.

    Tidsstemplet bevares, så versionen bliver stående samme sted i historikken —
    kun navnet efter ``__`` ændres. Et tomt navn fjerner mærkatet, og versionen
    indgår derefter i rotationen igen.
    """
    p = Path(char_path)
    snap = snapshot_dir(p) / snapshot_name
    if not snap.is_file():
        raise FileNotFoundError(f"Snapshot findes ikke: {snap}")
    ts, _ = split_snapshot_name(snap)
    label = sanitize_label(new_name)
    dest = snap.parent / (f"{ts}{LABEL_SEP}{label}.yaml" if label else f"{ts}.yaml")
    if dest != snap:
        os.replace(snap, dest)
    return dest.name


def _timestamp() -> str:
    """Mikrosekunder i navnet → ingen kollision og korrekt kronologisk sortering."""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def write_snapshot(char_path: Path) -> None:
    """Kopiér den netop-gemte tilstand til et tidsstemplet snapshot og roter.

    Best-effort: en fejl her må ALDRIG forplante sig — et gem skal altid lykkes,
    også selvom backup-mappen er utilgængelig.
    """
    try:
        if not char_path.exists():
            return
        snap_dir = snapshot_dir(char_path)
        snap_dir.mkdir(parents=True, exist_ok=True)
        current = char_path.read_bytes()
        existing = sorted(snap_dir.glob("*.yaml"))
        # Spring over hvis intet er ændret siden nyeste snapshot (undgå spam ved
        # idempotente gem, fx "ny dag" hvor intet var brugt).
        if existing and existing[-1].read_bytes() == current:
            return
        (snap_dir / f"{_timestamp()}.yaml").write_bytes(current)
        # Roter: behold de seneste SNAPSHOT_KEEP UNAVNGIVNE. Navngivne versioner
        # er mærket med vilje ("efter session 12") og skal overleve for evigt,
        # så de holdes helt uden for rotationen.
        unnamed = [s for s in sorted(snap_dir.glob("*.yaml")) if not snapshot_label(s)]
        for old in unnamed[:-SNAPSHOT_KEEP]:
            old.unlink()
    except Exception:
        pass


def restore_snapshot(char_path: str, snapshot_name: str) -> None:
    """Gendan en karakterfil fra et navngivet snapshot (atomart).

    snapshot_name er filnavnet i backups/<navn>/, fx "20260619-204500-123456.yaml".
    Tager selv et snapshot af nuværende tilstand først, så gendannelsen kan fortrydes.
    """
    p = Path(char_path)
    snap = snapshot_dir(p) / snapshot_name
    if not snap.is_file():
        raise FileNotFoundError(f"Snapshot findes ikke: {snap}")
    write_snapshot(p)  # bevar nuværende tilstand inden overskrivning
    atomic_write_bytes(p, snap.read_bytes())
