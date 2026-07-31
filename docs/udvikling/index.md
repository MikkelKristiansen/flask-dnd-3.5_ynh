# Udvikling

Sådan kommer du i gang med at arbejde i appen.

## Start den lokalt

```bash
./run-local.sh            # http://localhost:5000, auto-reload
./run-local.sh --fresh    # nulstiller lokal test-tilstand + srd35.db
```

`run-local.sh` seeder `srd35.db` hvis den mangler, sætter datastierne til en
lokal test-mappe og peger `DND_PRIVATE_DATA_DIR` på `../dnd-private-data`.
Uden kodeord i miljøet slår `auth.py` sig selv fra og logger en advarsel — det
er den tilstand lokal udvikling kører i.

## De tre kommandoer du bruger hele tiden

```bash
.venv/bin/python importer.py            # data/*.yaml + schema.sql → srd35.db
.venv/bin/python -m pytest -q           # 702 passed på ~31 s
node test_js_smoke.js                   # JS-smoke, fra repo-roden
```

Efter en ændring i `data/` eller `schema.sql`: kør de to første i den
rækkefølge.

!!! warning "En frisk klon fejler med 296 tests før du seeder"
    `srd35.db` er gitignoreret. Se [Test](test.md) — det er den fælde der
    koster mest tid første gang.

## Hvor koden ligger

Al appkode er i **repo-roden** — fladt, ingen `src/` eller `sources/`.
[Arkitektur › Filkort](../arkitektur/index.md#filkort) viser hvilken fil der
gør hvad.

Skal du forstå *hvordan* noget hænger sammen frem for hvor det ligger:

| | |
|---|---|
| [Dataflow](../arkitektur/dataflow.md) | de to veje fra `data/`, seeding, hvor brugerdata bor |
| [Regelmotor](../arkitektur/regelmotor.md) | hvordan tallene på arket bliver til |
| [Datamodel](../arkitektur/datamodel.md) | tabellerne — **genereret** af `scripts/gen_docs.py` |
| [Ruter](../arkitektur/ruter.md) | alle endpoints — **genereret** |

## Videre herfra

| Side | Hvad den dækker |
|---|---|
| [Opskrifter](opskrifter.md) | tilføj monster, spell, fælde, magisk genstand, race, ny tabel |
| [Test](test.md) | begge suiter, baseline-tal, hvad der ikke er dækket |
| [Værktøj](vaerktoej.md) | `scripts/` og Emacs-integrationen |

Regler for arbejdet — hvad der aldrig må committes, hvornår der skal reseedes —
står i `CLAUDE.md` i repo-roden.
