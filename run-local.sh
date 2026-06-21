#!/usr/bin/env bash
# Kør D&D-webappen lokalt til udvikling/test.
#
# Gør tre ting før den starter Flask:
#   1. Tjekker at flask/ruamel.yaml er installeret.
#   2. Seeder srd35.db fra data/*.yaml hvis den mangler (genereres, ikke i git).
#   3. Bruger en lokal, git-ignoreret kopi af eksempel-karaktererne, så test
#      (tilføj/rediger angreb osv.) IKKE ændrer de committede defaults/.
#
# Brug:   ./run-local.sh            → starter på http://localhost:5000
#         ./run-local.sh --fresh    → nulstiller test-karaktererne fra defaults/
set -euo pipefail

cd "$(dirname "$0")/sources"

DATA_DIR=".local-characters"

# --fresh: smid den lokale test-mappe væk, så den seedes på ny fra defaults/
if [ "${1:-}" = "--fresh" ]; then
  rm -rf "$DATA_DIR" backups
  echo "Nulstillede $DATA_DIR (og lokale backups)."
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

# 4) Start
echo "▶ http://localhost:5000   (Ctrl+C for at stoppe)"
DND_CHARACTERS_DIR="$DATA_DIR" python app.py
