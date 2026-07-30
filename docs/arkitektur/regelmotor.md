# Regelmotor

## Kerneprincippet: gem aldrig et beregnet tal

Det står i `rules.py`'s egen docstring, og det er den vigtigste enkeltregel i
projektet:

> Gem aldrig beregnede totaler — udled dem fra base + udstyr + effekter ved hver
> render.

En karakters YAML-fil har 26 nøgler, og de indeholder **kun grunddata**:

```yaml
ability_scores: {str: 14, dex: 10, con: 13, int: 10, wis: 16, cha: 15}
saves:   {fortitude: 2, reflex: 0, will: 2}    # klassetabellens BASIS
combat:  {bab: 0, speed: 30}                   # BASE attack bonus
skills:  [{id: concentration, ranks: 4.0, misc: 0}]
```

!!! note "`fortitude: 2` er ikke din Fort-save"
    Det er *basisværdien* fra klassetabellen. Din faktiske Fort-save = 2
    + Con-modifier + effekter + item-bonusser, og den regnes ved hver visning.
    Samme for `bab: 0`, der bliver til til-hit sammen med Str/Dex, størrelse,
    våben-enchantment, TWF-straffe og aktive buffs.

### Hvad det køber

- Retter du en regel, er **alle** karakterer rettet ved næste sideopdatering.
  Der findes ingen gemte totaler der kan blive uenige med reglerne.
- Ingen migrering når en beregning ændres.
- En effekt der udløber, forsvinder af sig selv fra alle afledte tal — der er
  ikke noget at rulle tilbage.

### Hvad det koster

- Intet må caches. Hvert kald til `/karakter/<navn>` regner alt forfra.
- Beregningerne skal være hurtige, og de skal være **rene** (ingen I/O ud over
  det `db`-objekt der gives som argument).

I praksis er det billigt: arket regnes på millisekunder, fordi al referencedata
enten ligger i SQLite med indekserede id'er eller i dicts i hukommelsen.

## Arbejdsdelingen mellem de fire moduler

`rules.py` var oprindeligt én fil på 1.377 linjer med mange ansvar. Den er
udspaltet efter *hvad slags tal* der regnes:

| Modul | Linjer | Regner | Importerer |
|---|--:|---|---|
| `rules.py` | 313 | Skills, saves, AC, XP, bæreevne, spell slots, synergier | `models`, `refdata`, `attacks` |
| `attacks.py` | 666 | Til-hit, skade, våben-afledning, TWF, proficiency, monk | `models`, `refdata`, `magic_abilities` |
| `spells.py` | 587 | Skade-skalering, save-DC, slots, spell-afledte angreb | `models`, `refdata` |
| `effects.py` | 448 | Buffs/tilstande → modifiers der kaskaderer | `db`, `character` |

Bemærk hvad de **ikke** importerer: ingen af dem kender `app.py`, `db.py`
(bortset fra `effects`), templates eller HTTP. De tager tal ind og giver tal
tilbage. Det er derfor de kan testes uden at starte Flask.

### Én-vejs-afhængigheden mellem `rules` og `attacks`

`attacks.py` blev spaltet ud af `rules.py`, og retningen er bevidst holdt ren:

```
rules.py  ──importerer──>  attacks.py     (size_mod_attack til armor_class)
attacks.py ──importerer IKKE──>  rules.py
```

`attacks.py`'s egen docstring siger det direkte: *"Importerer kun models +
refdata (IKKE rules/items) — rules importerer til gengæld `size_mod_attack`
herfra til `armor_class` (én-vejs, ingen cyklus)."*

Det er mønstret at kende: **når du spalter en fil, vælg en retning og skriv den
ned.** Uden det valg ender to filer med at importere hinanden, og så er de i
praksis stadig én fil.

## Effekt-motoren

`effects.py` har to ansvar i samme emne, og det er derfor de er samlet: den
mekaniske motor (buff → modifier) og view-laget (hvad brugeren ser om aktive
effekter).

Effekterne **kaskaderer**, og det er hele grunden til at de bor i motoren og
ikke i templaten. Et eksempel: `Bull's Strength` giver +4 Str. Det ændrer ikke
kun Str-feltet, men også:

- til-hit med nærkampsvåben
- skade med nærkampsvåben
- Climb, Jump, Swim (Str-baserede skills)
- bæreevne → muligvis encumbrance-niveau → muligvis AC og max Dex

