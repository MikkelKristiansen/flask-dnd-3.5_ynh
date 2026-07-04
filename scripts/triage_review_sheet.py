#!/usr/bin/env python3
"""
Review-ark: træk KUN de 'lav'-konfidens spells ud af triagen og præsentér dem
kompakt med et beskrivelses-uddrag, så mennesket kan afgøre kategorien hurtigt.

Genbruger classify() fra triage_spells.py — indeholder ingen egen logik.
Output: briefs/spell-triage-review.md — kun det du skal øjne på.
"""
from pathlib import Path
import triage_spells as t

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "briefs" / "spell-triage-review.md"


def snippet(desc, n=180):
    s = t.clean(desc or "").replace("\n", " ").strip()
    return (s[:n] + "…") if len(s) > n else s


def main():
    data = t.load(t.SPELLS)
    rows = []
    for sp in data:
        cat, conf, ev = t.classify(sp)
        if conf == "lav":
            rows.append((cat, sp))
    rows.sort(key=lambda r: (r[0], r[1].get("name", "").lower()))

    lines = [
        "# Spell-triage — REVIEW-BUNKE (kun de usikre)\n",
        f"De **{len(rows)}** spells scriptet var usikkert på. Alt andet "
        "(høj-konfidens) behøver du ikke se på.\n",
        "**Sådan:** læs `gæt` + uddraget. Er gættet rigtigt → lad stå. Er det "
        "forkert → skriv rigtig bogstav i `→ ret`-kolonnen.\n",
        "Kategorier: A=passiv buff · B=spell-angreb · C=summon · D=buff-på-våben · "
        "E=offensiv/fjende · F=utility · G=healing\n",
    ]

    last = None
    for cat, sp in rows:
        if cat != last:
            lines.append(f"\n## Gættet **{cat}** — {t.CAT_NAMES[cat]}\n")
            lines.append("| gæt | → ret | navn | save | range | uddrag |")
            lines.append("|-----|-------|------|------|-------|--------|")
            last = cat
        name = sp.get("name", "")
        save = str(sp.get("save") or "None").replace("|", "/")[:22]
        rng = str(sp.get("range") or "—").replace("|", "/")[:22]
        snip = snippet(sp.get("description", "")).replace("|", "/")
        lines.append(f"| {cat} |  | {name} | {save} | {rng} | {snip} |")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"Skrev {OUT}  ({len(rows)} rækker til review)")


if __name__ == "__main__":
    main()
