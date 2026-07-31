# 0002: Flad filstruktur i repo-roden

**Status:** gældende · **Besluttet:** 26. juli 2026 (`1112a9e`)

## Problem

Appen var pakket som en YunoHost-applikation. Al appkode lå i en `sources/`-mappe
ved siden af ynh-lagets `conf/`, `manifest.toml` og
`scripts/{install,upgrade,remove,backup,restore}`.

Da appen flyttede til systemd på Proxmox, forsvandt grunden til den opdeling:
`sources/` fandtes udelukkende, fordi ynh-pakkeformatet krævede at appkoden lå
adskilt fra pakkens egne filer. Spørgsmålet var, hvad der skulle træde i stedet.

## Beslutning

**Al appkode ligger fladt i repo-roden.** Ingen `src/`, ingen `sources/`, ingen
pakke-mapper. 196 filer blev fladet ud, og hele ynh-laget fjernet i samme
commit.

Kun rene, ikke-kode-aktiver har egen mappe: `data/`, `templates/`, `static/`,
`defaults/`, `adventures/`, `editor/`, `scripts/`, `deploy/`, `docs/`.

Det virker, fordi filerne er skarpt opdelt efter **ansvar** — `rules.py` regner,
`db.py` læser, `paths.py` kender stier. Strukturen ligger i lagdelingen, ikke i
mappetræet.

## Forkastet

**At beholde `sources/`.** Mappen bar ingen betydning efter ynh: den var ét
niveau ekstra på hver eneste sti, i hver import, i hvert testkald og i enhver
`grep`. En mappe der ikke adskiller noget, koster kun.

**At erstatte den med et rigtigt `src/`-layout eller Python-pakker.** Det ville
have været en ægte omstrukturering — nye `__init__.py`-filer, omskrevne imports
overalt, og et pakkenavn at forholde sig til — for en app hvor alle moduler i
forvejen er entydigt navngivet og importeres direkte. Gevinsten var
navnerumsbeskyttelse mod et problem projektet ikke har.

## Konsekvens

- **Rediger altid i repo-roden.** Ser du en sti med `sources/` i en gammel
  brief, et gammelt script eller en gammel note, er den forældet. Flytningen
  ramte også `paths.py`, testene, JS-smoketesten og Emacs-modet.
- **`manifest.toml` findes ikke længere.** Et versionsbump i den fil er en vane
  fra ynh-tiden og skal ikke foreslås.
- **Prisen er en stor rodmappe.** Cirka 70 `.py`-filer ligger side om side. Det
  er acceptabelt, fordi navnene er præcise, men det betyder at *filnavnet* skal
  bære sit ansvar tydeligt — der er ingen mappe til at gøre det.
- Nærmer en fil sig ~200-300 linjer eller begynder at blande ansvar, spaltes den
  ud i en ny fil i roden. `attacks.py` blev sådan spaltet ud af `rules.py` med
  en bevidst én-vejs-afhængighed — se
  [Regelmotor](../arkitektur/regelmotor.md#en-vejs-afhngigheden-mellem-rules-og-attacks).

Se [Arkitektur](../arkitektur/index.md) for lagdelingen og filkortet.
