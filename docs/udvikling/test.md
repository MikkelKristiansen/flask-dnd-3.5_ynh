# Test

To testsuiter: pytest for Python, en afhængighedsfri smoke-test for JavaScript.
Begge køres fra **repo-roden**.

---

## Læs denne først: en frisk klon fejler

!!! danger "296 failed er ikke din fejl"

    **Symptom:** du har lige klonet repoet, kører pytest, og får en mur af
    fejl:

    ```
    296 failed, 406 passed in 35.45s
    FAILED test_wild_shape.py::… - sqlite3.OperationalError: no such table: animals
    ```

    **Årsag:** `srd35.db` er gitignoreret. Den *bygges* af `importer.py` ud fra
    `data/` + `schema.sql` og findes ikke i en frisk klon. Testene fejler ikke
    på logik, men på et tomt fundament.

    **Fix:**

    ```bash
    .venv/bin/python importer.py
    ```

    **Fejlmeddelelsen peger ikke selv på årsagen.** Den nævner en tilfældig
    tabel — hvilken afhænger af hvilken test der når først — og ligner derfor
    et problem med netop den tabel.

Tallene er værd at kende, fordi de er nemme at genkende:

| Tilstand | Resultat |
|---|---|
| Uden `srd35.db` | **296 failed, 406 passed** |
| Med `srd35.db` | **702 passed** |

Begge målt 31. juli 2026 ved faktisk at parkere databasen og køre suiten.

!!! note "Kunne fjernes helt"
    En pytest-fixture kunne seede databasen automatisk og gøre fælden
    umulig. Det er en kodeændring, ikke dokumentation — noteret, ikke gjort.

---

## pytest

```bash
.venv/bin/python -m pytest -q
```

**Baseline: 702 passed på ~31 sekunder** (39 testfiler, målt 31. juli 2026).

!!! warning "Brug venv'ens interpreter eksplicit"
    System-`python3` har ikke pakkerne. `pytest` alene i PATH kan ramme en
    anden interpreter end den appen kører på. Skriv `.venv/bin/python -m
    pytest` — det er den eneste form der altid rammer rigtigt.

Kør efter ændringer i `data/` eller `schema.sql`:

```bash
.venv/bin/python importer.py && .venv/bin/python -m pytest -q
```

Nyttige former:

```bash
.venv/bin/python -m pytest test_bestiary.py          # én fil
.venv/bin/python -m pytest -k "wild_shape"           # navnefilter
.venv/bin/python -m pytest -q -x                     # stop ved første fejl
```

---

## JS-smoke-test

```bash
node test_js_smoke.js
```

```
JS smoke OK — 9 filer loadet uden fejl, 15 nøglefunktioner defineret.
```

Verificeret 31. juli 2026 på Node v20. **Kør den fra repo-roden.**

!!! warning "Ældre briefs siger `cd sources && node test_js_smoke.js`"
    `sources/` findes ikke længere — repoet er fladt siden ynh-laget blev
    fjernet 26. juli 2026. Kommandoen er `node test_js_smoke.js` fra roden.

### Hvad den fanger — og hvorfor den findes

JS'en er browser-globale klassiske scripts uden build-trin eller moduler.
Testen konkatenerer `static/character-*.js` i **load-orden fra
`character.html`** og kører dem én gang i en Node-`vm` med samme delte globale
scope som browserens `<script>`-tags.

Det fanger tre ting `node --check` **ikke** kan se, fordi de kun opstår når
filerne deler scope:

- **redeklaration** — `const x` defineret i to filer
- **forkert load-orden** — en fil bruger noget der defineres senere
- **globals der er udefinerede ved load**

En mock-`DND` leverer serverdata; ukendte felter bliver `[]`, som virker både
som tom array og som objekt.

Til ren syntakstjek af én fil:

```bash
node --check static/character-combat.js
```

Ingen npm involveret — kun Nodes indbyggede `fs` og `vm`. Testen er dev-only
og shippes ikke.

---

## Hvad testene ikke dækker

**Kamp-kontekst kan ikke ses headless.** Der er ingen browser i suiten, så alt
der afhænger af en aktiv encounter i UI'et skal testes gennem Flask-klienten
med en encounter faktisk startet.

Mønstret findes i `test_dm_routes.py` — se fixturerne `enc_client` og `_start`
(omkring linje 613). Skriver du en ny test der kræver en igangværende kamp, så
genbrug dem frem for at bygge tilstanden op i hånden.

En fuld adfærdstest af JS'en med jsdom er noteret som en mulig fremtid, ikke
bygget.
