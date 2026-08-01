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

Modulet kender kun bytes og stier — ikke YAML og ikke Character-dataklassen.
``persistence.py`` bygger oven på det og re-eksporterer navnene, så
``character.py``-façaden og alle ``char_module.*``-kald i app-laget virker
uændret.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

# Antal versioner der beholdes pr. karakter i backups/<navn>/ (roteres ved gem)
SNAPSHOT_KEEP = 50


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
        # Mikrosekunder i navnet → ingen kollision og korrekt kronologisk sortering.
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (snap_dir / f"{ts}.yaml").write_bytes(current)
        # Roter: behold kun de seneste SNAPSHOT_KEEP.
        snaps = sorted(snap_dir.glob("*.yaml"))
        for old in snaps[:-SNAPSHOT_KEEP]:
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
