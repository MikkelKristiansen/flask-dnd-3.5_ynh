#!/usr/bin/env bash
# Byg dokumentationen til statisk HTML i site/ (gitignoreret).
#
# Brug:   ./docs/build.sh                      → byg til site/
#         ./docs/build.sh --udgiv              → byg + rsync til docs.mkuv.dk/dnd/
#
# --udgiv kræver at 'ssh edge true' virker uden prompt, og at rsync er
# installeret i begge ender. Både x1 og dev.lan kan i dag — men ad hver sin
# vej, se DOCS_FJERN_ROD nedenfor.
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv-docs"

# edge (192.168.0.70, LXC 110) er maskinen med Caddy — IKKE apps-mk, som denne
# fil hævdede indtil 31. jul 2026. apps-mk har ikke engang /etc/caddy.
FJERN_VAERT="${DOCS_FJERN_VAERT:-edge}"

# ###  ROD + SLUG, ikke én færdig sti. Læs før du forenkler.  ###
#
# Variablen holder KUN maskinens rod. Sluggen ('dnd') hører til projektet og
# sættes af scriptet her. Det er hele pointen: en variabel der indeholdt den
# færdige sti kunne ikke være rigtig for både hub og projekter på én gang —
# hub'en skulle bruge '/' og dette projekt '/dnd/'. Med én global export i
# ~/.bashrc vandt hub'ens værdi, og et 'rsync --delete' herfra ville så have
# ramt RODEN og slettet alle projekternes mapper. Derfor blev den gamle
# DOCS_FJERN_STI afskaffet — genindfør den ikke.
#
#   x1       ingen DOCS_*-variabler → default herunder, root-ssh, fuld sti.
#   dev.lan  kontoen 'docs-udgiver', låst til 'rrsync -wo /srv/www/docs.mkuv.dk'.
#            rrsync gør stien RELATIV til den mappe, så dev.lan sætter
#            DOCS_FJERN_ROD=/ i sin ~/.bashrc → stien bliver /dnd/.
# Den relative sti ER sikkerheden: kontoen kan ikke skrive uden for mappen.
DOCS_FJERN_ROD="${DOCS_FJERN_ROD:-/srv/www/docs.mkuv.dk}"
# %/ klipper en eventuel afsluttende skråstreg, så roden må skrives med eller
# uden — ellers gav '…/docs.mkuv.dk' stien '…/docs.mkuv.dkdnd/'.
FJERN_STI="${DOCS_FJERN_ROD%/}/dnd/"

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
