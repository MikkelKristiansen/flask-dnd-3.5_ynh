#!/usr/bin/env python3
"""dm_preview — forfatter-værktøj til DM-eventyr (indtil browser-editing findes).

    python dm_preview.py <fil.md>            # læsbart træ af den parsede struktur
    python dm_preview.py <fil.md> --check    # valider @-referencer (exit 1 ved fejl)

Ren læse-/rapporteringshjælp oven på dm_parser. Ingen Flask, ingen DB.
"""
import argparse
import os
import sys

import dm_parser as P

DEFAULT = os.path.join(os.path.dirname(__file__), "adventures", "Midsommer-2.md")


# ── Reference-opsamling ──────────────────────────────────────────────────────
def iter_refs(adv):
    """Yield (Entity, sted-tekst) for HVER @type[id] i eventyret — roster,
    embed og inline i prosa/read-aloud (rekursivt ned i rum)."""
    def blocks(bs, where):
        for b in bs:
            if b.kind == "embed":
                yield b.entity, where
            elif b.kind == "roster":
                for e in b.entries:
                    yield P.Entity(e.type, e.id, f"@{e.type}[{e.id}]"), where
            elif b.kind in ("prose", "readaloud"):
                for e in b.entities:
                    yield e, where
            elif b.kind == "room":
                yield from blocks(b.blocks, f"{where} › {b.title}")

    for s in adv.scenes:
        yield from blocks(s.blocks, s.title)


def check(adv):
    """→ {dead, external, unused}. dead = doc-lokal type men ukendt id
    (stavefejl); external = type slet ikke i appendiks (fra DB i R2);
    unused = definition der aldrig refereres."""
    defined_types = {t for (t, _) in adv.documents}
    used = set()
    dead, external = [], []
    for ent, where in iter_refs(adv):
        key = (ent.type, ent.id)
        if key in adv.documents:
            used.add(key)
        elif ent.type in defined_types:
            dead.append((ent, where))
        else:
            external.append((ent, where))
    unused = [d for k, d in adv.documents.items() if k not in used]
    return {"dead": dead, "external": external, "unused": unused}


# ── Rapport (--check) ────────────────────────────────────────────────────────
def report(adv) -> int:
    r = check(adv)
    if r["dead"]:
        print("⚠  DØDE REFERENCER (type er defineret i appendiks, men id findes ikke):")
        for ent, where in r["dead"]:
            print(f"     {ent.raw}   i «{where}»  — stavefejl?")
    else:
        print("✅ Ingen døde dokument-referencer.")

    if r["unused"]:
        print("\nℹ  UBRUGTE DEFINITIONER (defineret i # Dokumenter, aldrig refereret):")
        for d in r["unused"]:
            print(f"     @{d.type}[{d.id}]  «{d.title}»")

    ext = sorted({(e.type, e.id) for e, _ in r["external"]})
    if ext:
        print("\nℹ  EKSTERNE REFERENCER (ikke i appendiks — forventes fra database i R2):")
        for typ, id_ in ext:
            print(f"     @{typ}[{id_}]")

    return 1 if r["dead"] else 0


# ── Træ-visning (standard) ───────────────────────────────────────────────────
def _clip(s, n=60):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _show(b, indent="  "):
    if b.kind == "embed":
        print(f"{indent}🗺  {b.entity.type}: {b.entity.id}")
    elif b.kind == "roster":
        print(f"{indent}⚔  {b.label or 'Monstre'}: "
              + ", ".join(f"{e.count}× {e.id}" for e in b.entries))
    elif b.kind == "readaloud":
        cap = f" [{b.caption}]" if b.caption else ""
        print(f"{indent}📢{cap} «{_clip(b.text)}»")
    elif b.kind == "prose":
        lbl = f"{b.label}: " if b.label else ""
        refs = "  →" + " ".join(e.raw for e in b.entities) if b.entities else ""
        print(f"{indent}📝 {lbl}{_clip(b.text)}{refs}")
    elif b.kind == "image":
        print(f"{indent}🖼  {b.src}")
    elif b.kind == "subheading":
        print(f"{indent}—— {b.text} ——")
    elif b.kind == "room":
        print(f"{indent}🚪 Rum: {b.title}")
        for rb in b.blocks:
            _show(rb, indent + "     ")


def tree(adv):
    print(f"\n📖 {adv.title}  — {adv.meta.get('subtitle', '')}")
    print(f"   Party: {', '.join(adv.party) or '(ingen)'}")
    print(f"   {len(adv.scenes)} scener · {len(adv.documents)} dokumenter\n")
    for s in adv.scenes:
        print(f"# {s.title}")
        for b in s.blocks:
            _show(b)
        print()
    if adv.documents:
        print("── # Dokumenter (opslagsbare) ──")
        for (typ, id_), d in sorted(adv.documents.items()):
            body = _clip(" ".join(getattr(b, "text", getattr(b, "src", ""))
                                  for b in d.blocks), 50)
            print(f"  @{typ}[{id_}]  «{body}»")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Preview/tjek et DM-eventyr.")
    ap.add_argument("fil", nargs="?", default=DEFAULT, help="sti til eventyr-.md")
    ap.add_argument("--check", action="store_true",
                    help="valider @-referencer i stedet for at vise træet")
    args = ap.parse_args(argv)

    with open(args.fil, encoding="utf-8") as f:
        adv = P.parse_adventure(f.read())

    if args.check:
        return report(adv)
    tree(adv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
