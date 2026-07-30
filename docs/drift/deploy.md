# Deploy

Deploy er to kommandoer. Alt det interessante ligger i hvad den anden af dem
gør — og i det den bevidst *ikke* gør.

```bash
git push                                     # fra dev.lan, efter Mikkels ok
sudo /srv/apps/flask_dnd/deploy/update.sh    # på apps-mk
```

`update.sh` er versioneret i `deploy/` og kører som root, fordi den skal både
git-pulle som brugeren `apps` og genstarte tjenesten.

---

## Hvad `update.sh` gør, trin for trin

### 1. Hent nyeste kode — `--ff-only`

```bash
git pull --ff-only
```

`--ff-only` er ikke en detalje. **En deploy-server skal aldrig lave
merge-commits.** Er serveren divergeret fra `main` — nogen har rettet noget
direkte i `/srv/apps/flask_dnd` — så fejler pullet **højlydt** i stedet for at
flette blindt og efterlade serveren i en tilstand der ikke findes i noget repo.

Scriptet sammenligner `HEAD` før og efter. Er der ingen nye commits, stopper det
med det samme:

```
Ingen nye commits (a1b2c3d) — intet at gøre.
```

`--force-seed` kører videre alligevel — se nedenfor.

### 2. Advar hvis unit-filen er drevet

Se [Deploy udruller ikke unit-filen](#deploy-udruller-bevidst-ikke-unit-filen)
nedenfor. Dette trin *advarer* kun.

### 3. Reseed databasen — betinget

`srd35.db` genbygges i tre tilfælde, ikke ellers:

| Betingelse | Hvorfor |
|---|---|
| `--force-seed` | manuelt valg — fx efter en ændring i det private overlay |
| `srd35.db` mangler | intet fundament at køre på |
| pullet ramte `^data/` | kilderne til databasen er ændret |

Testen er bevidst simpel:

```bash
git diff --name-only "$before" "$after" | grep -q '^data/'
```

**Både `data/*.yaml` og `schema.sql` ligger under `data/`** — det er hele
`importer.py`'s input. Derfor er ét præfiks nok til at fange begge.

Er intet ændret, springes trinnet over:

```
Ingen ændringer under data/ — springer reseed over.
```

!!! info "Reseed rører aldrig brugerdata"
    `importer.py` skriver kun `srd35.db`. `characters/`, `adventures/`,
    `sessions/`, `portraits/` og `backups/` ligger i
    `/srv/apps/flask_dnd-data/` og bliver **aldrig** rørt. Reference-data og
    brugerdata er to forskellige ting, også når de ligger i samme mappe.

Seed'en kører med begge datastier sat, så det private overlay kommer med:

```bash
DND_DB_PATH=…/srd35.db DND_PRIVATE_DATA_DIR=…/private-data venv/bin/python importer.py
```

### 4. Genstart + health-check

```
Health: http://127.0.0.1:8764/ -> 302
Deploy OK: a1b2c3d4e -> f6e5d4c3b
```

!!! warning "302 er lige så sundt som 200"
    Med adgangskontrol slået til sender `/` en ulogget klient videre til
    `/login` — og curl **er** en ulogget klient. Health-checket spørger om
    tjenesten svarer, ikke om den lukker os ind.

    Accepterer man kun 200, fejler hvert eneste deploy på en korrekt sikret app.
    Alt andet end 200/302 afbryder med exitkode 1 og henviser til
    `journalctl -u flask_dnd`.

---

## Deploy udruller BEVIDST ikke unit-filen

`update.sh` kopierer **aldrig** `deploy/flask_dnd.service` til
`/etc/systemd/system/`. Den advarer i stedet, hvis de to afviger:

```
BEMÆRK: /etc/systemd/system/flask_dnd.service afviger fra deploy/flask_dnd.service.
        Deploy rører ikke unit-filen — se forskellen med:
          diff /etc/systemd/system/flask_dnd.service /srv/apps/flask_dnd/deploy/flask_dnd.service
        Skal repoets version gælde: cp den ind, systemctl daemon-reload.
```

**Hvorfor:** unitten kan have lokale tilpasninger på serveren, og en genstart
med en *forkert* unit er værre end at køre videre på en forældet. En automatisk
udrulning ville overskrive tilpasningerne tavst.

!!! danger "Den gang det bed"
    `EnvironmentFile` med kodeords-hashene blev tilføjet i repoets unit — og
    nåede aldrig `/etc`. Appen kørte derfor **uden adgangskontrol**, uden at
    noget så forkert ud.

    Advarslen i trin 2 findes udelukkende på grund af den hændelse. Det er også
    derfor stien i dag står **uden** bindestreg: mangler filen, nægter
    tjenesten at starte, i stedet for at starte åbent. Se
    [Adgangskontrol](index.md#adgangskontrol).

Læs altså advarslen når den kommer. Den er den eneste besked i outputtet der
kræver en beslutning.

---

## Rollback

```bash
cd /srv/apps/flask_dnd
sudo -u apps git checkout <commit>
sudo systemctl restart flask_dnd
```

**Rollback er ufarligt for data.** `git checkout` og `git pull` rører kun
`/srv/apps/flask_dnd` — aldrig `/srv/apps/flask_dnd-data`. Karakterer,
eventyrer og sessioner overlever enhver kode-rullen frem og tilbage.

!!! note "Ét forbehold"
    Ruller du tilbage forbi en ændring i `data/` eller `schema.sql`, passer
    databasen ikke længere til koden. Kør `update.sh --force-seed` bagefter, så
    `srd35.db` bygges fra den kode du faktisk kører.

---

## Ingen version at bumpe

Der er **ingen `manifest.toml`** og intet versionsnummer at hæve før deploy.
Ynh-laget blev fjernet 26. juli 2026. Se [Faldgruber](faldgruber.md).
