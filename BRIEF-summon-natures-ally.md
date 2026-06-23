# BRIEF — Summon Nature's Ally (summonede væsner med egen fane)

Når en druide kaster **Summon Nature's Ally** (SNA) — enten fra et forberedt spell
eller **spontant** ved at ofre et andet forberedt spell — skal spilleren kunne
**vælge hvilket væsen** der summones. Væsenet får sin **egen fane** ligesom en
Animal Companion, og fanen **forsvinder igen, når SNA-spellet markeres "Brugt"**.
Har karakteren feat'en **Augment Summoning**, får væsenet +4 Str og +4 Con.

Til forskel fra spellcaster-briefen er dette **ikke et data-tungt klasse-arbejde** —
det er at **genbruge to mekanismer der allerede findes** og koble dem sammen, plus
ét nyt (afgrænset) datasæt: SNA-tabellen over summonbare væsner.

---

## ⚠️ FØRST: SRD-mappen — statblokke MÅ IKKE gættes

Samme regel som i `BRIEF-spellcasters.md`: `rules/srd-v3.5-md/` er **gitignored** og
et **separat git-repo** — den er IKKE i pakke-repoet. En web-session har den ikke.

**Klon SRD-repoet først, hvis den mangler** (public):
```bash
git clone https://github.com/olimot/srd-v3.5-md rules/srd-v3.5-md
```
Relevant kilde:
- Spell-teksten: `rules/srd-v3.5-md/spells/` (summon-nature-s-ally + Summon Nature's Ally-tabellen).
- Væsen-statblokke: SRD's monster-/dyre-sektioner (samme kilde som `animals.yaml` blev bootstrappet fra).

**Lykkes klonen IKKE: STOP og meld tilbage.** Forkerte statblokke (HP, AC, til-hit,
saves) ser korrekte ud og er næsten umulige at fange bagefter. Hele projektet er
bygget på at parse fra SRD-kilden; uden den er væsen-data ikke til at stole på.
Bedre at stoppe end at gætte. (Dette er den vigtigste enkeltregel i briefen.)

---

## Nuværende tilstand (verificeret i koden)

**Det der allerede findes og skal genbruges:**

- **Companion-mønstret = skabelonen.** `companion.py` regner et fuldt statblok ud fra
  et RÅ basis-dyr (`data/animals.yaml`) + en TYND reference på karakteren
  (`char.companion = {name, animal, hp_current, tricks, buffs, conditions}`).
  `build_companion(char, db)` renderer det; `app.py` viser en companion-fane
  `{% if companion %}` (character.html linje 594 + 766). Persistensen håndterer
  `companion_*`-opdateringer (persistence.py 386-416). **Et summonet væsen er det
  samme mønster — bare midlertidigt og uden niveau-avancement.**
- **Tre-tilstands-spells = fanens livscyklus.** `self_duration`-spells har tre
  tilstande: **Ledig / I brug / Brugt** via `char.spells_active` (app.py 754-775,
  endpoint `/api/spells` 1128-1181). Det matcher kravet 1:1:
  **kast SNA → spell "I brug" + fane dukker op → tryk "Brugt" → fane væk.**
- **Effekt-motoren kan lægge ability-bonusser på et væsen.** `companion.py` kører
  allerede `collect_active_effects` → `advance_companion(...)` og lader fx Bull's
  Strength kaskadere via `effective_ability_scores`. **Augment Summoning (+4 Str,
  +4 Con enhancement) modelleres som en buff på væsenet — ingen særlogik i
  beregningen.**
- **Feat'en findes:** `data/feats.yaml` → `augment_summoning` ("+4 enhancement bonus
  to Strength and Constitution for the duration"). Vi tjekker bare om karakteren har
  den (`char.feats`) og lægger buffen på.
- **SNA-spellsene findes:** `data/spells.yaml` → `summon_natures_ally_i` … `_ix`
  med `level_druid` sat. En druide kan altså allerede forberede og se dem på arket.

**Det der IKKE findes endnu (det vi skal bygge):**

- **SNA-væsen-tabellen.** `animals.yaml` har KUN de ~15 companion-dyr. Summon
  Nature's Ally-listen (niveau I-IX → bestemte væsner: porpoise, dire badger,
  dire wolf, hippogriff, elementaler Small→Elder osv.) findes **slet ikke**.
  Overlap med companion-dyr findes (dog, eagle, owl, wolf …) men listen er
  markant større. **Dette er den eneste større dataopgave.**
  → **Besluttet:** `animals.yaml` udvides til ét **delt væsen-katalog** (companion-
  OG summon-væsner) med et `companion_ok`-flag, frem for en separat fil. Se
  Arkitektur. Dette undgår dubletter af de overlappende væsner.
