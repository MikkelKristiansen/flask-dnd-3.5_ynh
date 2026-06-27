# BRIEF — Udstyrs-slots + two-weapon fighting (TWF)

Status: **planlagt, ikke bygget.** Skrevet 27. jun 2026 til en kommende session.

## Problemet (det Mikkel observerede)

1. **Man kan bære flere rustninger på én gang.** I inventaret kan flere armor-poster
   stå som `state: worn` samtidig (fx både Leather og Padded "BÅRET"). Det giver ikke
   mening — RAW bærer man én body-rustning + (evt.) ét skjold.
2. **Man kan "wielde" vilkårligt mange våben uden konsekvens.** Tjørn kan stå med både
   Quarterstaff og Sickle wielded, og hvert wielded våben bliver til et fuldt angreb
   uden straf. RAW: to våben (two-weapon fighting) giver **straf på alle angreb**, og
   man har kun to hænder.

Mål: udstyr skal afspejle reglerne — kun lovlige kombinationer giver lovlige tal, og
two-weapon fighting skal regne straffene korrekt (bl.a. til rangerens to-våben-stil).

## Nuværende kode-adfærd (kilde til sandheden lige nu)

- `sources/rules.py`
  - `INVENTORY_STATES = {"wielded","worn","backpack","stored","dropped"}` (~l.428).
  - `equipped_armor(inventory, db)` (~l.592): tager **første** worn body-armor (light/
    medium/heavy) og **første** worn shield — resten ignoreres *mekanisk*, men UI'en
    lader dig stadig markere flere som worn (= forvirrende, vægt tæller dem alle med).
  - `derive_attacks(inventory, db, size, weapon_prof, allowed_weapons)` (~l.408): laver
    **ét angreb pr. wielded våben**. Ingen hånd-begrænsning, ingen TWF-straf. `str_mult`
    pr. post bruges (1 / 1.5 ved two_handed / default fra weapon_class). `not_proficient`
    giver allerede −4 (fra proficiency-featuren).
- `sources/models.py` — `InventoryItem` har allerede relevante felter: `state`,
  `two_handed: bool`, `str_mult: float|None`, `bonus: int`. **Mangler**: en måde at
  markere et våben som off-hand (til TWF), og hvor mange hænder et våben kræver.
- `sources/app.py` — `/api/inventory` (set state via item-modal), `_inv_row` (JSON til
  visning), angrebs-render (~l.860: `derive_attacks(...)` → `attack_rows`).
- `sources/templates/character.html` — item-modal har en `state`-dropdown (wielded/worn/
  backpack/stored/dropped); inventar-listen viser BÅRET/I HÅNDEN-badges; Angreb-sektion.

## Reglerne (SRD 3.5 — verificeret)

### Rustning
- Én body-rustning ad gangen + (evt.) ét skjold. (`armor.yaml type`: light/medium/heavy
  vs. shield.)

### Wielding / hænder
- En Medium-skabning har 2 hænder. Våben koster hænder efter `weapon_class`:
  light/one-handed = 1 hånd, two-handed = 2 hænder. Et skjold optager også en hånd
  (men giver ikke angreb). Tower shield = 2 hænder reelt (special).
- To-håndsvåben + andet våben/skjold er ikke muligt samtidig.

### Two-weapon fighting (combat-ii §513, Table: TWF Penalties)
Når man wielder et ekstra våben i off-hand: ét ekstra angreb med off-hand, MEN straf på
**alle** angreb:

| Omstændighed | Primær hånd | Off-hand |
|---|---|---|
| Normal | −6 | −10 |
| Off-hand-våben er light | −4 | −8 |
| Two-Weapon Fighting-feat | −4 | −4 |
| Off-hand light **og** TWF-feat | −2 | −2 |

- Off-hand-angreb tilføjer kun **½ Str** til skade (primær får fuld Str; et to-håndsvåben
  ville ellers give ×1,5 — gælder ikke ved TWF).
- **Double weapons** (fx quarterstaff): kan bruges som to våben; off-hand-enden tæller
  som et light våben mht. straffene.
- Feats: **Improved Two-Weapon Fighting** (ekstra off-hand-angreb ved −5), **Greater
  Two-Weapon Fighting** (tredje off-hand-angreb ved −10). De findes pt. næppe i
  `data/feats.yaml` — tjek og tilføj ved behov (som proficiency-feat-opfølgningen).

