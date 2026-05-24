# D&D 3.5 Character Sheet — YunoHost-pakke

En tablet-optimeret Flask-webapp til håndtering af D&D 3.5 karakterark.
Pakket som YunoHost-app med Gunicorn og Nginx.

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
cd sources/
DND_CHARACTERS_DIR=defaults/ python app.py
# Åbn http://localhost:5000
```

## Deploy (YunoHost)

```bash
yunohost app upgrade flask_dnd --url https://github.com/MikkelKristiansen/flask-dnd-3.5_ynh.git
```

## Filstruktur

```
sources/          App-kode (Flask, Jinja2-templates)
conf/             Nginx + systemd-konfiguration (med __PLACEHOLDERS__)
scripts/          YunoHost install/upgrade/remove/backup/restore
```

---

## Open Game License

Spell-, feat- og skill-data i `sources/srd35.db` stammer fra
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