- **Statblok for et "almindeligt" væsen.** `companion.py` *avancerer* et dyr efter
  druideniveau. Et summonet væsen er FAST (en summonet wolf = bare en wolf på
  base_hd). Vi skal bruge en rå statblok-beregning UDEN companion-avancement.
- **Spontant kast (ofre et spell).** Druiden konverterer ethvert forberedt spell af
  samme/højere niveau til SNA (som cleric→cure). Findes ikke; skal hægtes på
  spell-tabbens "brugt"-flow.
- **`summons`-reference på karakteren** + persistens (spejler `companion`).

---

## Arkitektur — ny `summon.py`, parallelt med `companion.py`

For at holde filerne fokuserede (ét ansvar pr. fil) lægges beregningen i sit eget
modul. `character.py`/`companion.py` blandes IKKE med summon-logik.

```
data/animals.yaml            # DELT væsen-katalog: companion + summon, m. companion_ok  [udvid]
data/summon_lists.yaml       # SNA-niveau I..IX → [creature_ids]  (tabellen)   [NY]
summon.py                    # rå-væsen → renderet statblok (+ Augment)        [NY]
companion.py / app.py        # companion-vælger filtrerer på companion_ok      [udvid]
character.py / persistence   # tynd `summons`-reference på karakteren          [udvid]
app.py                       # kast/afvis-endpoints + render summon-fane(r)    [udvid]
templates/character.html     # summon-fane(r) + "Kast som SNA" + væsen-vælger  [udvid]
```

**Det delte katalog (`animals.yaml`):** filen er i forvejen kilden til companion-
basis-dyr, indlæst via `importer.py` → SQLite → `db.get_animal()`. Vi udvider den til
at rumme ALLE summonbare væsner og tilføjer ét flag pr. række:

```yaml
- id: wolf
  companion_ok: true     # tilbydes som animal companion (eksisterende dyr → true)
  ...
- id: dire_wolf
  companion_ok: false    # kun summonbar, ikke en companion-mulighed
  ...
```

Eksisterende felt-skema (`base_hd`, abilities, `natural_armor`, `attacks`/`skills`
som JSON, `feats`) bevares uændret — summon genbruger det samme. **Det eneste der
rører fungerende kode:** companion-vælgeren (generatoren + arket) skal filtrere på
`companion_ok` i stedet for "alle animals", så elementaler/dire-væsner ikke pludselig
kan vælges som companion. Lille, afgrænset ændring — ingen omskrivning af
`advance_companion`. (Note: kataloget rummer nu også ikke-dyr som elementaler; vi
beholder filnavnet `animals.yaml` for at undgå unødig churn i `db.py`/`importer.py`,
men en kommentar i toppen af filen forklarer at det nu er et generelt væsen-katalog.)

**Hvorfor eget modul (`summon.py`):** et summonet væsen er et selvstændigt sekundært
væsen med eget statblok — præcis samme begrundelse som `companion.py` fik sit eget
hjem. At lægge det i `character.py` ville blande to ansvar. `summon.py` genbruger de
rene byggeklodser fra `character.py` (`AbilityScores`, `armor_class`,
`size_mod_attack`, `effective_ability_scores`, save-helpers) og effekt-motoren fra
`effects.py` — ligesom `companion.py` gør.

**Den TYNDE reference** (gemmes i karakter-YAML, aldrig beregnede totaler):
```yaml
summons:                      # liste — kan være tom; ryddes når spell sættes "Brugt"
  - creature: dire_wolf       # id i animals.yaml (det delte katalog)
    spell_level: 3            # hvilket SNA-niveau (I=1 … IX=9)
    spell_index: 0            # hvilket slot/sacrifice det kom fra (kobler fane↔spell)
    count: 1                  # antal ens væsner (SNA II+: 1d3 osv.)
    hp_current: [37]          # HP pr. væsen
    augment: true             # snapshot: havde karakteren Augment Summoning ved kast
    buffs: []
    conditions: []
```

