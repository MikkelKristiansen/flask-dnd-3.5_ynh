"""Portræt-håndtering: validering, format-genkendelse og skrivning til disk.

Portrætter ligger i data-mappen (portraits/<slug>.<ext>), adskilt fra app-koden
så de overlever upgrade. Stier/slug kommer fra paths.py — modulet importerer
aldrig app.py, så ingen cyklisk import. Ruterne (/portrait, /api/portrait) bliver
i app.py og kalder herind.
"""
from pathlib import Path

from paths import PORTRAITS_DIR, PORTRAIT_EXTS, _safe_slug


def _portrait_path(slug: str) -> Path | None:
    """Find karakterens portrætfil i data-mappen, hvis en findes (slug.<ext>)."""
    safe = _safe_slug(slug)
    if not safe:
        return None
    for ext in PORTRAIT_EXTS:
        p = PORTRAITS_DIR / f"{safe}.{ext}"
        if p.exists():
            return p
    return None


def _sniff_image_ext(raw: bytes) -> str | None:
    """Genkend billedformat ud fra magic-bytes (imghdr er fjernet i Python 3.13+).

    Returnerer en endelse fra PORTRAIT_EXTS hvis indholdet er et understøttet
    billede, ellers None. Vi stoler på indholdet, ikke på filnavnets endelse.
    """
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return None


def _validate_portrait(file) -> bytes | None:
    """Læs + valider et uploadet portræt. Returnerer rå bytes, eller None hvis
    der ikke blev uploadet nogen fil. Rejser ValueError hvis filen ikke er et
    understøttet billede — så opretteren kan afvise FØR karakteren skrives.
    """
    if file is None or not file.filename:
        return None
    raw = file.read()
    if not raw:
        raise ValueError("Portrætfilen er tom.")
    if _sniff_image_ext(raw) is None:
        raise ValueError("Portrættet skal være et JPG-, PNG- eller WEBP-billede.")
    return raw


def _write_portrait(slug: str, raw: bytes) -> None:
    """Skriv et valideret portræt som portraits/<slug>.<ext>.

    Endelsen bestemmes af det faktiske billedindhold (magic-bytes), ikke af
    filnavnet. Et eksisterende portræt for samme slug (uanset endelse) ryddes
    først, så vi ikke ender med både .png og .jpg for samme karakter.
    """
    safe = _safe_slug(slug)
    ext = _sniff_image_ext(raw)
    if not safe or ext is None:
        raise ValueError("Ugyldigt portræt.")
    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    for old in PORTRAIT_EXTS:
        old_path = PORTRAITS_DIR / f"{safe}.{old}"
        if old_path.exists():
            old_path.unlink()
    (PORTRAITS_DIR / f"{safe}.{ext}").write_bytes(raw)
