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

_KINDS = {"pc", "monster", "npc", "trap", "door", "treasure", "note"}


def _as_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def sanitize_tokens(raw) -> list:
    """Rens en rå token-liste (typisk fra browser-editoren) til det gemte skema.

    Ukendte `kind`-værdier og felter droppes, og col/row tvinges til heltal — så
    en manipuleret POST aldrig kan korrumpere opstillings-YAML'en. Tomme
    ref/label/note udelades helt (holder filen ren)."""
    out = []
    for t in raw or []:
        if not isinstance(t, dict) or t.get("kind") not in _KINDS:
            continue
        tok = {"kind": t["kind"], "col": _as_int(t.get("col")), "row": _as_int(t.get("row"))}
        for field in ("ref", "label", "note"):
            val = str(t.get(field) or "").strip()
            if val:
                tok[field] = val
        if t.get("hidden"):
            tok["hidden"] = True
        out.append(tok)
    return out


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


def all_tokens(adv_ref: str) -> list:
    """Alle tokens på tværs af eventyrets kort-opstillinger — til opsamling af fx
    trap-markører uden at kende de enkelte kort-slugs. Manglende setups-mappe →
    tom liste (eventyret har endnu ingen opstillinger)."""
    setups_dir = ds.adventure_dir(adv_ref) / "setups"
    if not setups_dir.exists():
        return []
    tokens = []
    for path in sorted(setups_dir.glob("*.yaml")):
        data = _yaml.load(path.read_text(encoding="utf-8")) or {}
        tokens.extend(data.get("tokens") or [])
    return tokens


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
