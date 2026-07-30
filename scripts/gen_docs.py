"""Generér de mekaniske referencesider i docs/ ud af koden selv.

Kør:  .venv/bin/python scripts/gen_docs.py

To sider bliver skrevet, og de må IKKE redigeres i hånden:
  docs/arkitektur/datamodel.md   ← data/schema.sql + rækketal fra data/*.yaml
  docs/arkitektur/ruter.md       ← app.url_map + view-funktionernes docstrings

Hvorfor generere frem for skrive: 19 tabeller og 81 ruter er lige præcis nok til
at en håndskreven liste er forældet inden for en måned. Alt der KAN udledes af
koden, bliver udledt; docs/arkitektur/*.md ved siden af er det håndskrevne, hvor
der står *hvorfor* — det kan koden ikke fortælle.

Scriptet bruger appens venv (ikke .venv-docs), fordi ruterne læses ud af den
rigtige Flask-app frem for med regex. En regex over @route-dekoratorer ville
misse blueprint-prefikser og fejle stille; url_map er sandheden.
"""
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DOCS = BASE / "docs" / "arkitektur"

BANNER = (
    "<!-- GENERERET AF scripts/gen_docs.py — REDIGÉR IKKE I HÅNDEN.\n"
    "     Ret kilden ({kilde}) og kør scriptet igen. -->\n\n"
)

# Tabel-konstraints, ikke kolonner — skal ikke med i kolonnetabellen.
_CONSTRAINT_ORD = {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}


# ── datamodel.md ────────────────────────────────────────────────────────────

