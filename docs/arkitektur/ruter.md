<!-- GENERERET AF scripts/gen_docs.py — REDIGÉR IKKE I HÅNDEN.
     Ret kilden (`app.py` + `routes_*.py` + `dm*.py`) og kør scriptet igen. -->


# Ruter

**81 ruter** fordelt på **8 grupper**. Kernen (karakterark, portrætter, terningkast) ligger i `app.py`; resten er udspaltet i blueprints — ét domæne pr. fil.

Ruter under `/api/` returnerer JSON og kaldes fra `static/*.js`. De øvrige renderer Jinja-templates.


## app.py (kerne)

Fil(er): `app.py`, `auth.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/` | GET | — |
| `/api/catalog` | GET | Beriget udstyrs-katalog til udrustningsbutikken (UI tegnes ud fra dette). |
| `/api/detail/<dtype>/<did>` | GET | — |
| `/api/hp` | POST | — |
| `/api/portrait` | POST | Skift/tilføj portræt på en eksisterende karakter (multipart-upload). |
| `/api/restore` | POST | — |
| `/api/roll/<path:expression>` | GET | — |
| `/create` | GET | — |
| `/create` | POST | Byg en ny level-1-karakter fra formularen, valider mod reglerne og skriv YAML. |
| `/delete/<slug>` | POST | Slet en karakter permanent: YAML-fil, snapshots og portræt. |
| `/dev/equipment-picker` | GET | Isoleret dev-testside for udrustningsbutik-komponenten (kun i debug). |
| `/dm/monster_token/<slug>` | GET | Server et monster-billed-token fra data-mappen (monster_tokens/<slug>. |
| `/export/<slug>` | GET | Hent en karakters rå YAML som fil-download (off-box kopi). |
| `/import` | POST | Importér en karakter-YAML fra brugerens disk. |
| `/karakter/<name>` | GET | — |
| `/login` | GET, POST | — |
| `/logout` | GET, POST | — |
| `/portrait/<slug>` | GET | Server karakterens portræt fra data-mappen (uden for Flasks static/). |

## Blueprint `combat`

Fil(er): `routes_combat.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/api/attacks` | POST | — |
| `/api/buffs` | POST | — |
| `/api/combat_options` | POST | Slå én kampindstilling til/fra (Point Blank/Dodge/Charge/Fighting Defensively — simple bools) ELLER sæt en talværdi (Power Attack/Combat Expertise — "editable" options, Lag B). |
| `/api/conditions` | POST | — |
| `/api/weapon_throw` | POST | Skift et kastbart våbens tilstand mellem nærkamp og kastet. |

## Blueprint `companion`

Fil(er): `routes_companion.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/api/companion` | POST | Tilkald en ny animal companion (summon) eller sig farvel til den (dismiss). |
| `/api/companion_hp` | POST | — |
| `/api/companion_tricks` | POST | — |
| `/api/familiar` | POST | Familiar-tab-tracker: familiaren dør (died) eller tæl ventetiden ned (cooldown). |
| `/api/wild_shape` | POST | Skift til en wild shape-form (shape) eller tilbage til egen form (revert). |

## Blueprint `dm`

Fil(er): `dm.py`, `dm_routes_content.py`, `dm_routes_encounter.py`, `dm_routes_media.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/dm/` | GET | — |
| `/dm/adventures` | POST | Opret et nyt eventyr fra forsiden og hop direkte i tekst-editoren. |
| `/dm/adventures/<adventure>` | GET | Administrér ét eventyrs kort/handout-billeder: se dem + upload + slet. |
| `/dm/adventures/<adventure>/edit` | GET, POST | Rediger et eventyrs rå Markdown i browseren (simpel tekstboks) — fjerner behovet for scp. |
| `/dm/adventures/<adventure>/media` | POST | — |
| `/dm/adventures/<adventure>/media/<filename>/delete` | POST | — |
| `/dm/api/catalog-statblock/<etype>/<ident>` | GET | Statblok for en katalog-post UDEN eventyr-kontekst (opslagsværket, begge lag). |
| `/dm/api/encounter/<slug>/board` | GET | Bræt-fragmentet for aktiv scenes primær-kort (kamp- eller opstillings- tilstand). |
| `/dm/api/encounter/<slug>/condition` | POST | — |
| `/dm/api/encounter/<slug>/door/<ref>` | GET | Dør-statblok til inspektøren, beriget med kamp-HP når en kamp kører. |
| `/dm/api/encounter/<slug>/door_hp` | POST | Justér en dørs kamp-HP (rå +/-, reset til fuld). |
| `/dm/api/encounter/<slug>/end` | POST | — |
| `/dm/api/encounter/<slug>/hp` | POST | — |
| `/dm/api/encounter/<slug>/initiative` | POST | — |
| `/dm/api/encounter/<slug>/move` | POST | Flyt en combatant til en ny grid-celle under kamp (live-position). |
| `/dm/api/encounter/<slug>/next` | POST | — |
| `/dm/api/encounter/<slug>/start` | POST | — |
| `/dm/api/entity-ids` | GET | Id+navn til editor-autocomplete (@monster/@faelde/@dør). |
| `/dm/api/give-loot` | POST | DM lægger et magisk item i en spillers rygsæk. |
| `/dm/api/party/<slug>` | POST | Rediger en kørende sessions party (Lag 2): tilføj/fjern en spiller. |
| `/dm/api/statblock/<adventure>/<etype>/<ident>` | GET | Slå en klikket entity op og returnér dens statblok som HTML-fragment til inspector-panelet. |
| `/dm/bestiary/<adventure>` | GET | Bestiarie-fane: alle monstre/NPC'er i ét eventyr som statblokke, så DM'en kan slå væsener op uden for en scene. |
| `/dm/board/<adventure>/<map_slug>` | GET | Vis et korts startopstilling (grid + tokens) med grid-kalibrering og træk-placér-editor. |
| `/dm/board/<adventure>/<map_slug>/grid` | POST | Gem grid-kalibreringen (cellestørrelse + offset) for et kort. |
| `/dm/board/<adventure>/<map_slug>/tokens` | POST | Gem token-placeringerne fra opstillings-editoren. |
| `/dm/media/<adventure>/<path:filename>` | GET | Servér et eventyrs billeder fra `adventures/<eventyr>/media/…`. |
| `/dm/monster-tokens` | GET | Administrér monster-billed-tokens i browseren: se, upload, slet — erstatter scp. |
| `/dm/monster-tokens/<slug>/delete` | POST | — |
| `/dm/monster-tokens/upload` | POST | — |
| `/dm/opslag` | GET | Selvstændigt opslagsværk: browse hele kataloget (monstre/fælder/døre/genstande). |
| `/dm/play/<slug>` | GET | — |
| `/dm/sessions` | POST | — |
| `/dm/sessions/<slug>/delete` | POST | — |

## Blueprint `inventory`

Fil(er): `routes_inventory.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/api/inventory` | POST | — |
| `/api/notes` | POST | — |

## Blueprint `progression`

Fil(er): `routes_progression.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/api/gold` | POST | — |
| `/api/levelup` | POST | — |
| `/api/newday` | POST | — |
| `/api/paladin` | POST | Paladin-ressourcer: brug en Smite Evil eller helbred dig selv med Lay on Hands. |
| `/api/xp` | POST | — |

## Blueprint `spells`

Fil(er): `routes_spells.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/api/cast_known` | POST | Spontan caster: forbrug (+1) eller frigiv (−1) en slot af et niveau. |
| `/api/domain_used` | POST | — |
| `/api/known_active` | POST | Spontane castere: opret/fjern en aktiv spell-INSTANS (varigheds-/vedvarende spell). |
| `/api/prepare` | POST | — |
| `/api/spell_charge` | POST | Tæl en spells ladninger op/ned (Magic Stone: brug en sten). |
| `/api/spell_duration` | POST | Tæl en aktiv utility-spells (kategori F) resterende varighed op/ned. |
| `/api/spell_mode` | POST | Skift en aktiv spells angrebs-tilstand (Produce Flame: nærkamp ⇄ kastet). |
| `/api/spells` | POST | — |
| `/api/spells_known` | POST | Lær eller glem et spell på en spontan casters kendte liste (sorcerer/bard). |

## Blueprint `summon`

Fil(er): `routes_summon.py`

| Rute | Metode | Hvad den gør |
|---|---|---|
| `/api/summon` | POST | Kast et summonet væsen (Summon Nature's Ally ELLER Summon Monster). |
| `/api/summon_dismiss` | POST | Afskedig et spontant summonet væsen (fjern ref'en fra summons-listen). |
| `/api/summon_hp` | POST | Justér HP for ÉT væsen i et summon (identificeret af SNA-slot + væsen-index). |
| `/api/summon_rounds` | POST | Tæl et summons resterende runder op/ned (varighed = 1 runde/casterniveau). |
