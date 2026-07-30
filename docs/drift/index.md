# Drift

Appen kører som systemd-tjeneste på Proxmox. Ynh-pakningen blev fjernet
**26. juli 2026**; der er ingen `manifest.toml` og ingen version at bumpe før
deploy.

## Hvor tingene er

| | |
|---|---|
| Vært | LXC 112 `apps-mk` (192.168.0.73) |
| Tjeneste | `flask_dnd` — gunicorn, 2 workers, `127.0.0.1:8764` |
| Offentlig URL | [https://dnd.mkuv.dk](https://dnd.mkuv.dk) via Caddy |
| Kode | `/srv/apps/flask_dnd/` (git-klon + `venv/`) |
| Data | `/srv/apps/flask_dnd-data/` |
| Hemmeligheder | `/etc/flask_dnd.env` (chmod 600, uden for git) |
| Bruger | `apps` |

Kode og data er **adskilt med vilje**, præcis som de var på rpi5. Unitten
sætter kun to stier:

```ini
Environment=DND_DB_PATH=/srv/apps/flask_dnd-data/srd35.db
Environment=DND_CHARACTERS_DIR=/srv/apps/flask_dnd-data/characters
```

Alle øvrige datastier — `portraits/`, `adventures/`, `sessions/`,
`monster_tokens/`, `private-data/` — udleder `paths.py` af
`CHARACTERS_DIR.parent`. Derfor er to variabler nok, og derfor flytter man hele
brugerdata-laget ved at pege `DND_CHARACTERS_DIR` et andet sted hen.

## Adgangskontrol

To delte kodeord (spiller og DM). Hashes ligger i `/etc/flask_dnd.env`, som
unitten indlæser **uden** bindestreg foran stien:

```ini
EnvironmentFile=/etc/flask_dnd.env
```

Det er et bevidst valg: mangler filen, **nægter tjenesten at starte**. Det er
bedre end at starte uden adgangskontrol — hvilket er sket før (da
`EnvironmentFile` blev tilføjet i repoets unit, men aldrig kopieret til `/etc`).

Nye hashes laves med `scripts/lav-kodeord-hash.py`. Sætter du ingen kodeord i
miljøet, slår `auth.py` sig selv fra og logger en advarsel — det er den
tilstand `run-local.sh` kører i.

## Deploy, kort

```bash
git push                                     # fra dev.lan, efter Mikkels ok
sudo /srv/apps/flask_dnd/deploy/update.sh    # på apps-mk
```

`update.sh` gør: `git pull --ff-only` → reseeder `srd35.db` **kun** hvis noget
under `data/` ændrede sig → genstarter → health-checker `:8764` (både 200 og 302
tælles som sundt, fordi en ulogget klient sendes til `/login`).

Rollback: `git checkout <commit>` + `sudo systemctl restart flask_dnd`.
`git pull` er ufarlig for data — den rører aldrig `/srv/apps/flask_dnd-data`.

**[Deploy i detaljer](deploy.md)** — hvad hvert trin gør og hvorfor, hvorfor
unit-filen bevidst ikke udrulles, og forbeholdet ved rollback.

## Videre herfra

| Side | Hvad den dækker |
|---|---|
| [Deploy](deploy.md) | `update.sh` trin for trin, rollback |
| [Privat overlay](privat-overlay.md) | egne NPC'er: stier, arbejdsgang, de tre fælder |
| [Faldgruber](faldgruber.md) | fejl der har kostet tid — slå op på symptomet |
