#!/usr/bin/env bash
# Deploy/opdater flask_dnd på serveren: git pull → (reseed db hvis data ændret) → restart.
#
# Kør som root på apps-mk:
#     sudo /srv/apps/flask_dnd/deploy/update.sh
#     sudo /srv/apps/flask_dnd/deploy/update.sh --force-seed   # reseed uanset ændringer
#
# - Henter nyeste main med --ff-only (aldrig merge-commits på en deploy-server;
#   fejler højlydt hvis serveren er divergeret i stedet for at flette blindt).
# - Reseeder srd35.db KUN hvis noget under data/ ændrede sig i pullet (både *.yaml
#   og schema.sql ligger dér — det er hele importer.py's input)
#   (eller --force-seed, eller hvis db-filen mangler). Reference-db'en er genereret
#   fra data/ + schema.sql; brugerdata (characters/adventures/sessions/…) ligger i
#   flask_dnd-data/ og røres ALDRIG af importer.py.
# - Genstarter tjenesten og health-checker :8764.
set -euo pipefail

# ── Konfiguration (matcher flask_dnd.service) ────────────────────────────────
APP_DIR=/srv/apps/flask_dnd
DATA_DB=/srv/apps/flask_dnd-data/srd35.db
# Privat data-overlay (egne NPC'er m.m., ikke i det offentlige repo). Ligger i
# data-mappen som alt andet brugerdata; opdateres IKKE af pullet herunder — når
# du har lagt nye filer derop, reseed med --force-seed.
PRIVATE_DATA=/srv/apps/flask_dnd-data/private-data
APP_USER=apps
SERVICE=flask_dnd
PORT=8764

# ── Forudsætninger ───────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  echo "Kør scriptet som root (sudo) — det skal både git-pulle som $APP_USER og genstarte tjenesten." >&2
  exit 1
fi

force_seed=false
[ "${1:-}" = "--force-seed" ] && force_seed=true

cd "$APP_DIR"

# ── 1) Hent nyeste kode ──────────────────────────────────────────────────────
before=$(sudo -u "$APP_USER" git rev-parse HEAD)
sudo -u "$APP_USER" git pull --ff-only
after=$(sudo -u "$APP_USER" git rev-parse HEAD)

if [ "$before" = "$after" ] && ! $force_seed; then
  echo "Ingen nye commits ($after) — intet at gøre."
  exit 0
fi

# ── 1b) Advar hvis den kørende unit er drevet fra repoets ────────────────────
# Deploy udruller BEVIDST ikke unit-filen (den kan have lokale tilpasninger, og
# en restart med en forkert unit er værre end en forældet). Men en ændring i
# repoet, der aldrig når /etc, er svær at få øje på — fx da EnvironmentFile med
# kodeords-hashene blev tilføjet, og appen derfor startede uden adgangskontrol.
INSTALLED_UNIT="/etc/systemd/system/$SERVICE.service"
if [ -f "$INSTALLED_UNIT" ] && \
   ! diff -q "$INSTALLED_UNIT" "$APP_DIR/deploy/$SERVICE.service" >/dev/null 2>&1; then
  echo "BEMÆRK: $INSTALLED_UNIT afviger fra deploy/$SERVICE.service."
  echo "        Deploy rører ikke unit-filen — se forskellen med:"
  echo "          diff $INSTALLED_UNIT $APP_DIR/deploy/$SERVICE.service"
  echo "        Skal repoets version gælde: cp den ind, systemctl daemon-reload."
fi

# ── 2) Reseed db'en hvis nødvendigt ──────────────────────────────────────────
need_seed=false
if $force_seed; then
  need_seed=true
elif [ ! -f "$DATA_DB" ]; then
  echo "srd35.db mangler — reseeder."
  need_seed=true
elif sudo -u "$APP_USER" git diff --name-only "$before" "$after" | grep -q '^data/'; then
  need_seed=true
fi

if $need_seed; then
  echo "Reseeder $DATA_DB …"
  sudo -u "$APP_USER" DND_DB_PATH="$DATA_DB" DND_PRIVATE_DATA_DIR="$PRIVATE_DATA" \
    "$APP_DIR/venv/bin/python" importer.py
else
  echo "Ingen ændringer under data/ — springer reseed over."
fi

# ── 3) Genstart + health-check ───────────────────────────────────────────────
echo "Genstarter $SERVICE …"
systemctl restart "$SERVICE"
sleep 2

code=$(curl -s -o /dev/null -w "%{http_code}" --retry 5 --retry-connrefused --retry-delay 1 --max-time 8 "http://127.0.0.1:$PORT/" || true)
echo "Health: http://127.0.0.1:$PORT/ -> $code"
# 302 er lige så sundt som 200: med adgangskontrol slået til sender "/" en
# ulogget klient (og det er curl her) videre til /login. Health-checket spørger
# kun om tjenesten svarer — ikke om den lukker os ind.
case "$code" in
  200|302) ;;
  *)
    echo "ADVARSEL: uventet HTTP-status efter genstart — tjek 'journalctl -u $SERVICE'." >&2
    exit 1
    ;;
esac

echo "Deploy OK: ${before:0:9} -> ${after:0:9}"
