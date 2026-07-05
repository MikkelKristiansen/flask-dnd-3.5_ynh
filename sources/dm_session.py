"""dm_session — DM-kampagnesessioner.

Én session binder et EVENTYR sammen med et PARTY (PC-slugs) og den AKTIVE SCENE.
Gemmer — som karakter-YAML'erne — KUN mutabel tilstand: selve eventyret
genindlæses og parses fra `adventures/<ref>.md` ved behov (aldrig gemt i sessionen).

Ansvar: session-persistens + adgang til eventyr-filer. Ingen Flask, ingen HTML.
"""
from __future__ import annotations

import io
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

import dm_parser as P
from paths import ADVENTURES_DIR, SESSIONS_DIR, _safe_slug

_yaml = YAML()


@dataclass
class CampaignSession:
    slug: str
    adventure: str                                 # filnavn-stem i adventures/
    party: list[str] = field(default_factory=list)  # PC-slugs
    active_scene: str = ""                          # scene-id
    name: str = ""

    def to_dict(self) -> dict:
        """Kun mutabel tilstand — aldrig det parsede eventyr."""
        return {"name": self.name, "adventure": self.adventure,
                "party": list(self.party), "active_scene": self.active_scene}


# ── Eventyr-filer ────────────────────────────────────────────────────────────
def _adventure_path(ref: str) -> Path:
    # Case-bevarende sanitering (filnavne kan have store bogstaver, fx Midsommer-2)
    # + værn mod sti-traversal.
    return ADVENTURES_DIR / f"{re.sub(r'[^A-Za-z0-9_-]+', '', str(ref))}.md"


def list_adventures() -> list[str]:
    """Filnavn-stems for tilgængelige eventyr (skjuler _TEMPLATE o.l.)."""
    if not ADVENTURES_DIR.exists():
        return []
    return sorted(p.stem for p in ADVENTURES_DIR.glob("*.md")
                  if not p.name.startswith("_"))


def load_adventure(ref: str) -> P.Adventure:
    path = _adventure_path(ref)
    if not path.exists():
        raise FileNotFoundError(f"Eventyr ikke fundet: {ref}")
    return P.parse_adventure(path.read_text(encoding="utf-8"))


# ── Session-persistens ───────────────────────────────────────────────────────
def _session_path(slug: str) -> Path:
    return SESSIONS_DIR / f"{_safe_slug(slug)}.yaml"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def list_sessions() -> list[dict]:
    """Lette resuméer til oversigten: {slug, name, adventure}."""
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for p in sorted(SESSIONS_DIR.glob("*.yaml")):
        data = _yaml.load(p.read_text(encoding="utf-8")) or {}
        out.append({"slug": p.stem, "name": data.get("name") or p.stem,
                    "adventure": data.get("adventure", "")})
    return out


def load_session(slug: str) -> CampaignSession:
    path = _session_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Session ikke fundet: {slug}")
    data = _yaml.load(path.read_text(encoding="utf-8")) or {}
    return CampaignSession(
        slug=_safe_slug(slug),
        adventure=str(data.get("adventure", "")),
        party=list(data.get("party") or []),
        active_scene=str(data.get("active_scene", "")),
        name=str(data.get("name", "")),
    )


def save_session(session: CampaignSession) -> None:
    buf = io.BytesIO()
    _yaml.dump(session.to_dict(), buf)
    _atomic_write(_session_path(session.slug), buf.getvalue())


def _unique_slug(base: str) -> str:
    slug = _safe_slug(base) or "session"
    if not _session_path(slug).exists():
        return slug
    n = 2
    while _session_path(f"{slug}-{n}").exists():
        n += 1
    return f"{slug}-{n}"


def create_session(name: str, adventure: str,
                   party: list[str] | None = None) -> CampaignSession:
    """Ny session mod et eksisterende eventyr. active_scene defaulter til
    eventyrets første scene. Fejler hvis eventyret ikke findes."""
    adv = load_adventure(adventure)                    # validerer + giver scener
    session = CampaignSession(
        slug=_unique_slug(name or adventure),
        adventure=adventure,
        party=list(party or []),
        active_scene=adv.scenes[0].id if adv.scenes else "",
        name=name or adventure,
    )
    save_session(session)
    return session


def delete_session(slug: str) -> None:
    path = _session_path(slug)
    if path.exists():
        path.unlink()


def goto_scene(slug: str, scene_id: str) -> CampaignSession:
    """Sæt aktiv scene (valideret mod eventyrets scener) og gem."""
    session = load_session(slug)
    adv = load_adventure(session.adventure)
    if scene_id not in {s.id for s in adv.scenes}:
        raise ValueError(f"Ukendt scene '{scene_id}' i {session.adventure}")
    session.active_scene = scene_id
    save_session(session)
    return session
