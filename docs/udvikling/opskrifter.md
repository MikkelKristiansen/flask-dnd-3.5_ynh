# Opskrifter

Sådan udvider du appen med indhold. Hver opskrift er nummererede trin med de
faktiske kommandoer, og slutter med **hvor du ser resultatet**.

Alle opskrifterne herunder er gået igennem i praksis, ikke skrevet ud fra
koden.

---

## Først: hvilken vej går din nye ting?

Der er **to dataveje** fra `data/`, og valget bestemmer om en reseed er
nødvendig. Se [Dataflow](../arkitektur/dataflow.md) for mekanikken.

| | Vej 1 — gennem `srd35.db` | Vej 2 — direkte i RAM |
|---|---|---|
| Filer | `spells`, `monsters`, `weapons`, `traps`, `doors`, `effects`, `class_levels`, `magic_items`, `specific_items` … | `races`, `classes`, `starting_kits`, `spell_notes`, `summon_lists`, `creature_templates`, `combat_options` … |
| Indlæses af | `importer.py` (står i `TABLES`) | `refdata._load_yaml()` ved import |
| Efter en ændring | **reseed** (`importer.py`) | **kun genstart** |

!!! tip "Er du i tvivl, så kig i `importer.py`'s `TABLES`-liste"
    Står tabellen der, er det vej 1. Ellers vej 2.

---

## Tilføj et monster til bestiaret

1. **Find statblokken i SRD-kilden.** Brug `olimot/srd-v3.5-md` (klonet i
   `~/lokalmidler/Projekter/srd-v3.5-md/monsters/`). `realmshelps` har fejl.

   ```bash
   grep -n -A 40 "^## Krenshar" ~/lokalmidler/Projekter/srd-v3.5-md/monsters/monsters-k-l.md
   ```

2. **Tjek at den ikke allerede findes:**

   ```bash
   grep -n "^- id: krenshar" data/monsters.yaml
   ```

3. **Tilføj rækken i `data/monsters.yaml`.** Kopier feltrækkefølgen fra den
   sidste post i filen. Skriv den **trykte** statblok — ikke rå stats appen
   skal regne på. (`animals` er modsat: dér er det rå stats, fordi wild
   shape/companions regner videre på dem.)

4. **Reseed og verificér antallet steg:**

   ```bash
   .venv/bin/python importer.py
   ```

5. **Se det i UI'et.** Statblokken hentes af DM-modulet:

   ```
   /dm/api/catalog-statblock/monster/krenshar
   ```

   Ruten returnerer et **HTML-fragment**, ikke JSON — trods `api` i navnet.
   Bestiar-oversigten ligger på `/dm/bestiary/<eventyr>` og kræver altså et
   eventyr; katalog-ruten ovenfor gør ikke.

6. **Kør testene:** `.venv/bin/python -m pytest -q` → 702 passed.

!!! danger "`attacks` er NOT NULL"
    Har monsteret ingen angreb, skriv den **tomme JSON-liste**, ikke `NULL`:

    ```yaml
    attacks: '[]'
    ```

    Udelader du feltet, fejler seed'en. Det er den hyppigste fejl i
    monster-batches.

!!! note "Felter der må være tomme"
    `str` … `cha` må være `NULL` (fx undead uden Con), og `grapple` må være
    `NULL` når det ikke er relevant. `hp_max`, `ac`, `ac_touch`, `ac_flat`,
    `size`, `type` og `name` skal have værdi.

---

## Tilføj en spell

En spell er op til **tre** filer. Kun den første er obligatorisk.

1. **`data/spells.yaml`** — selve spellen. Niveau-felterne er én pr. klasse
   (`level_wizard: 1`), og de klasser der ikke får spellen lades tomme.

2. **`data/spell_attacks.yaml`** — kun hvis spellen giver et angreb på arket.
   **0..n rækker pr. spell.** Skade udregnes som:

   ```
   base_damage + min(niveau*dmg_per_level/dmg_per_level_div, dmg_per_level_max) + dmg_bonus
   ```

   `kind` er `melee`, `ranged`, `melee_touch`, `ranged_touch`, `save` (område
   uden til-hit) eller `heal`. Skal spellen kunne skifte mellem to tilstande
   (Produce Flame: nærkamp **eller** kastet), giver du rækkerne samme
   `mode_group` — så bliver de ét angreb med en ⇄-knap, ikke to samtidige.

3. **`data/spell_notes.yaml`** — valgfri visningsnote. Det er **vej 2**:

   !!! warning "spell_notes kræver ingen reseed"
       Filen læses af `refdata` ved import, ikke gennem databasen. Efter en
       ændring er det **kun** en genstart der skal til. Kører du `importer.py`,
       sker der ikke noget forkert — det er bare unødvendigt.

