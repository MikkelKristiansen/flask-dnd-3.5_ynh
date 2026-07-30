# Privat overlay

Repoet er offentligt og indeholder kun OGL-materiale. Mikkels egne monstre,
NPC'er, fælder og magiske genstande ligger i et **privat overlay uden for
repoet**, med samme filnavne som `data/`.

Denne side er **arbejdsgangen**. Mekanikken — hvordan `importer.py` lægger
overlayet ovenpå — står i [Dataflow › Det private
overlay](../arkitektur/dataflow.md#det-private-overlay), og gentages ikke her.

---

## Stierne

| | Sti | Sat af |
|---|---|---|
| Lokalt | `../dnd-private-data/` (eget privat git-repo, søskende til dette) | `run-local.sh` |
| Server | `/srv/apps/flask_dnd-data/private-data/` | `deploy/update.sh` |

Begge sætter miljøvariablen `DND_PRIVATE_DATA_DIR`. Er den ikke sat, springes
overlayet bare over — appen kører fint uden.

---

## Tilføj et eget monster

1. **Find den rigtige fil.** Filnavnet skal matche `data/`-tabellen præcis. Skal
   monsteret i bestiaret, hedder filen det samme som SRD-filen for bestiaret.

2. **Skriv rækken** i `../dnd-private-data/<tabel>.yaml`, med samme kolonner som
   `data/<tabel>.yaml` bruger. Skemaet er fælles — det er `schema.sql`, og der
   er ingen separat "privat" tabel.

3. **Reseed lokalt** og se efter advarsler:

   ```bash
   .venv/bin/python importer.py
   ```

4. **Commit i det private repo** — ikke i dette. De to repoer er adskilte med
   vilje.

5. **På serveren:** læg filen i `/srv/apps/flask_dnd-data/private-data/` og
   reseed. Se fælde 2 nedenfor for hvorfor `--force-seed` er nødvendig.

---

## De tre fælder

!!! danger "1. Læg ALDRIG privat indhold i `data/` eller `adventures/`"

    Begge er versioneret i det **offentlige** repo. En egen NPC lagt i
    `data/*.yaml` eller i `adventures/*/adventure.md` bliver publiceret ved
    næste push.

    `Mordekain` i `adventures/Midsommer/` er en **bevidst valgt undtagelse** og
    bliver liggende. Den er ikke et fortilfælde for at lægge flere ind.

!!! warning "2. Serverens overlay følger ikke med `git pull`"

    Overlayet ligger i data-mappen, ikke i repoet — og `git pull` rører aldrig
    `/srv/apps/flask_dnd-data`. Det er hele pointen med adskillelsen, men det
    betyder også at et deploy **ikke** opdager at du har lagt en ny fil derop.

    `update.sh` reseeder kun hvis pullet ramte `data/`. Et overlay-tillæg
    ændrer intet i repoet, så den betingelse er falsk:

    ```bash
    sudo /srv/apps/flask_dnd/deploy/update.sh --force-seed
    ```

    `--force-seed` er den eneste vej. Se [Deploy › Reseed
    databasen](deploy.md#3-reseed-databasen-betinget).

!!! warning "3. Samme primærnøgle overskriver SRD-rækken"

    Overlayet lægges på med `INSERT OR REPLACE` og kommer **sidst**. Bruger du
    en nøgle der allerede findes i SRD'et, vinder din række — SRD-versionen
    forsvinder ud af databasen.

    Det er **tilladt** og nogle gange meningen (en husregel-version af et
    monster). Men seed'en printer `ADVARSEL` når det sker:

    ```
    ADVARSEL: privat række overskriver SRD-række …
    ```

    **Læs outputtet fra `importer.py`.** En utilsigtet kollision ser ellers ud
    som om SRD-data er forsvundet uden grund.

---

## Hvorfor et overlay og ikke en gren

En gren med private data skulle merges ved hver SRD-opdatering, og en fejlagtig
`git push` ville publicere alt. Overlayet kan ikke publiceres ved et uheld: det
ligger i et andet repo og en anden mappe, og det offentlige repo har ingen
reference til det.

Prisen er den du betaler i fælde 2 — deploy kan ikke se overlayet, så
opdateringer kræver `--force-seed`. Det er en bevidst byttehandel.
