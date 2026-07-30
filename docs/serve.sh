#!/usr/bin/env bash
# Læs dokumentationen lokalt med live-reload — samme idé som ./run-local.sh,
# bare for docs/. Gem en .md-fil, og browseren opdaterer sig selv.
#
# Brug:   ./docs/serve.sh            → http://localhost:8000
#         ./docs/serve.sh --fresh    → smid .venv-docs væk og installér forfra
#
# Første kørsel opretter .venv-docs (gitignoreret) og installerer
# docs/requirements.txt. Appens egen .venv røres ikke.
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv-docs"

if [ "${1:-}" = "--fresh" ]; then
  rm -rf "$VENV"
  echo "Fjernede $VENV — installerer forfra."
  shift
fi

if [ ! -x "$VENV/bin/mkdocs" ]; then
  echo "Opretter $VENV og installerer docs/requirements.txt…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r docs/requirements.txt
fi

# Genererede referencesider (datamodel + ruter) bygges først, så de altid
# matcher koden. BEMÆRK: gen_docs.py kører med APPENS venv, ikke .venv-docs —
# den læser ruterne ud af den rigtige Flask-app og har derfor brug for flask
# og ruamel.yaml. Mangler appens venv, springes generering over (de committede
# sider bruges) frem for at fejle.
if [ -x .venv/bin/python ]; then
  .venv/bin/python scripts/gen_docs.py
else
  echo "BEMÆRK: appens .venv mangler — bruger de committede genererede sider." >&2
fi

echo "▶ http://localhost:8000   (Ctrl+C for at stoppe)"
# 0.0.0.0 så siden også kan læses fra tablet/telefon på LAN'et under skrivning.
exec "$VENV/bin/mkdocs" serve --dev-addr 0.0.0.0:8000 "$@"
