"""Monster billed-token-opslag + -administration: monster-id → billedfil på disk.

Tvilling til portraits.py. Både OPSLAG (token_lookup, injiceres i dm_board) og
UPLOAD/SLET (v2 browser-UI: list_tokens/save_token/delete_token). Ved upload
oprettes mappen af app-brugeren → filerne ejes af flask_dnd (undgår den root-
ejerskabs-500'er portrætterne ramte). Modulet importerer aldrig app.py (ingen
cyklisk import); ruterne (/dm/monster_token/<slug> + /dm/monster-tokens-siden)
ligger i app.py/dm.py og kalder herind.

Ansvarsgrænse: dette modul ejer AL disk-I/O og navn→fil-oversættelsen (inkl.
alias-map). dm_board injiceres med token_lookup som en ren callable, så
view-modellen forbliver I/O-fri.
"""
from pathlib import Path

from paths import MONSTER_TOKENS_DIR, MONSTER_TOKEN_EXTS, _safe_slug
from portraits import _validate_portrait

# Alias-map: catalog-id (eller dets slug) → filnavn-slug, for de tilfælde hvor
# udklippets navn afviger fra monsterets id (danske id'er vs. engelske pawn-labels,
# OCR-varianter, forkortelser). Redigeres i data/monster_token_aliases.yaml UDEN
# kodeændring; kræver app-genstart for at slå igennem (som øvrige data/-filer).
_ALIAS_FILE = Path(__file__).parent / "data" / "monster_token_aliases.yaml"


def _load_aliases() -> dict[str, str]:
    """Læs alias-mappen. Blødt fallback til tom map hvis filen mangler/er tom, så
    featuren virker uden aliaser (den almindelige vej: id sluggger direkte)."""
    try:
        from ruamel.yaml import YAML
        with _ALIAS_FILE.open(encoding="utf-8") as f:
            raw = YAML(typ="safe").load(f) or {}
    except (FileNotFoundError, ImportError):
        return {}
    # Normalisér både nøgle og værdi til slug-form, så opslag er robust.
    return {_safe_slug(str(k)): _safe_slug(str(v)) for k, v in raw.items() if v}


_ALIASES = _load_aliases()


def token_slug(ref: str) -> str:
    """Oversæt et catalog-id/monster-ref til det billed-slug filen forventes at
    hedde: alias hvis et findes, ellers monsterets eget slug (samme _safe_slug som
    portrætter, så 'Demon, Babau' → 'demon-babau')."""
    safe = _safe_slug(ref)
    return _ALIASES.get(safe, safe)


def token_path(slug: str) -> Path | None:
    """Find token-billedfilen for et slug, hvis en findes (slug.png). Sikker sti:
    kun sanitérede slugs slås op inde i MONSTER_TOKENS_DIR — aldrig rå input, så
    '..'/absolutte stier kan ikke slippe ud af mappen."""
    safe = _safe_slug(slug)
    if not safe:
        return None
    for ext in MONSTER_TOKEN_EXTS:
        p = MONSTER_TOKENS_DIR / f"{safe}.{ext}"
        if p.exists():
            return p
    return None


def token_lookup(ref: str) -> str | None:
    """ref (monster-id) → billed-slug HVIS en token-fil findes på disk, ellers None.

    Dette er den callable dm_board injiceres med: den samler navn→slug-oversættelse
    (via alias-map) og disk-eksistens ét sted, så view-modellen kan spørge "har
    dette væsen et billede?" uden selv at røre disken. None → bræt falder tilbage
    til bogstav-token."""
    if not ref:
        return None
    slug = token_slug(ref)
    return slug if token_path(slug) else None


# ── Administration (v2 browser-UI) ───────────────────────────────────────────
def _slug_from_filename(name: str) -> str:
    """Filnavn → token-slug: stammen (uden endelse) gennem samme _safe_slug som
    opslaget, så 'Demon, Babau.png' → 'demon-babau' (matcher crop_pawns-navngivningen)."""
    stem = (name or "").replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return _safe_slug(stem)


def list_tokens() -> list[str]:
    """Slugs for de token-billeder der ligger i mappen (sorteret). Tom/manglende
    mappe → tom liste."""
    if not MONSTER_TOKENS_DIR.exists():
        return []
    exts = set(MONSTER_TOKEN_EXTS)
    return sorted(p.stem for p in MONSTER_TOKENS_DIR.iterdir()
                  if p.is_file() and p.suffix.lower().lstrip(".") in exts)


def save_token(file) -> str:
    """Validér + gem ét uploadet monster-token. Filnavnet bliver token-slug
    (<slug>.png). Kræver en (transparent) PNG. Returnerer slug; rejser ValueError
    ved fejl. Mappen oprettes af app-brugeren → filerne ejes af flask_dnd."""
    raw = _validate_portrait(file)                     # None hvis tom, ValueError hvis ikke-billede
    if raw is None:
        raise ValueError("Ingen fil valgt.")
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Token skal være en (transparent) PNG.")
    slug = _slug_from_filename(getattr(file, "filename", ""))
    if not slug:
        raise ValueError("Ugyldigt filnavn.")
    MONSTER_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    (MONSTER_TOKENS_DIR / f"{slug}.png").write_bytes(raw)
    return slug


def delete_token(slug: str) -> bool:
    """Slet et token-billede (sikker slug via token_path — ingen traversal).
    True hvis en fil blev slettet."""
    p = token_path(slug)
    if p and p.exists():
        p.unlink()
        return True
    return False
