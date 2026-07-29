# D&D 3.5 Character Sheet

En tablet-optimeret Flask-webapp til håndtering af D&D 3.5 karakterark.
Kører som systemd-tjeneste; deploy sker via git (se nedenfor). Ynh-pakningen
blev fjernet 26. juli 2026.

## Funktioner

- Karakterark med ability scores, saves, HP-tracker og conditions
- Skills med synergibonus (SRD 3.5)
- Spell-forberedelse og spells-used-tracking
- Feats og items med noter
- Terningkast direkte fra arket
- Markdown-notesblok
- Gemmer automatisk til YAML ved ændringer

## Lokal udvikling

```bash
./run-local.sh            # starter på http://localhost:5000 (auto-reload)
./run-local.sh --fresh    # nulstiller lokal test-tilstand + srd35.db
```

## Deploy

Appen kører som systemd-tjeneste (`flask_dnd`) i `/srv/apps/flask_dnd` på serveren.
Deploy = push fra din maskine, opdatér på serveren:

```bash
git push                                   # fra din maskine
# på serveren:
sudo /srv/apps/flask_dnd/deploy/update.sh
```

`deploy/update.sh` gør det hele: `git pull` → reseeder `srd35.db` **kun** hvis
`data/*.yaml` eller `schema.sql` ændrede sig → genstarter tjenesten → health-check.
Brug `--force-seed` for at reseede uanset. `srd35.db` genseedes ikke af `git pull`
alene, så kør altid via scriptet (eller reseed manuelt, se nedenfor).

Rollback: `git checkout <commit>` + `sudo systemctl restart flask_dnd`.

Manuel reseed (hvis du ikke bruger scriptet):

```bash
cd /srv/apps/flask_dnd
sudo -u apps DND_DB_PATH=/srv/apps/flask_dnd-data/srd35.db venv/bin/python importer.py
sudo systemctl restart flask_dnd
```

## Privat indhold (egne NPC'er m.m.)

Repoet indeholder kun OGL-materiale. Hjemmelavede monstre, NPC'er, fælder og
magiske genstande hører til i et **privat data-overlay** uden for repoet — samme
filnavne og format som `data/`:

```
data/monsters.yaml          SRD-monstre (i git)
private-data/monsters.yaml  dine egne  (aldrig i dette repo)
                         →  begge seedes ind i srd35.db
```

`importer.py` læser SRD-filen først og lægger overlayet ovenpå, så private
monstre optræder i bestiaret, `@monster[id]`-autocomplete, encounters og på
brættet præcis som SRD-indholdet. Samme id som en SRD-række overskriver den —
tilladt, men seed'en advarer om det.

Stien styres af `DND_PRIVATE_DATA_DIR`: lokalt sætter `run-local.sh` den til
`../dnd-private-data` (eget privat git-repo, søskende til dette), på serveren
peger `deploy/update.sh` den på `/srv/apps/flask_dnd-data/private-data/`.
Serverens kopi følger ikke med app-repoets `git pull` — læg filerne derop og
kør `sudo /srv/apps/flask_dnd/deploy/update.sh --force-seed`.

## Filstruktur

```
app.py, *.py       App-kode (Flask, ruter, regel-motor) i roden
data/              SRD-data (YAML) — kilden importer.py seeder srd35.db fra
                   (+ privat overlay uden for repoet, se ovenfor)
templates/         Jinja2-templates          static/   CSS/JS/billeder
defaults/          Eksempel-karakterer (seed)  adventures/  eventyr-seeds
editor/            Emacs/redigerings-værktøjer
scripts/           Egne data-værktøjer (gen_control_e_rows, triage_*)
deploy/            flask_dnd.service (systemd-unit til serveren)
```

---

## Open Game License

Spell-, feat- og skill-data i `srd35.db` stammer fra
**System Reference Document (SRD) v3.5**, udgivet af Wizards of the Coast
under **Open Game License v1.0a**.

Alt SRD-afledt indhold i dette repository er **Open Game Content**
som defineret i OGL afsnit 1(d).

Den fulde licenstekst findes i [`OGL.txt`](OGL.txt).

### Section 15 — Copyright Notice

```
Open Game License v1.0a Copyright 2000, Wizards of the Coast, Inc.

System Reference Document Copyright 2000-2003, Wizards of the Coast, Inc.;
Authors Jonathan Tweet, Monte Cook, Skip Williams, Rich Baker, Andy Collins,
David Noonan, Rich Redman, Bruce R. Cordell, John D. Rateliff, Thomas Reid,
James Wyatt, based on original material by E. Gary Gygax and Dave Arneson.

flask-dnd-3.5 Copyright 2024-2025, Mikkel Kristiansen.
```
