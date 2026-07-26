"""dm_parser — parser for eventyr-Markdown → Adventure (ren, UI-afkoblet).

Læser det forfatter-format der er defineret i `adventures/_TEMPLATE.md` og
`briefs/BRIEF-dm-adventure-format.md`. Ingen Flask, ingen DB, ingen I/O — kun
`parse_adventure(raw: str) -> Adventure`. Datakontrakten ligger fast; senere
releases fortykker felterne, ændrer dem ikke.

Format i korthed:
  #  = scene            ## Monstre = roster · ## Handling = spiltekst
  ## Rum: X = dungeon-rum · andre ## = under-overskrift + tekst
  >  = read-aloud-boks (valgfri **Fed caption:**)   ![alt](src) = billede
  @type[id] = entity (inline el. alene på en linje = embed)
  # Dokumenter = appendiks: ## Type: Titel → Definition (brev/kort/npc/…)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import ClassVar

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")

# ── Regexes ─────────────────────────────────────────────────────────────────
_ENTITY_RE = re.compile(r"@([A-Za-zÆØÅæøå]+)\[([^\]]+)\]")
# roster-punkt: "1x @monster[kriger]" (antal valgfrit → default 1)
_ROSTER_RE = re.compile(r"(?:(\d+)\s*x\s*)?@([A-Za-zÆØÅæøå]+)\[([^\]]+)\]")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_FIELD_RE = re.compile(r"^\*\s*\*\*(.+?):\*\*\s*(.*)$")      # * **Label:** indhold
_CAPTION_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")          # **Caption:** rest
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


# ── Datakontrakt ────────────────────────────────────────────────────────────
@dataclass
class Entity:
    type: str
    id: str
    raw: str


@dataclass
class RosterEntry:
    count: int
    type: str
    id: str


@dataclass
class Embed:
    entity: Entity
    kind: ClassVar[str] = "embed"


@dataclass
class Roster:
    entries: list[RosterEntry]
    label: str = ""
    kind: ClassVar[str] = "roster"


@dataclass
class ReadAloud:
    text: str
    caption: str = ""
    entities: list[Entity] = field(default_factory=list)
    kind: ClassVar[str] = "readaloud"


@dataclass
class Prose:
    text: str
    label: str = ""
    entities: list[Entity] = field(default_factory=list)
    kind: ClassVar[str] = "prose"


@dataclass
class Image:
    src: str
    alt: str = ""
    kind: ClassVar[str] = "image"


@dataclass
class Subheading:
    text: str
    kind: ClassVar[str] = "subheading"


@dataclass
class Room:
    id: str
    title: str
    blocks: list = field(default_factory=list)
    kind: ClassVar[str] = "room"


@dataclass
class Scene:
    id: str
    title: str
    blocks: list = field(default_factory=list)


@dataclass
class Definition:
    type: str
    id: str
    title: str
    blocks: list = field(default_factory=list)


@dataclass
class Adventure:
    title: str = ""
    meta: dict = field(default_factory=dict)
    party: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    documents: dict = field(default_factory=dict)   # (type, id) -> Definition
    statblocks: dict = field(default_factory=dict)  # id -> stat-dict (## Statblok:)

    def resolve(self, entity: Entity) -> Definition | None:
        """Slå en dokument-lokal entity op (brev/kort/…). None hvis ekstern
        (monster/npc uden appendiks-def) eller ukendt."""
        return self.documents.get((entity.type, entity.id))

    def statblock(self, ident: str) -> dict | None:
        """Adventure-lokalt statblok slået op på id (uafhængigt af ref-typen, så
        @npc[mordekain] rammer '## Statblok: Mordekain'). None hvis ukendt."""
        return self.statblocks.get(ident)


# ── Hjælpere ────────────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    text = text.strip().lower().translate(str.maketrans(
        {"æ": "ae", "ø": "oe", "å": "aa"}))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _entities(text: str) -> list[Entity]:
    return [Entity(m.group(1).lower(), m.group(2), m.group(0))
            for m in _ENTITY_RE.finditer(text)]


def _roster_entries(text: str) -> list[RosterEntry]:
    return [RosterEntry(int(m.group(1) or 1), m.group(2).lower(), m.group(3))
            for m in _ROSTER_RE.finditer(text)]


def _group_by(lines: list[str], marker: str):
    """Del linjer i (overskrift|None, krops-linjer) ved hver linje der starter
    med marker (fx '# ' eller '## '). Tekst før første overskrift → (None, …)."""
    groups, head, body = [], None, []
    for ln in lines:
        if ln.startswith(marker):
            groups.append((head, body))
            head, body = ln[len(marker):].strip(), []
        else:
            body.append(ln)
    groups.append((head, body))
    return [(h, b) for h, b in groups if h is not None or any(x.strip() for x in b)]


# ── Blok-parsing (read-aloud / prosa / billede / embed) ─────────────────────
def _parse_blocks(lines: list[str]) -> list:
    blocks, i, n = [], 0, len(lines)
    while i < n:
        raw = lines[i]
        line = raw.strip()
        if not line or line == "---":
            i += 1
            continue
        if line.startswith(">"):                                   # read-aloud-boks
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            text = "\n".join(buf).strip()
            caption = ""
            m = _CAPTION_RE.match(text)
            if m:
                caption, text = m.group(1).strip(), m.group(2).strip()
            blocks.append(ReadAloud(text=text, caption=caption,
                                    entities=_entities(text)))
            continue
        m = _IMAGE_RE.match(line)
        if m:                                                      # ![alt](src)
            blocks.append(Image(src=m.group(2).strip(), alt=m.group(1).strip()))
            i += 1
            continue
        if _ENTITY_RE.fullmatch(line):                             # @type[id] alene
            e = _entities(line)[0]
            blocks.append(Embed(entity=e))
            i += 1
            continue
        buf = []                                                   # prosa-afsnit
        while i < n and lines[i].strip() and not lines[i].strip().startswith((">", "#")) \
                and not _IMAGE_RE.match(lines[i].strip()) \
                and not _ENTITY_RE.fullmatch(lines[i].strip()) \
                and lines[i].strip() != "---":
            buf.append(lines[i].strip())
            i += 1
        text = " ".join(buf).strip()
        if text:
            blocks.append(Prose(text=text, entities=_entities(text)))
    return blocks


def _parse_room(title: str, body: list[str]) -> Room:
    """Rum = kompakte '* **Felt:** indhold'-punkter (Monstre/Fælder → roster,
    Kort → embed, resten → labeled prosa)."""
    blocks = []
    for ln in body:
        m = _FIELD_RE.match(ln.strip())
        if not m:
            continue
        label, content = m.group(1).strip(), m.group(2).strip()
        low = label.lower()
        if low in ("monstre", "fælder", "faelder"):
            blocks.append(Roster(entries=_roster_entries(content), label=label))
        elif low == "kort":
            ents = _entities(content)
            if ents:
                blocks.append(Embed(entity=ents[0]))
        else:
            blocks.append(Prose(text=content, label=label,
                                entities=_entities(content)))
    return Room(id=slugify(title), title=title, blocks=blocks)


def _parse_scene(title: str, body: list[str]) -> Scene:
    scene = Scene(id=slugify(title), title=title)
    for head, sub in _group_by(body, "## "):
        if head is None:                                # præ-tekst (fx @kort-embed)
            scene.blocks.extend(_parse_blocks(sub))
        elif head == "Monstre":
            bullets = " ".join(l.strip().lstrip("*").strip()
                               for l in sub if l.strip().startswith("*"))
            scene.blocks.append(Roster(entries=_roster_entries(bullets)))
        elif head.startswith("Rum:"):
            scene.blocks.append(_parse_room(head[4:].strip(), sub))
        elif head == "Handling":
            scene.blocks.extend(_parse_blocks(sub))
        else:                                           # navngivet sektion (Baggrund…)
            scene.blocks.append(Subheading(text=head))
            scene.blocks.extend(_parse_blocks(sub))
    return scene


def _fenced_or_all(lines: list[str]) -> list[str]:
    """Linjerne inde i den første ```-indhegnede blok, ellers alle linjerne."""
    fences = [i for i, l in enumerate(lines) if l.strip().startswith("```")]
    if len(fences) >= 2:
        return lines[fences[0] + 1:fences[1]]
    return lines


