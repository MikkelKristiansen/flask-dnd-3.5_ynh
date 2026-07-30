# Faldgruber

Fejl der allerede har kostet tid. De står med **symptom først**, fordi det er
symptomet du har i hånden når du leder — ikke årsagen.

Ingen af dem er teoretiske. Hver enkelt er sket.

---

## Links bliver dobbeltpræfiksede: `/dnd/dnd/karakter/…`

!!! danger "Sæt IKKE `X-Forwarded-Prefix` i Caddy"

    **Symptom:** alle links på siden peger ét niveau for dybt. Forsiden virker,
    men alt du klikker på giver 404.

    **Årsag:** appen sætter selv `ProxyFix(app.wsgi_app, x_prefix=1)` i
    `app.py`. Sender proxyen så *også* en `X-Forwarded-Prefix`-header, lægges
    præfikset på to gange.

    **Fix:** fjern headeren fra Caddy-blokken. Appen skal ikke have den.

Vanen stammer fra YunoHost-tiden, hvor appen lå under `dnd.mkuv.dk/dnd/` og
præfikset var reelt. Efter flytningen **26. juli 2026** ligger appen i roden af
sit eget domæne, og headeren gør kun skade. Den ser rigtig ud at tilføje, og det
er præcis derfor den er farlig.

---

## Data er "ikke opdateret" efter et deploy

!!! warning "`srd35.db` genseedes IKKE af `git pull` alene"

    **Symptom:** du har rettet en `data/*.yaml`, pushet og pullet — men appen
    viser stadig det gamle.

    **Årsag:** `srd35.db` er gitignoreret. Den *bygges* af `importer.py` ud fra
    `data/` + `schema.sql`; git flytter kun kilderne, ikke resultatet.

    **Fix:** brug `deploy/update.sh`. Den reseeder betinget — se
    [Deploy](deploy.md). Manuelt:

    ```bash
    cd /srv/apps/flask_dnd
    sudo -u apps DND_DB_PATH=/srv/apps/flask_dnd-data/srd35.db \
        venv/bin/python importer.py
    sudo systemctl restart flask_dnd
    ```

---

## `pytest` fejler med hundredvis af "no such table"

!!! warning "En frisk klon har ingen database"

    **Symptom:** på en nyklonet maskine fejler suiten massivt — **296 failed /
    406 passed** (målt 30. juli 2026) med `sqlite3.OperationalError: no such
    table: …`.

    **Årsag:** `srd35.db` er gitignoreret og findes ikke endnu. Testene fejler
    ikke på logik, men på et tomt fundament.

    **Fix:** seed først.

    ```bash
    .venv/bin/python importer.py
    .venv/bin/python -m pytest -q      # → 702 passed
    ```

Tallene er værd at kende: ser du **296 failed**, er det næsten altid dette og
ikke noget du har ødelagt.

!!! note "Kunne løses i koden"
    En pytest-fixture kunne seede databasen automatisk og fjerne fælden helt.
    Det er en kodeændring, ikke dokumentation — noteret her, ikke gjort.

---

## Fristelsen til at bumpe en version før deploy

!!! danger "Foreslå ALDRIG et `manifest.toml`-versionsbump"

    **Symptom:** en vane siger "bump versionen før du deployer".

    **Årsag:** ynh-laget — `manifest.toml`, `conf/`, ynh-`scripts/` — blev
    **fjernet 26. juli 2026**, da appen flyttede fra YunoHost/rpi5 til systemd
    på Proxmox.

    **Fix:** der er ingen version at bumpe. Filen findes ikke. Deploy er
    `git push` + `update.sh`, intet andet.

---

## Et igangværende eventyr er ikke i git

!!! danger "Repoets `adventures/` er en seed, ikke sandheden"

    **Symptom:** du regner med at `git push` har sikret dit eventyr. Det har den
    ikke.

    **Årsag:** `adventures/` findes to steder. `paths.py` udleder
    `ADVENTURES_DIR` af `CHARACTERS_DIR.parent`, og unitten peger
    `DND_CHARACTERS_DIR` ind i data-mappen:

    | | Sti | I git? |
    |---|---|---|
    | Repoets seed + `_TEMPLATE` | `adventures/` | ja |
    | **Det appen faktisk læser** | `/srv/apps/flask_dnd-data/adventures/` | **nej** |

    **Fix:** redigerer du et eventyr i DM-modulet, lander det i data-mappen og
    aldrig i git. Skal det sikres, skal data-mappen med i en backup — `git push`
    dækker den ikke.

Det er ikke en fejl i opsætningen: kode og data er adskilt med vilje. Fælden er
at *tro* repoets kopi er den levende.

---

## 500-fejl når et portræt uploades

!!! warning "`portraits/` skal ejes af tjenestebrugeren"

    **Symptom:** upload af et karakterportræt giver 500 i stedet for et billede.

    **Årsag:** mappen under `/srv/apps/flask_dnd-data/` er ejet af en anden
    bruger end den tjenesten kører som, så skrivningen afvises.

    **Fix:** ejerskabet skal være `flask_dnd`/`apps` — samme bruger som unitten
    kører under. Gælder hele data-laget, men portrætter er der hvor det
    opdages, fordi det er den eneste sti hvor webappen selv skriver filer.

---

## Tjenesten starter — men uden adgangskontrol

!!! danger "Deploy udruller BEVIDST ikke unit-filen"

    **Symptom:** en ændring du lavede i `deploy/flask_dnd.service` har ingen
    effekt efter deploy.

    **Årsag:** `update.sh` kopierer aldrig unitten til `/etc/systemd/system/`.
    Den *advarer* i stedet, hvis den installerede afviger:

    ```
    BEMÆRK: /etc/systemd/system/flask_dnd.service afviger fra deploy/flask_dnd.service.
    ```

    **Fix:** læs advarslen, og kopiér unitten i hånden hvis ændringen skal med.

Hvorfor det er sådan med vilje: unitten kan have lokale tilpasninger på
serveren, og en genstart med en forkert unit er værre end en forældet. En
automatisk udrulning ville overskrive dem tavst.

**Den gang det bed:** `EnvironmentFile` med kodeords-hashene blev tilføjet i
repoets unit, nåede aldrig `/etc`, og appen kørte derfor **uden
adgangskontrol**. Det er også grunden til at stien i dag står uden bindestreg —
mangler filen, nægter tjenesten at starte. Se
[Adgangskontrol](index.md#adgangskontrol).

---

## Private NPC'er havner i et offentligt repo

!!! danger "Læg aldrig privat indhold i `data/` eller `adventures/`"

    **Symptom:** en egen NPC dukker op i en commit til det offentlige repo.

    **Årsag:** både `data/*.yaml` og `adventures/*/adventure.md` er versioneret.

    **Fix:** privat indhold hører i overlayet — se
    [Privat overlay](privat-overlay.md).

    `Mordekain` i `adventures/Midsommer/` er en **bevidst valgt undtagelse** og
    bliver liggende. Den er ikke et fortilfælde.