---

## Faser (hver kan committes for sig — ét commit pr. feature)

### Fase 0 — Data + delt katalog ✅ FÆRDIG (commit: SNA Fase 0)
Leveret og verificeret mod SRD (alle 26 væsner: HP, AC, til-hit, saves matcher 100%):
- **`animals.yaml`** udvidet til delt katalog: 14 companions + **26 nye summon-væsner
  for SNA I-III**, alle med `companion_ok: false`. (Konvention: feltet UDELADES på de
  14 eksisterende = companion-egnet; rørte derfor ikke gennemprøvet data.)
- **`data/summon_lists.yaml`**: SNA I/II/III → 8/13/11 væsen-id'er. Indlæses af
  `refdata.summon_creatures(spell_level)`.
- **`schema.sql`**: 4 nye nullable kolonner på `animals` (se "Datakontrakt" nedenfor).
  `db._animal_row` afkoder `good_saves`-JSON. `srd35.db` genbygget.
- **`app.py`** (~356): companion-vælgeren filtrerer på `companion_ok != 0`.
  Companion-generering uændret (verificeret: 14 egnede, summon-kun ekskluderet).

**Datakontrakt for summon (vigtigt for Fase 1 — summon.py SKAL respektere disse):**
Verifikationen viste, at companion-motoren IKKE kan genbruges råt: den hardkoder
¾ BAB, poor Will og d8. Derfor bærer kataloget nu nok data til korrekt beregning:
- `type` (NULL=animal | magical_beast | elemental | fey) → **BAB**: animal/elemental
  ¾·HD, magical_beast 1·HD, fey ½·HD.
- `hit_die` (NULL=8 | 10 magical beast | 6 fey) → **HP** = ⌊(hit_die+1)/2 · HD⌋ + Con·HD.
- `good_saves` (JSON; NULL = udled af type) → hvilke saves er "gode". Sat eksplicit
  på elementaler (luft/ild `["ref"]`, jord/vand `["fort"]`) og dire-dyr
  (`["fort","ref","will"]` — dire animals har god Will, modsat almindelige dyr).
- **Toughness (+3 HP):** companion-motoren modellerer det IKKE. Feat'en STÅR i
  dataen (fx dire_badger, ape, wolverine, snake_constrictor), så Fase 1 kan vælge at
  anvende den. Beslutning til Fase 1 — verifikationen forudsatte +3 pr. Toughness.
- Skade gemmes UDEN Str-bidrag (motoren lægger ×1,5/×1/×0,5 på); rider-skade
  (ild/gift) står som tekst i `special_attacks`.

**Kendt forenkling i dataen (noteret, ikke en fejl):** "enten/eller"-angreb (fx
crocodile bite *eller* tail slap) gemmes som ét primært angreb; alternativet står i
`special_attacks`. Octopus/squid "Arms (0)" gemmes med skade `"0"`.

### Fase 1 — `summon.py` statblok-motor ✅ FÆRDIG (commit: SNA Fase 1)
Leveret (45 tests grønne — 34 eksisterende + 11 nye):
- **`summon.py`** (eget modul, parallelt med `companion.py`). Offentligt API:
  - `build_summon(ref, db)` → renderet statblok for ÉN summon-instans, eller None.
    `ref` er den tynde reference (`creature`, `spell_level`, `spell_index`, `count`,
    `hp_current`-liste, `augment`, `buffs`, `conditions`).
  - `build_summons(refs, db)` → liste for alle aktive summons (bruges af Fase 3).
  - `build_summon_stat(animal, db, modifiers, riders)` → den rene beregning.
- FAST statblok (ingen avancement). Type-bevidst: `_bab` (magical_beast fuld /
  fey ½ / øvrige ¾), `_good_saves` (eksplicit data → ellers udledt af type), HP via
  `hit_die`, Toughness `+3` anvendt. Returnerer samme form som `build_companion`
  (hp_max, hp_current, ac, attacks, saves, skills, conditions, buffs …) → Fase 3
  kan genbruge companion-templaten.