def _parse_statblock(lines: list[str]) -> dict:
    """'## Statblok:'-sektion → stat-dict (samme skema som data/monsters.yaml).
    YAML foretrækkes i en ```-blok, men rå YAML virker også. attacks/skills/feats
    accepteres både som native YAML-lister OG JSON-strenge (copy-paste fra
    monsters.yaml), så forfatteren har én genkendelig form."""
    data = _yaml.load("\n".join(_fenced_or_all(lines))) or {}
    for key in ("attacks", "skills", "feats"):
        if isinstance(data.get(key), str):
            data[key] = json.loads(data[key])
    return data


def _parse_appendix(body: list[str]) -> tuple[dict, dict]:
    """# Dokumenter → ({(type, id): Definition}, {id: stat-dict}). Hver '## Type:
    Titel' bliver en definition (brev/kort/npc/gaade/…); '## Statblok: Navn'
    bliver derimod et adventure-lokalt monster-statblok."""
    docs, statblocks = {}, {}
    for head, sub in _group_by(body, "## "):
        if head is None or ":" not in head:
            continue
        typ, title = head.split(":", 1)
        typ, title = typ.strip().lower(), title.strip()
        if typ in ("statblok", "statblock"):
            stats = _parse_statblock(sub)
            sid = slugify(title)
            stats.setdefault("id", sid)
            stats.setdefault("name", title)
            statblocks[sid] = stats
            continue
        d = Definition(type=typ, id=slugify(title), title=title,
                       blocks=_parse_blocks(sub))
        docs[(typ, d.id)] = d
    return docs, statblocks


# ── Indgang ─────────────────────────────────────────────────────────────────
def parse_adventure(raw: str) -> Adventure:
    raw = _COMMENT_RE.sub("", raw)
    lines = raw.split("\n")

    # Frontmatter: '---' … ('---' | '...')
    meta: dict = {}
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                meta = _yaml.load("\n".join(lines[1:j])) or {}
                lines = lines[j + 1:]
                break

    adv = Adventure(
        title=str(meta.get("title", "")).strip(),
        party=list(meta.get("party") or []),
        meta={k: v for k, v in meta.items() if k not in ("title", "party")},
    )

    for head, body in _group_by(lines, "# "):
        if head is None:
            continue
        if head.strip().lower() == "dokumenter":
            adv.documents, adv.statblocks = _parse_appendix(body)
        else:
            adv.scenes.append(_parse_scene(head, body))
    return adv
