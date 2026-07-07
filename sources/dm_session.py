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

import dm_encounter
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
    # Aktiv kamp (mutabel tilstand): {} = ingen. Ellers {round, turn_index,
    # turn_order:[ids], combatants:[dict]}. Combatants er et SNAPSHOT af kampen
    # i gang (navn/init/hp_max taget ved start; current_hp/conditions muterer) —
    # samme mønster som summons' per-instans-HP, ikke afledte tal der genberegnes.
    encounter: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Kun mutabel tilstand — aldrig det parsede eventyr."""
        return {"name": self.name, "adventure": self.adventure,
                "party": list(self.party), "active_scene": self.active_scene,
                "encounter": dict(self.encounter)}


# ── Eventyr-filer ────────────────────────────────────────────────────────────
# Hvert eventyr er en mappe: adventures/<ref>/adventure.md (+ media/-billeder).
ADVENTURE_FILE = "adventure.md"


def _safe_ref(ref: str) -> str:
    """Case-bevarende sanitering (mappenavne kan have store bogstaver, fx
    Midsommer) + værn mod sti-traversal — ét mappe-segment, ingen skråstreger."""
    return re.sub(r"[^A-Za-z0-9_-]+", "", str(ref))


def adventure_dir(ref: str) -> Path:
    return ADVENTURES_DIR / _safe_ref(ref)


def _adventure_path(ref: str) -> Path:
    return adventure_dir(ref) / ADVENTURE_FILE


def list_adventures() -> list[str]:
    """Mappenavne for tilgængelige eventyr (skjuler _TEMPLATE o.l.). Et eventyr
    tæller kun med hvis mappen har en adventure.md."""
    if not ADVENTURES_DIR.exists():
        return []
    return sorted(p.name for p in ADVENTURES_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith("_")
                  and (p / ADVENTURE_FILE).exists())


def load_adventure(ref: str) -> P.Adventure:
    path = _adventure_path(ref)
    if not path.exists():
        raise FileNotFoundError(f"Eventyr ikke fundet: {ref}")
    return P.parse_adventure(path.read_text(encoding="utf-8"))


def read_adventure_source(ref: str) -> str:
    """Rå Markdown-kilde for et eventyr (til browser-redigering)."""
    path = _adventure_path(ref)
    if not path.exists():
        raise FileNotFoundError(f"Eventyr ikke fundet: {ref}")
    return path.read_text(encoding="utf-8")


def write_adventure_source(ref: str, text: str) -> None:
    """Overskriv et eventyrs adventure.md (atomisk). Normaliserer CRLF→LF."""
    _atomic_write(_adventure_path(ref), text.replace("\r\n", "\n").encode("utf-8"))


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
        encounter=dict(data.get("encounter") or {}),
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


# ── Encounter-tilstand ───────────────────────────────────────────────────────
# Ren logik (initiativ/rækkefølge/tur) bor i dm_encounter; her bindes den til
# den persisterede session. Combatant-opslag i encounteren er pr. id.
def _find_combatant(session: CampaignSession, cid: str) -> dict | None:
    return next((c for c in session.encounter.get("combatants", [])
                 if c["id"] == cid), None)


def begin_encounter(slug: str, combatants: list[dict],
                    setup_tokens: list[dict] | None = None) -> CampaignSession:
    """Start en kamp fra allerede byggede+initiativ-rullede combatants (bygges i
    routen ud fra scenens roster + party). Sætter tur-rækkefølge, runde 1, tur 0.
    `setup_tokens` (kortets opstilling) → hver combatant får sin startposition
    fra den matchende token, så brættet viser hvor alle står ved kamp-start."""
    session = load_session(slug)
    if setup_tokens:
        dm_encounter.seed_positions(combatants, setup_tokens)
    session.encounter = {
        "round": 1,
        "turn_index": 0,
        "turn_order": dm_encounter.turn_order(combatants),
        "combatants": combatants,
        "active": True,
    }
    save_session(session)
    return session


def end_encounter(slug: str) -> CampaignSession:
    session = load_session(slug)
    session.encounter = {}
    save_session(session)
    return session


def next_turn(slug: str) -> CampaignSession:
    """Ryk turen frem (og runden når rækken er gennemløbet)."""
    session = load_session(slug)
    enc = session.encounter
    if enc.get("active"):
        enc["round"], enc["turn_index"] = dm_encounter.advance(
            int(enc.get("round", 1)), int(enc.get("turn_index", 0)),
            len(enc.get("turn_order", [])))
        save_session(session)
    return session


def set_initiative(slug: str, cid: str, value: int) -> CampaignSession:
    """Sæt en combatants initiativ (fx en PC's egen rulning) og genberegn tur-
    rækkefølgen. turn_index nulstilles ikke — kampen fortsætter hvor den er."""
    session = load_session(slug)
    c = _find_combatant(session, cid)
    if c is not None and session.encounter.get("active"):
        c["initiative"] = int(value)
        enc = session.encounter
        enc["turn_order"] = dm_encounter.turn_order(enc["combatants"])
        enc["turn_index"] = min(int(enc.get("turn_index", 0)),
                                max(0, len(enc["turn_order"]) - 1))
        save_session(session)
    return session


def set_combatant_hp(slug: str, cid: str, current_hp: int) -> CampaignSession:
    """Sæt en combatants aktuelle HP (kan gå negativt — DM afgør bevidstløs/død)."""
    session = load_session(slug)
    c = _find_combatant(session, cid)
    if c is not None:
        c["current_hp"] = int(current_hp)
        save_session(session)
    return session


def set_combatant_position(slug: str, cid: str, col: int, row: int) -> CampaignSession:
    """Flyt en combatant til en ny grid-celle (live-position under kamp). Muterer
    kun encounter-tilstanden — kortets forfattede opstilling røres ikke."""
    session = load_session(slug)
    c = _find_combatant(session, cid)
    if c is not None and session.encounter.get("active"):
        c["col"], c["row"] = int(col), int(row)
        save_session(session)
    return session


def toggle_condition(slug: str, cid: str, condition: str) -> CampaignSession:
    """Slå en condition til/fra på en combatant (fri streng — condition-id)."""
    session = load_session(slug)
    c = _find_combatant(session, cid)
    if c is not None:
        conds = c.setdefault("conditions", [])
        if condition in conds:
            conds.remove(condition)
        else:
            conds.append(condition)
        save_session(session)
    return session
