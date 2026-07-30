#!/usr/bin/env bash
# Byg dokumentationen til statisk HTML i site/ (gitignoreret).
#
# Brug:   ./docs/build.sh                      → byg til site/
#         ./docs/build.sh --udgiv              → byg + rsync til docs.mkuv.dk
#
# --udgiv kræver ssh-adgang til apps-mk. Kører du det derfra hvor der ikke er
# nøgle, så byg lokalt og send site/ over med rsync i hånden — se
# docs/drift/dokumentation.md.
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv-docs"
FJERN_VAERT="apps-mk"
FJERN_STI="/srv/www/docs.mkuv.dk/dnd/"

if [ ! -x "$VENV/bin/mkdocs" ]; then
  echo "Mangler $VENV. Kør ./docs/serve.sh én gang først (den installerer den)." >&2
  exit 1
fi

# Genererede sider først, så site/ aldrig indeholder en forældet datamodel.
# gen_docs.py kører med APPENS venv (den læser app.url_map → kræver flask).
# Her fejler vi højlydt hvis den mangler: en udgivelse må ikke ske med en
# datamodel-side der er ude af trit med koden.
if [ ! -x .venv/bin/python ]; then
  echo "Mangler appens .venv — kan ikke regenerere datamodel/ruter." >&2
  echo "Opret den, eller byg uden generering med: .venv-docs/bin/mkdocs build" >&2
  exit 1
fi
.venv/bin/python scripts/gen_docs.py

# --strict er slået til i mkdocs.yml: byggeriet FEJLER på døde interne links.
# Det er meningen — en dokumentation med døde links er værre end ingen.
"$VENV/bin/mkdocs" build --clean

echo "✓ Byggede site/ ($(du -sh site | cut -f1))"

if [ "${1:-}" = "--udgiv" ]; then
  echo "Sender til ${FJERN_VAERT}:${FJERN_STI} …"
  # --delete så slettede sider også forsvinder fra den udgivne version.
  rsync -az --delete site/ "${FJERN_VAERT}:${FJERN_STI}"
  echo "✓ Udgivet → https://docs.mkuv.dk/dnd/"
fi
