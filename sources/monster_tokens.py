"""Monster billed-token-opslag: monster-id → billedfil på disk.

Tvilling til portraits.py, men KUN opslag (ingen upload/skrivning i v1 — Mikkel
scp'er slug-navngivne PNG'er ind i monster_tokens/ og chown'er til flask_dnd).
Stier/slug kommer fra paths.py; modulet importerer aldrig app.py (ingen cyklisk
import). Ruten (/dm/monster_token/<slug>) bliver i app.py og kalder herind.

Ansvarsgrænse: dette modul ejer AL disk-I/O og navn→fil-oversættelsen (inkl.
alias-map). dm_board injiceres med token_lookup som en ren callable, så
view-modellen forbliver I/O-fri.
"""
from pathlib import Path

from paths import MONSTER_TOKENS_DIR, MONSTER_TOKEN_EXTS, _safe_slug

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
