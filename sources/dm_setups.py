"""dm_setups — startopstillinger (grid + token-placeringer) pr. kort.

Forfattet brugerdata: én fil pr. kort i eventyrmappen
(adventures/<adv>/setups/<kort-slug>.yaml). Gemmer KUN den rå opstilling
(grid-kalibrering + tokens med felt-koordinater) — live-positioner under kamp
hører til encounter (dm_session), ikke her.

Skema:
  grid:   {cell: <px>, x: <offset px>, y: <offset px>}   # billedets naturlige px
  tokens: [{kind, ref?, label?, col, row, hidden?, note?}]
    kind = pc | monster | npc | trap | door | treasure | note
"""
from __future__ import annotations

import io
import os
import tempfile

from ruamel.yaml import YAML

import dm_session as ds
from paths import _safe_slug

_yaml = YAML()


def _setup_path(adv_ref: str, map_slug: str):
    return ds.adventure_dir(adv_ref) / "setups" / f"{_safe_slug(map_slug)}.yaml"


def load_setup(adv_ref: str, map_slug: str) -> dict:
    """Opstillingen for ét kort. Manglende fil → tom opstilling (intet grid endnu)."""
    path = _setup_path(adv_ref, map_slug)
    if not path.exists():
        return {"grid": {}, "tokens": []}
    data = _yaml.load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("grid", {})
    data.setdefault("tokens", [])
    return data


def save_setup(adv_ref: str, map_slug: str, setup: dict) -> None:
    """Skriv opstillingen atomisk. Kun grid + tokens gemmes."""
    path = _setup_path(adv_ref, map_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    _yaml.dump({"grid": dict(setup.get("grid") or {}),
                "tokens": list(setup.get("tokens") or [])}, buf)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(buf.getvalue())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