Fordi intet er gemt, følger alle fem konsekvenser automatisk af de +4. Havde
totalerne været gemt, skulle hver af dem opdateres — og én glemt ville være en
stille fejl der først opdages midt i en kamp.

51 effekter er defineret i `data/effects.yaml` som modifiers, ikke som kode.

## Sekundære væsner: samme princip, egne moduler

Companion, familiar, summonede væsner og wild shape er **fire** moduler, ikke
ét. Det ser ud som duplikering, men reglerne er forskellige nok til at deling
ville sløre:

| Modul | Væsentype | Hvorfor eget modul |
|---|---|---|
| `companion.py` | Animal companion | Egen avancementtabel (druide-/ranger-niveau → bonus-HD, HP, AC, tricks) |
| `familiar.py` | Familiar | Genbruger companion-motoren, men afviger på tre SRD-punkter |
| `summon.py` | Summonet væsen | Fast statblok ved tilkald + Augment Summoning, plus antal og varighed |
| `wild_shape.py` | Formskift | Erstatter *karakterens egne* fysiske tal, ikke et separat væsen |

Alle fire følger kerneprincippet: intet gemmes, alt regnes ved visning. Det
gemte er kun *hvilket* dyr, hvilket niveau, og hvornår det blev tilkaldt.

`familiar.py` er det pædagogisk mest interessante eksempel på genbrug: den
importerer `advance_companion` fra `companion.py` og låner hele
statblok-udregningen (BAB, saves, AC, angreb) **uændret**. Kun tre SRD-afvigelser
er kodet i `familiar.py` selv:

- ingen bonus-HD — naturlig rustning og Int stiger efter **mesterens** niveau
- maks-HP = **halvdelen** af mesterens maks-HP, ikke afledt af familiarens HD
- specials akkumulerer (Alertness → share spells → deliver touch → speak with master)

Mester-bonussen (toad +3 HP, rat +2 Fort …) ligger i `data/familiars.yaml` og
lægges på *mesterens* ark i `character_view` — ikke i `familiar.py`. Det er den
rigtige grænse: familiar-modulet regner familiaren, ikke mesteren.

`wild_shape.py` er den modsatte ende: den merger druide og form. Fysiske scores
(Str/Dex/Con), størrelse, naturlig rustning, naturlige angreb og speed kommer fra
**formen**; mentale scores, HP, BAB, base-saves, feats og skills beholdes fra
**druiden**. Båret udstyr melder væk, så armor- og shield-bonus falder bort.

## Façade-mønstret i `character.py`

`character.py` indeholder næsten ingen logik. Den re-eksporterer navnene fra
`persistence`, `rules`, `attacks`, `spells`, `effects` og `items`:

```python
# app.py kan blive ved med at kalde det ét sted:
char_module.load_character(...)   # bor i persistence.py
char_module.armor_class(...)      # bor i rules.py
```

Formålet var at kunne spalte den oprindelige store fil **uden** at røre de
mange kaldesteder i `app.py` og i testene. Det virkede — men det efterlader en
skævhed værd at kende:

!!! note "Façaden skjuler hvor koden bor"
    Ser du `char_module.armor_class(...)` i `app.py`, fortæller det dig ikke at
    funktionen bor i `rules.py`. Docstringen i `character.py` nævner selv at
    migrering til direkte imports "kan ske senere, i ro". Indtil da: slå navnet
    op med `grep -rn "def armor_class" *.py` frem for at lede i `character.py`.

## Beregninger man skal kende

To ting virker som fejl, men er reglerne:

**Skade har et gulv på 1.** Et succesfuldt angreb giver mindst 1 i skade, også
hvis modifiers ville give 0 eller mindre. Det håndteres i rul-ruten med en
`min`-parameter, ikke i skade-formlen:

```python
minimum = request.args.get("min", type=int)
if minimum is not None and result["total"] < minimum:
    result["total"] = minimum
    result["floored"] = True
```

**HP kan gå over max.** Midlertidigt HP (`Virtue` m.fl.) og en toad-familiar
(+3 maks-HP efter SRD) hæver *loftet*, så `hp_current` kan overstige `hp_max`.
Loftet regnes i `/api/hp`:

```python
ceiling = char.hp_max + fam_hp + effects.temp_hp(char, db)
new_hp  = max(-20, min(ceiling, char.hp_current + delta))
```

Gulvet på −20 er ikke tilfældigt: under −10 er man død efter SRD, og de
resterende ti giver plads til at se *hvor* dødt det gik.