- **Augment Summoning:** `_AUGMENT_MODIFIERS` (+4 Str/+4 Con, type enhancement)
  prependes til effekt-listen når `ref["augment"]`, og kaskaderer via
  `effective_ability_scores` — verificeret i test (HP +12, skade ×1,5 → +13, på
  dire_wolf). Ingen særlogik i selve beregningen.
- Effekter (buffs/tilstande) virker via samme `collect_active_effects`-motor som
  companion. `test_summon.py` dækker hver væsen-type + Augment + count/HP-klamp.

**Note til Fase 3:** Augment-flaget er et SNAPSHOT taget ved kast (om casteren havde
feat'en da), gemt i `ref["augment"]` — ikke slået op live. Fase 3 sætter det fra
`char.feats` når summon-entry oprettes.

### Fase 2 — Model + persistens ✅ FÆRDIG (commit: SNA Fase 2)
Leveret (46 tests grønne):
- **`models.py`**: nyt `Character.summons: list`-felt (tynde refs), parallelt med
  `companion`.
- **`persistence.py`**: indlæser `summons` fra YAML; gemmer via ÉN update-nøgle
  `summons` (hele listen ad gangen, som `inventory`/`buffs` — app-endpoints i Fase 3
  bygger den nye liste ved kast/“Brugt”/HP/effekt-ændring). `_serialize_summon`
  skriver kun rå data (creature, spell_level, spell_index, count, hp_current-liste,
  augment, name, buffs, conditions) — aldrig beregnede totaler; valgfrie felter kun
  når de afviger fra default.
- **Designvalg vs. brief:** valgte ÉN `summons`-nøgle frem for 5 granulære
  (`summon_add/remove/hp/...`). Enklere, matcher list-replacement-mønstret, og
  summons adresseres af `(spell_level, spell_index)` i app-laget.
- Test: round-trip (gem → genindlæs → byg; augment slår igennem; tom liste rydder).

### Fase 3 — UI *(kerne-featuren; delt i fire showbare bidder)*

Den største og mest UI-tunge fase. Rører `app.py` (render_character ~1035 +
spell-endpoints ~1128) og `templates/character.html` (3350 linjer: companion-fane
~766, spell-tab ~957, `effect_picker`-makro ~472, `showTab`-JS ~1640). Bidderne
bygger oven på hinanden, og hver kan vises kørende for sig.

**Kontrakt der binder fane↔spell:** en summon identificeres af `(spell_level,
spell_index)` = det SNA-slot der skabte den. Den lever, mens spellet er "I brug"
(`spells_active`), og fjernes når spellet sættes "Brugt" (eller tilbage til "Ledig").
`summon.build_summons(char.summons, db)` giver den renderede liste (samme form som
`build_companion`).

#### Fase 3a — Render summon-faner *(read-only; bevis layout + stats)*
- `render_character` (app.py ~1035): kald `summon.build_summons(char.summons, db)`
  og send `summons` til templaten ved siden af `companion`.
- `character.html`: tab-knap + tab-panel **pr. summon** (loop over `summons`), klonet
  fra companion-fanen (HP, AC, angreb, saves, special_qualities). Fane-titel fx
  "🐾 Dire Wolf ×3" eller "🐾 Small Fire Elemental". `showTab`-JS virker uændret.
- Antal>1: vis ét statblok + "Antal: N" + HP pr. væsen (liste).
- **Vises ved** at hånd-seede en `summons`-entry i en YAML og åbne arket. Ingen
  kast/fjern endnu — beviser at faner renderer korrekt for alle væsen-typer.

#### Fase 3b — Kast-flow *(opret summon)*
- Spell-tabben: på forberedte **SNA**-spells (id `summon_natures_ally_*`) en knap
  "Kast → vælg væsen". Picker viser `refdata.summon_creatures(level)` (navne slås op
  i kataloget); SNA II/III tillader også et antal.
- Nyt endpoint `POST /api/summon` (action=cast): sæt spellet "I brug" (genbrug
  `spells_active`-mekanikken fra `/api/spells`), append en `summons`-entry
  `{creature, spell_level, spell_index, count, augment, hp_current}`, gem hele
  `summons`-listen. **Augment-flag snapshottes** fra `char.feats` (har karakteren
  `augment_summoning`?) ved kast — ikke live.
- Efter svar: fane dukker op (reload eller dynamisk).

#### Fase 3c — Fjern-flow *(afvis ved "Brugt")*
- Når et SNA-spell skifter til "Brugt" (eller "Ledig"): fjern den `summons`-entry
  hvis `(spell_level, spell_index)` matcher → **fane forsvinder**.
- Hægtes på `spells_active`-tilstandsskiftet i `/api/spells` (når spellet er et
  SNA-spell), så "Brugt"-knappen brugeren allerede kender også rydder summon'en.
- **Vises:** kast (3b) → fane → tryk "Brugt" → fane væk. Hele MVP-loopet kører.

#### Fase 3d — Fane-interaktivitet *(HP + effekter pr. summon)*
- Rediger HP pr. væsen og brug `effect_picker`-makroen på summon-fanen (buffs/
  tilstande), spejlet fra companion-fanens HP/effekt-wiring (app.py
  `/api/companion_hp`, `/api/companion_*` + JS ~1559-1640).
- Skriver tilbage ved at gemme hele `summons`-listen (Fase 2's `summons`-nøgle) —
  app-endpointet finder entry'en på `(spell_level, spell_index)`, muterer den,
  gemmer listen.
- Augment + buffs kaskaderer allerede i `summon.py` (Fase 1) → ingen motor-arbejde.

### Fase 4 — UI: spontant kast (ofre et spell) *(udvidelse)*
- På et hvilket som helst forberedt spell af niveau ≥ N: handling "Ofre til Summon
  Nature's Ally N" (N = det ofrede spells niveau). Marker det ofrede slot "Brugt"
  og kør samme summon-flow som Fase 3 med SNA-niveau = N.

**Efter MVP (I-III virker ende-til-ende) — ren udvidelse, ingen ny arkitektur:**

### Fase 5 — Fuld multi-visning
- I dag: ét statblok + `count` + HP-liste (dækker bordet). Nu: vis hvert af de N
  ens væsner som individuelle statblokke i fanen (separat HP/effekter pr. individ).
  `summons`-referencen rummer allerede `count` + `hp_current`-liste, så det er en
  ren render-/UI-udvidelse oven på Fase 1-4.

### Fase 6 — Data-udvidelse til SNA I-V → I-IX
- Tilføj de resterende væsner til `animals.yaml` + `summon_lists.yaml` (I-V, derefter
  I-IX). **Ren data** parset fra SRD — ingen kodeændring, fordi motoren/UI'et er
  niveau-agnostisk. Verificér nye statblokke mod SRD som altid.

---

## Beslutninger (alle afgjort med Mikkel)

1. **Niveau-omfang:** Start med **SNA I-III** som komplet skive (Fase 0-4), udvid så
   til **I-V** og til sidst **alle I-IX** som ren data (Fase 6). Slutmålet er I-IX.
2. **Flere væsner:** **Ét statblok + `count` + HP-liste nu** (Fase 0-4); **fuld
   multi-individuel visning bagefter** (Fase 5), når MVP'en virker ende-til-ende.
3. **Væsen-katalog:** `animals.yaml` udvides til ét **delt katalog** med
   `companion_ok`-flag (gjort ordentligt fra starten). Se Arkitektur + Fase 0.

---

## Verifikation (samme metode som hidtil)
- Statblok-motor: `test_summon.py` + before/after-probe (Augment til/fra → korrekt
  +4 Str/Con-kaskade på HP og til-hit/skade).
- Ende-til-ende i browseren (Chrome DevTools, som hidtil): forbered SNA på en druide,
  kast → vælg væsen → fane dukker op med korrekt statblok → tryk Brugt → fane væk.
  Gentag for spontant kast. Tjek mod et SRD-verificeret statblok.

## Husk
- Klon SRD-repoet først (se øverst) — gæt ALDRIG statblokke.
- `srd35.db` genbygges (`python importer.py`) efter ændringer i `data/`-tabeller.
- Version-bump i `manifest.toml` før deploy.
- Ét commit pr. fase/feature.