4. **Reseed** (for trin 1 og 2) og kør testene.

5. **Se det i UI'et:** åbn et karakterark for en klasse der har spellen, sæt
   den på "I brug", og se at angrebsrækken dukker op med den rigtige skade.

---

## Tilføj en fælde eller en dør

`data/traps.yaml` og `data/doors.yaml`. Begge er **trykte statblokke med
skalarer** — der er ingen beregning bag dem, så de er de enkleste at tilføje.

1. Tilføj rækken. 2. Reseed. 3. Verificér i DM-modulet.

Fælder og døre bruges af dungeon-rum og af brættet; en dør har HP og kan
angribes.

---

## Tilføj en magisk genstand

To tabeller, og forskellen er ikke selvindlysende:

| | `magic_items` | `specific_items` |
|---|---|---|
| Hvad | **Permanente bonusser** i et krops-slot | **Navngivne, færdige** våben/rustninger |
| Eksempel | `cloak_of_resistance_1` | `flame_tongue` |
| Nøglefelter | `slot`, `category` (wondrous/ring/rod/potion/scroll/wand) | `base_ref` (`weapons/longsword`), `enhancement`, `abilities` |
| Virker ved | båret item (`state=worn`) → modifiers gennem effekt-motoren | `base_ref` + `enhancement` + `abilities` → et fungerende inventar-item |

Kort sagt: **er det en bonus du har på dig, er det `magic_items`. Er det et
navngivent våben, er det `specific_items`.**

`specific_items.abilities` er en JSON-liste af `magic_abilities`-id'er, fx
`["flaming_burst"]` — angrebs-motoren wirer dem selv. Bespoke-effekter
(charge-skade, slay-on-crit) kan ikke wires og skrives som noter.

Forbrugsvarer (potions, scrolls) er `magic_items` med `spell_id` +
`charges_max`.

---

## Tilføj en effekt eller buff

`data/effects.yaml`. En effekt er **modifiers som data, ikke kode** — det er
hele pointen: du beskriver hvad der ændrer sig, og effekt-motoren lader det
kaskadere gennem alle afledte tal (AC, angreb, saves, skills).

Se [Regelmotor](../arkitektur/regelmotor.md) for hvordan kaskaden virker. Du
skal ikke skrive beregningen — kun modifieren.

---

## Tilføj en race eller klasse

!!! warning "Race og klasse er vej 2 — klasse-progression er vej 1"

    | Hvad | Fil | Efter ændring |
    |---|---|---|
    | Racen | `data/races.yaml` | genstart |
    | Klassen | `data/classes.yaml` | genstart |
    | Klassens niveau-tabel | `data/class_levels.yaml` | **reseed** |

`class_levels` er BAB, saves, HD og skill points pr. niveau. Du **appender
rækker** med `class: <navn>` — ingen schema-ændring nødvendig.

`races.yaml` og `classes.yaml` valideres ved app-start (`_load_records`), så en
YAML-tastefejl eller et manglende påkrævet felt fejler **højlydt ved opstart**
i stedet for at give stille forkert opførsel. Racer kræver mindst `size` og
`speed`.

---

## Tilføj en helt ny tabel

`importer.py` er **fuldstændig generisk**: kolonnerne læses ud af databasen
selv med `PRAGMA table_info` efter `schema.sql` er kørt. En ny tabel kræver
derfor **ingen ny indlæsningskode** — tre trin:

1. **`CREATE TABLE` i `data/schema.sql`**
2. **`data/<tabel>.yaml`** ved siden af
3. **Tabelnavnet i `TABLES`** i `importer.py`

!!! tip "Skriv en `--`-kommentar over hver kolonne"
    `scripts/gen_docs.py` trækker kommentarerne fra `schema.sql` med ud i
    [Datamodel](../arkitektur/datamodel.md). **En god kommentar i skemaet
    bliver automatisk til god dokumentation** — det er den billigste
    dokumentation i projektet.

    ```sql
    CREATE TABLE doors (
        id      TEXT PRIMARY KEY,
        hp      INTEGER NOT NULL,   -- døren kan angribes; 0 = brudt op
    ```

Rækkefølgen i `TABLES` betyder noget hvis en tabel refererer en anden.

---

## Efter enhver ændring i `data/`

```bash
.venv/bin/python importer.py && .venv/bin/python -m pytest -q
```

Se [Test](test.md) — særligt fælden med de 296 fejl, hvis du arbejder i en
frisk klon.