def _parse_schema(sql: str) -> list[dict]:
    """Læs CREATE TABLE-blokke ud af data/schema.sql med kommentarer intakt.

    Kommentarerne er hele pointen: schema.sql forklarer i `--`-linjer hvad fx
    `self_duration` betyder. En PRAGMA table_info mod databasen ville give typer
    og nøgler, men tabe præcis den forklaring — derfor læses filen som tekst.
    """
    tables: list[dict] = []
    pending: list[str] = []   # kommentarlinjer siden sidste tomme linje
    current: dict | None = None
    set_statement = False     # har vi passeret filens header-kommentar?

    for raw in sql.splitlines():
        line = raw.strip()

        if current is None:
            if m := re.match(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)\s*\(", line):
                current = {"navn": m.group(1), "note": " ".join(pending),
                           "kolonner": []}
                pending = []
                set_statement = True
            elif line.startswith("--"):
                pending.append(line.lstrip("-").strip())
            elif not line:
                # Tom linje afslutter en kommentarblok. Nødvendigt fordi en
                # tabels note står lige over dens egen DROP, mens ældre
                # oprydnings-DROP'er kan have deres egen kommentar ovenover.
                pending = []
            else:
                # Filens indledende header-kommentar hører ikke til første
                # tabel — den beskriver hele schema.sql.
                if not set_statement:
                    pending = []
                set_statement = True
            continue

        if line.startswith(");"):
            tables.append(current)
            current = None
            pending = []
            continue

        if line.startswith("--"):
            pending.append(line.lstrip("-").strip())
            continue
        if not line:
            continue

        # Adskil en efterhængt kommentar fra selve kolonnedefinitionen.
        krop, _, hale = line.partition("--")
        note = " ".join(pending + ([hale.strip()] if hale.strip() else []))
        pending = []

        krop = krop.strip().rstrip(",").strip()
        if not krop:
            continue
        ord_ = krop.split()
        if ord_[0].upper() in _CONSTRAINT_ORD:
            continue
        current["kolonner"].append({
            "navn": ord_[0],
            "type": " ".join(ord_[1:]) or "—",
            "note": note,
        })

    if current is not None:
        sys.exit("FEJL: uafsluttet CREATE TABLE i data/schema.sql")
    return tables


def _raekketal() -> dict[str, int]:
    """Antal rækker pr. tabel, målt på data/*.yaml — kun SRD, uden privat overlay.

    Overlayet holdes bevidst ude: tallene her ender i den offentlige
    dokumentation, og de skal beskrive repoet, ikke Mikkels private indhold.
    """
    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    ud = {}
    for fil in sorted((BASE / "data").glob("*.yaml")):
        try:
            ud[fil.stem] = len(yaml.load(fil) or [])
        except Exception:
            ud[fil.stem] = 0
    return ud


def skriv_datamodel() -> Path:
    tabeller = _parse_schema((BASE / "data" / "schema.sql").read_text("utf-8"))
    tal = _raekketal()

    ud = [BANNER.format(kilde="`data/schema.sql`"),
          "# Datamodel\n",
          "`srd35.db` bygges fra bunden af `importer.py` ud af `data/schema.sql` "
          "og én `data/<tabel>.yaml` pr. tabel. Databasen er **genereret** og "
          "git-ignoreret — den er aldrig kilden til sandheden, filerne i `data/` er.\n",
          f"Skemaet har **{len(tabeller)} tabeller** med i alt "
          f"**{sum(tal.get(t['navn'], 0) for t in tabeller)} SRD-rækker**.\n",
          "!!! tip \"Tilføj en ny tabel\"\n"
          "    Tre trin, ingen ny indlæsningskode: `CREATE TABLE` i "
          "`data/schema.sql`, en `data/<tabel>.yaml` ved siden af, og tabelnavnet "
          "føjet til `TABLES` i `importer.py`.\n",
          "## Oversigt\n",
          "| Tabel | Rækker | Kolonner | Hvad den holder |",
          "|---|--:|--:|---|"]
    for t in tabeller:
        note = t["note"] or "—"
        ud.append(f"| [`{t['navn']}`](#{t['navn']}) | {tal.get(t['navn'], 0)} "
                  f"| {len(t['kolonner'])} | {note} |")

    for t in tabeller:
        ud.append(f"\n## {t['navn']}\n")
        if t["note"]:
            ud.append(f"{t['note']}\n")
        ud.append(f"Kilde: `data/{t['navn']}.yaml` "
                  f"({tal.get(t['navn'], 0)} rækker)\n")
        ud += ["| Kolonne | Type | Note |", "|---|---|---|"]
        for k in t["kolonner"]:
            ud.append(f"| `{k['navn']}` | `{k['type']}` | {k['note'] or ''} |")

    sti = DOCS / "datamodel.md"
    sti.write_text("\n".join(ud) + "\n", encoding="utf-8")
    return sti


# ── ruter.md ────────────────────────────────────────────────────────────────

def _resume(fn) -> str:
    """Første sætning af en view-funktions docstring, som ét-linjes resumé."""
    doc = (fn.__doc__ or "").strip()
    if not doc:
        return ""
    første = doc.split("\n\n")[0].replace("\n", " ")
    første = re.sub(r"\s+", " ", første).strip()
    # Klip ved punktum, men kun hvis der står noget efter (undgå at kappe
    # forkortelser midt over i korte docstrings).
    if "." in første and len(første.split(".")[0]) > 15:
        første = første.split(".")[0] + "."
    return første.replace("|", "\\|")


def skriv_ruter() -> Path:
    # Ingen database nødvendig for at bygge url_map — pegér den et sted der
    # ikke findes, så et import ikke kan komme til at røre den rigtige db.
    os.environ.setdefault("DND_DB_PATH", "/nonexistent/gen_docs.db")
    sys.path.insert(0, str(BASE))
    import app as app_modul

    flask_app = app_modul.app
    grupper: dict[str, list[dict]] = {}
    for regel in flask_app.url_map.iter_rules():
        if regel.endpoint == "static":
            continue
        bp = regel.endpoint.split(".")[0] if "." in regel.endpoint else "(app.py)"
        view = flask_app.view_functions[regel.endpoint]
        grupper.setdefault(bp, []).append({
            "rule": regel.rule,
            "metoder": ", ".join(sorted(regel.methods - {"HEAD", "OPTIONS"})),
            "modul": getattr(view, "__module__", "?"),
            "resume": _resume(view),
        })

    i_alt = sum(len(v) for v in grupper.values())
    ud = [BANNER.format(kilde="`app.py` + `routes_*.py` + `dm*.py`"),
          "# Ruter\n",
          f"**{i_alt} ruter** fordelt på **{len(grupper)} grupper**. "
          "Kernen (karakterark, portrætter, terningkast) ligger i `app.py`; "
          "resten er udspaltet i blueprints — ét domæne pr. fil.\n",
          "Ruter under `/api/` returnerer JSON og kaldes fra `static/*.js`. "
          "De øvrige renderer Jinja-templates.\n"]

    for bp in sorted(grupper, key=lambda b: (b == "(app.py)" and "0" or "1") + b):
        ruter = sorted(grupper[bp], key=lambda r: r["rule"])
        moduler = sorted({r["modul"] for r in ruter})
        titel = "app.py (kerne)" if bp == "(app.py)" else f"Blueprint `{bp}`"
        ud.append(f"\n## {titel}\n")
        ud.append("Fil(er): " + ", ".join(f"`{m}.py`" for m in moduler) + "\n")
        ud += ["| Rute | Metode | Hvad den gør |", "|---|---|---|"]
        for r in ruter:
            ud.append(f"| `{r['rule']}` | {r['metoder']} | {r['resume'] or '—'} |")

    sti = DOCS / "ruter.md"
    sti.write_text("\n".join(ud) + "\n", encoding="utf-8")

    # Gør huller synlige: en rute uden docstring bliver en tom celle i tabellen.
    # Det er ikke en fejl der skal stoppe byggeriet, men det er en opgaveliste.
    mangler = [r["rule"] for ruter in grupper.values() for r in ruter
               if not r["resume"]]
    if mangler:
        print(f"  bemærk: {len(mangler)} af {i_alt} ruter har ingen docstring "
              f"→ tom celle i tabellen")
        for rule in sorted(mangler)[:5]:
            print(f"    {rule}")
        if len(mangler) > 5:
            print(f"    … og {len(mangler) - 5} flere")
    return sti


if __name__ == "__main__":
    DOCS.mkdir(parents=True, exist_ok=True)
    for sti in (skriv_datamodel(), skriv_ruter()):
        print(f"skrev {sti.relative_to(BASE)}")
