"""Fil-stier og slug-sanitering — delt af app.py og portraits.py.

Ét sted for hvor karakterfiler og portrætter ligger, så de forskellige moduler
ikke dublerer env-var-læsningen eller sti-konventionen (og så portraits.py kan
importere herfra uden at skabe en cyklus med app.py).
"""
import os
import re
from pathlib import Path

CHARACTERS_DIR = Path(os.environ.get("DND_CHARACTERS_DIR",
                                     str(Path(__file__).parent / "characters")))
# Portrætter lægges manuelt i data-mappen (ved siden af characters/), ikke i
# sources/static/ som overskrives ved upgrade. Konvention: portraits/<slug>.<ext>.
PORTRAITS_DIR = CHARACTERS_DIR.parent / "portraits"
PORTRAIT_EXTS = ("jpg", "jpeg", "png", "webp")


def _safe_slug(text: str) -> str:
    """Saniter til et filsikkert slug: kun a-z, 0-9, bindestreg og underscore."""
    return re.sub(r"[^a-z0-9_-]+", "-", str(text).strip().lower()).strip("-")
