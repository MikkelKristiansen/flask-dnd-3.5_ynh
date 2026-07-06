#!/usr/bin/env bash
# Kør D&D-webappen lokalt til udvikling/test (debug=True → auto-reload:
# template/CSS-ændringer slår igennem ved browser-refresh, .py-ændringer
# genstarter serveren). Ingen git/yunohost nødvendig for at se ændringer.
#
# Gør før den starter Flask:
#   1. Tjekker at flask/ruamel.yaml er installeret.
#   2. Seeder srd35.db fra data/*.yaml hvis den mangler (genereres, ikke i git).
#   3. Lokal, git-ignoreret kopi af eksempel-karaktererne, så test IKKE ændrer
#      de committede defaults/.
#   4. DM-sessioner i en lokal, git-ignoreret mappe (så de ikke roder git-status).
#      Eventyr læses direkte fra sources/adventures/ (rediger adventure.md +
#      refresh for at se ændringer live).
#
# Brug:   ./run-local.sh            → starter på http://localhost:5000
#         ./run-local.sh --fresh    → nulstiller test-data OG srd35.db (brug efter
#                                      ændringer i data/*.yaml eller schema.sql)
set -euo pipefail

cd "$(dirname "$0")/sources"

DATA_DIR=".local-characters"
SESS_DIR=".local-sessions"

# --fresh: smid lokal test-tilstand + databasen væk, så alt seedes/genopbygges.
if [ "${1:-}" = "--fresh" ]; then
  rm -rf "$DATA_DIR" "$SESS_DIR" backups srd35.db
  echo "Nulstillede lokal test-tilstand ($DATA_DIR, $SESS_DIR, backups) + srd35.db."
fi

# 1) Afhængigheder
if ! python -c "import flask, ruamel.yaml" 2>/dev/null; then
  echo "Mangler flask/ruamel.yaml. Installer med:" >&2
  echo "  pip install -r sources/requirements.txt" >&2
  exit 1
fi

# 2) SRD-databasen (genereres af importer.py, ikke versioneret)
if [ ! -f srd35.db ]; then
  echo "Seeder srd35.db…"
  python importer.py
fi

# 3) Lokal karakter-mappe (git-ignoreret) seedet fra defaults/
if [ ! -d "$DATA_DIR" ]; then
  echo "Opretter lokal test-mappe $DATA_DIR fra defaults/…"
  mkdir -p "$DATA_DIR"
  cp defaults/*.yaml "$DATA_DIR"/
fi

# 4) Start. DND_ADVENTURES_DIR er ikke sat → defaulter til sources/adventures/
#    (de committede eventyr). Sessioner holdes i en lokal, git-ignoreret mappe.
echo "▶ http://localhost:5000   (Ctrl+C for at stoppe)"
DND_CHARACTERS_DIR="$DATA_DIR" DND_SESSIONS_DIR="$SESS_DIR" python app.py
