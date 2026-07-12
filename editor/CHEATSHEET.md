# Emacs-integration til D&D 3.5-eventyr — cheatsheet

To Emacs-værktøjer til at skrive eventyr i det format `dm_parser.py` læser:

| Fil | Ansvar |
|---|---|
| `dnd-adventure-mode.el` | **Skrivestøtte** i `adventure.md`: completion, eldoc, lint, hop, snippets |
| `dnd-browse.el` | **Opslag**: read-only browser over hele `srd35.db` |

Alt kører lokalt mod `sources/srd35.db` med Emacs' **indbyggede SQLite (Emacs 29+)**.
Ingen build, ingen kørende Flask, aldrig skrivning til db'en.

---

## Installation (i din init)

```elisp
(add-to-list 'load-path "/sti/til/flask-dnd-3.5/editor")
(require 'dnd-adventure-mode)
(add-to-list 'auto-mode-alist
             '("/adventures/.*/adventure\\.md\\'" . dnd-adventure-mode))
```

`dnd-browse` autoloades af mode-filen — ingen ekstra `require`.
Db'en findes automatisk (op fra filen til mappen med `sources/`); ellers sæt
`dnd-adventure-db-path` manuelt.

---

## Tastatur (i `dnd-adventure-mode`)

| Tast | Kommando | Gør |
|---|---|---|
| `C-c C-d m` | `dnd-insert-monster` | Vælg monster ved **navn** → indsæt `@monster[id]` |
| `C-c C-d b` | `dnd-browse` | Åbn db-browseren (se nedenfor) |
| `C-c C-d .` | `dnd-goto-definition` | Hop til definitionen af `@type[id]` ved punktet |
| `C-c C-d r` | `dnd-refresh-data` | Glem cachet SRD-data (kør efter `python importer.py`) |
| `TAB` / `M-TAB` | *(completion-at-point)* | Fuldfør `@type[…]` — se nedenfor |

---

## Entity-referencer `@type[id]`

| Reference | Resolver mod | Completion-kilde | Lint |
|---|---|---|---|
| `@monster[id]` | `srd35.db` (monstre + dyr) | db | ✔ ukendt id markeres |
| `@npc[id]` | `## Statblok: …` i bufferen | bufferens overskrifter | ✔ manglende def markeres |
| `@kort[id]` | `## Kort: …` i bufferen | bufferens overskrifter | ✔ |
| `@brev[id]` | `## Brev: …` i bufferen | bufferens overskrifter | ✔ |
| `@faelde[id]` | fælde-katalog (app) | tidligere brugte id'er i bufferen | — (lintes ikke) |

`id` slugificeres som appen: lowercase, `æ→ae ø→oe å→aa`, resten → `-`.

**Completion:** skriv fx `@monster[` og tryk `TAB` → alle id'er (med navn som
annotation). `@npc[`/`@kort[`/`@brev[` foreslår bufferens egne overskrifter.

**Eldoc** (auto, i minibufferen): punkt på `@monster[…]` → `navn · CR · HP · AC ·
angreb`; punkt på `@npc[…]` → titel + første linje af dens `## Statblok:`-blok.

**Flymake** markerer referencer der ikke resolver, mens du skriver (db utilgængelig
→ monster-lint droppes blødt, ingen falske fejl).

---

## Snippets (kræver `yasnippet`)

Skriv triggeren og tryk `TAB`. Spejler `adventures/_TEMPLATE.md`.

| Trigger | Indsætter |
|---|---|
| `scene` | `# titel` + `## Monstre` + `## Handling` (hel scene) |
| `rum` | `## Rum: <titel>` (dungeon-lokation) |
| `roster` | `## Monstre` (encounter-roster) |
| `statblok` | `## Statblok: <navn>` (eventyr-lokalt monster → `@npc[…]`) |
| `ra` | Read-aloud-boks (`> …`) |
| `brev` | `## Brev: <titel>` (handout → `@brev[…]`) |
| `kort` | `## Kort: <titel>` (handout → `@kort[…]`) |

---

## Db-browser — `M-x dnd-browse` (`C-c C-d b`)

Vælg en tabel → sorterbar liste over referencebanken. 10 tabeller:
**monstre, dyr, fælder, spells, feats, items, våben, skills, tilstande, domæner.**

| Tast | Gør |
|---|---|
| `RET` | Detalje-visning: **alle** felter for rækken (hele spell-teksten, statblok, feat-benefit …) |
| `i` | Indsæt `@monster[id]`/`@faelde[id]` i det adventure-buffer browseren blev åbnet fra |
| `s` | Sortér på kolonnen ved punktet |
| `/` | Filtrér på navn (regexp; tomt = ryd) |
| `g` | Genindlæs rækker |
| `n` / `p` | Næste / forrige række |
| `q` | Luk |

`i` virker kun på **referérbare** tabeller (monstre/fælder). På spells, feats osv.
gives en klar besked i stedet — de er ren læse-/opslagsdata.

---

## Fejlsøgning

| Symptom | Årsag / fix |
|---|---|
| "Denne Emacs har ikke indbygget SQLite" | Kræver Emacs 29+ bygget med SQLite |
| "srd35.db ikke fundet" | Kør `python importer.py` i `sources/`, eller sæt `dnd-adventure-db-path` |
| Completion tom / forkert efter data-ændring | `C-c C-d r` (glemmer cachen) |
| Ingen snippets | `yasnippet` er ikke indlæst — snippets er valgfrie |

---

*Data-kilde: `sources/srd35.db` (genereret af `importer.py` fra `data/*.yaml`).
Værktøjerne er altid read-only mod db'en.*
