"""dm_media — eventyrers billed-filer (kort/handouts) i data-mappen.

Ét ansvar: liste, gemme og slette billeder under `adventures/<eventyr>/media/`.
Genbruger portræt-uploadens validering (magic-bytes → kun jpg/png/webp), så et
uploadet kort valideres på samme måde som et portræt. Ingen Flask, ingen HTML —
routes i dm.py kalder herind.

Filnavnet bevares (saneret) så det matcher markdown-referencen `![](media/Fil.png)`
— derfor bruges IKKE portræt-modulets slug-navngivning, kun dets validering.
"""
from __future__ import annotations

import re

from paths import PORTRAIT_EXTS
from portraits import _validate_portrait

_UNSAFE = re.compile(r"[^A-Za-z0-9æøåÆØÅ._-]+")


def _safe_filename(name: str) -> str:
    """Ét filnavn-segment (ingen mapper, ingen '..'), med bevaret læsbart navn +
    billedendelse. Case bevares, så referencer som media/Heltenes-hus.png passer."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]      # kun basename
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = _UNSAFE.sub("-", stem).strip("-._") or "billede"
    ext = re.sub(r"[^A-Za-z0-9]+", "", ext).lower()
    if ext not in PORTRAIT_EXTS:
        ext = "png"                                                # normalisér ukendt endelse
    return f"{stem}.{ext}"


def list_media(adv_dir) -> list[str]:
    """Billedfilnavne i eventyrets media-mappe (sorteret)."""
    media = adv_dir / "media"
    if not media.exists():
        return []
    return sorted(p.name for p in media.iterdir()
                  if p.is_file() and p.suffix.lower().lstrip(".") in PORTRAIT_EXTS)


def save_media(adv_dir, file) -> str:
    """Validér + gem ét uploadet billede i eventyrets media-mappe. Returnerer det
    gemte filnavn. Rejser ValueError hvis der ikke er en gyldig billedfil."""
    raw = _validate_portrait(file)                    # None hvis tom, ValueError hvis ikke-billede
    if raw is None:
        raise ValueError("Ingen fil valgt.")
    media = adv_dir / "media"
    media.mkdir(parents=True, exist_ok=True)
    fname = _safe_filename(file.filename)
    (media / fname).write_bytes(raw)
    return fname


def delete_media(adv_dir, filename: str) -> bool:
    """Slet ét billede fra media-mappen. Filnavnet saneres til ét basename
    (ingen traversal muligt). True hvis en fil blev slettet."""
    target = adv_dir / "media" / _safe_filename(filename)
    if target.exists():
        target.unlink()
        return True
    return False
