# 0003: Databasen er genereret, ikke redigeret

**Status:** gældende · **Besluttet:** 19. juni 2026 (`726286a`)

## Problem

`srd35.db` er en SQLite-fil med 19 tabeller SRD-referencedata — spells,
monstre, feats, våben, items. Den blev oprindeligt committet til repoet sammen
med koden.

Det gav to problemer. En binær fil i git giver **støjende diffs**: hver reseed
producerede en helt ny blob, uden at man kunne se hvad der var ændret. Og den
committede kopi blev **aldrig brugt i produktion** — install og upgrade kørte
alligevel `importer.py` og byggede databasen på serveren.

Der var altså to kandidater til "kilden til sandheden", og kun den ene blev
brugt.

## Beslutning

**`data/*.yaml` er kilden til sandheden. `srd35.db` er en build-artefakt.**

Databasen blev fjernet fra git-tracking og tilføjet til `.gitignore`. Den bygges
af `importer.py` ud fra `data/schema.sql` + `data/<tabel>.yaml`, både lokalt og
på serveren.

Seedingen er **idempotent**: `schema.sql` begynder med `DROP TABLE IF EXISTS`,
så databasen bygges fra nul hver gang. Det er trygt netop fordi den kun
indeholder genereret referencedata — brugerdata ligger et helt andet sted, i
`/srv/apps/flask_dnd-data/`.

## Forkastet

**At versionere `srd35.db`.** Man ville kunne klone og køre uden et seed-trin,
men prisen var to kilder til sandheden om det samme indhold. Så snart en
YAML-fil og den committede database er uenige, findes der ikke længere et
entydigt svar på hvad en spell koster i slots. At have to kilder er værre end at
have et ekstra byggetrin.

**At redigere databasen direkte** — med `sqlite3` eller et GUI. Det er
fristende, når man skal rette ét felt, men enhver ændring bliver slettet ved
næste reseed, uden varsel. Rettelsen skal ske i YAML'en.

## Konsekvens

- **En frisk klon har ingen database.** Den skal seedes før appen — og før
  pytest — virker. Uden seed fejler ~296 tests på manglende tabeller. Tabellen
  der nævnes i fejlen er vilkårlig; den afhænger af hvilken test der når først.
- **Ret aldrig i `srd35.db`.** Ret i `data/<tabel>.yaml` og kør
  `python importer.py` (lokalt: `./run-local.sh --fresh`; på serveren:
  `sudo /srv/apps/flask_dnd/deploy/update.sh --force-seed`).
- **En ny tabel kræver ingen ny indlæsningskode.** `importer.py` er generisk og
  læser kolonnerne ud af databasen selv: `CREATE TABLE` i `schema.sql`,
  `data/<tabel>.yaml` med rækkerne, og tabelnavnet i `TABLES`.
- **Efter en reseed er filen ikke byte-identisk** med før, fordi SQLite lægger
  siderne anderledes. Indholdet er det samme. Sammenlign tabel for tabel — ikke
  med `sha256`.
- Det gælder kun **vej 1**-filerne. 11 YAML-filer læses direkte i hukommelsen og
  kræver kun en genstart, ingen reseed — se
  [Dataflow](../arkitektur/dataflow.md#de-to-veje).

Se [Dataflow](../arkitektur/dataflow.md) for seedingen i detaljer og
[Datamodel](../arkitektur/datamodel.md) for de 19 tabeller.