### Ranger Combat Style (character-classes-ii §157) — vigtigt for Mikkel
- L2: vælg **archery** eller **two-weapon combat**. Two-weapon ⇒ behandles som havende
  **Two-Weapon Fighting**-feat (uden Dex 15-krav). Archery ⇒ **Rapid Shot**.
- L6: Improved (TWF: Improved Two-Weapon Fighting / archery: Manyshot).
- L11: Mastery (TWF: Greater Two-Weapon Fighting / archery: Improved Precise Shot).
- **Kun i light/no armor** — mister stilen i medium/heavy.
- Dvs. ranger-data i `classes.yaml` skal kunne bære et combat-style-valg, og det skal
  fodre TWF-beregningen + armor-betingelsen.

## Foreslået design (til godkendelse i næste session)

**A. Udstyrs-slots (rustning):**
- Håndhæv én worn body-armor + ét worn shield. To muligheder (spørg Mikkel):
  - *Blød:* tillad flere worn, men vis en advarsel (som proficiency/druid-metal) +
    brug kun den første. Genbrug advarsels-bjælke-mønsteret.
  - *Hård:* når man sætter en post til `worn`, sæt automatisk den tidligere worn
    body-armor (hhv. shield) tilbage til `backpack`. Mest intuitivt, ingen ulovlig
    tilstand. **Anbefales** (passer til "kun lovlige kombinationer").
- Tower shield = 2 hænder (kan ikke kombineres med wielded våben i begge hænder).

**B. Hånd-budget for wielded våben:**
- Beregn forbrugte hænder af wielded våben (+ skjold). Overforbrug (>2) → advarsel
  (blød) eller bloker (hård). Genbrug samme valg som A.

**C. Two-weapon fighting i `derive_attacks`:**
- Identificér primær vs off-hand. Forslag: nyt felt `InventoryItem.off_hand: bool`
  (sat i item-modalen), ELLER: hvis præcis 2 én-hånds/light våben er wielded, behandl
  det andet som off-hand. Eksplicit flag er klarest.
- Beregn straf ud fra tabellen: off-hand light? + har TWF-feat (inkl. ranger-style)?
- Læg straffen på til-hit for **alle** wielded angreb (primær straf på primær, off-hand
  straf på off-hand). Off-hand skade = ½ Str.
- Double weapon (quarterstaff): tilbyd "brug som to våben" → to angreb, off-hand-enden
  som light. (Kataloget har `dmg_m: "1d6/1d6"` — `derive_attacks` splitter pt. på "/".)
- Marker straffen i UI (som "−4 uvant"-noten fra proficiency) så man ser hvorfor.

**D. Ranger combat style (kan være separat opfølgning):**
- `classes.yaml`: ranger får et `combat_style`-felt eller valg ved oprettelse/level 2.
- TWF-beregningen tjekker: har TWF-feat ELLER (ranger m. two-weapon style OG light/no
  armor). Improved/Greater ved L6/L11 → ekstra off-hand-angreb.

## Filer der skal røres (forventet)
- `sources/models.py` — `InventoryItem.off_hand` (+ evt. `hands`/double-weapon-flag).
- `sources/rules.py` — slot-validering (armor/shield/hænder); TWF-logik i
  `derive_attacks`; evt. helper `two_weapon_penalty(...)`.
- `sources/persistence.py` — load/serialiser nye felter.
- `sources/app.py` — håndhæv slots i `/api/inventory` (hård-variant); send hånd-/TWF-
  info til template; advarsler i kontekst.
- `sources/templates/character.html` — item-modal (off-hand-checkbox, evt.
  double-weapon), advarsler, angrebs-noter.
- `sources/data/classes.yaml` (+ feats.yaml) — ranger combat style; TWF-feats hvis de
  mangler.

## Åbne beslutninger til Mikkel
1. Blød (advarsel) vs. hård (auto-flyt/bloker) håndhævelse for rustning + hænder?
   (Anbefaling: hård for rustnings-slot, evt. blød for hænder.)
2. Off-hand: eksplicit checkbox vs. auto-gæt? (Anbefaling: eksplicit.)
3. Skal ranger combat style med i samme omgang, eller som separat opfølgning?
4. Double weapons (quarterstaff som to angreb) — med nu eller senere?

## Relaterede, allerede byggede mønstre at genbruge
- Advarsels-bjælke: proficiency (`prof_block`) + druid-metal (`druid_armor_block`).
- Angrebs-noter: `Attack.not_proficient` + "−4 uvant"-markør.
- `derive_attacks` (rules.py) er det centrale sted for angrebs-tal.
