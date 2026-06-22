# BRIEF: Refaktorering — del store filer op efter ansvar

**Mål:** Tre filer har samlet for mange ansvar, og effekt-wiring er duplikeret.
Skær dem op i fokuserede moduler — UDEN at ændre adfærd. Hver fase skal rendere
**byte-identisk** output (regression-gate nedenfor), så det er ren omflytning af kode.

**Status i dag (faktiske størrelser):**
- `sources/character.py` ≈ 1.700 linjer — blander 5 ansvar: dataklasser ·
  fil-persistens · beregninger · statisk referencedata (racer/sprog/feats) ·
  effekt-motor.
- `sources/app.py` ≈ 1.300 linjer — Flask-routes + API + en "gud-funktion"
  `karakter()` der bygger ét kæmpe context-dict + effekt-view-hjælpere.
- `sources/templates/character.html` ≈ 3.200 linjer — HTML + inline CSS + en hel
  JS-app i ét `<script>`.
- **Duplikering:** `companion.py: collect_companion_effects` er næsten en kopi af
  `app.py: _collect_active_effects`. Rettes ét sted, glemmes det andet → bug-risiko.

**Det der IKKE skal røres** (det er sundt): `db.py`, `importer.py`, `dice.py`,
`data/*.yaml`, selve effekt-MOTOREN (resolve_modifiers m.fl.), companion-BEREGNINGEN
(advance_companion), og princippet "gem aldrig beregnede totaler — udled ved render".

---

## Kerneidé: façade-mønster → nul ændringer i kald-steder

Næsten al kode kalder `import character as char_module` og `char_module.X(...)`.
For at undgå at røre hundredvis af kald-steder (og dermed risiko) bruger vi en
**façade**: koden flyttes til nye moduler, og `character.py` re-eksporterer de
offentlige navne, så `char_module.save_total`, `char_module.AbilityScores` osv.
fortsat virker uændret.

```python
# character.py efter opdeling — tynd façade:
from models import AbilityScores, Skill, Attack, InventoryItem, Character
from persistence import load_character, save_character, write_character_file, ...
from rules import modifier, save_total, attack_total, armor_class, ...
from effects import resolve_modifiers, effective_ability_scores, con_temp_hp, ...
from refdata import race_data, class_languages, feat_prereq_unmet, ...
```

Så kan kald-steder migreres til de direkte moduler SENERE, i ro — eller aldrig.

---

## Foreslået modul-opdeling (sources/)

| Nyt modul | Indhold (flyttes FRA character.py med mindre andet står) |
|---|---|
| `models.py` | Dataklasserne: `AbilityScores`, `Skill`, `Attack`, `InventoryItem`, `Character` + `validate_character_data` |
| `persistence.py` | `load_character`, `save_character`, `write_character_file`, `restore_snapshot`, `snapshot_dir`, `list_snapshots`, `_write_snapshot`, `_atomic_write_bytes`, `_serialize_inventory_item`, `_serialize_attack`, `SNAPSHOT_KEEP` |
| `rules.py` | Beregninger: `modifier`, `skill_total`, `save_total`, `attack_total`, `grapple_total`, `initiative_total`, `armor_class`, synergier, `carry_limits`/`encumbrance*`, `xp_*`, `spell_slots*`, `derive_attacks`, `spell_attack*`, størrelses-modifiers |
| `effects.py` | **Motor** (resolve_modifiers, _combine, effective_ability_scores, resolve_ac_bonuses, resolve_target, save/skill_effect_bonus, conditional_modifiers, con_temp_hp) **+ view-laget** (se Fase 1) |
| `refdata.py` | `_RACES`/`race_data`, sprog-funktioner, feat-prereq-parser, `WEAPON_CHOICE_FEATS`, klasse-skills/hit-die/skill-points, `spell_like_dc` (overvej: flyt racer/sprog HELT ud i `data/`) |

`character.py` bliver façaden. `app.py` beholder routes; effekt-view flyttes til
`effects.py`.

---

## Regression-gate (KRITISK — samme metode som virkede hele vejen)

Før hver fase: gem en baseline af alle karakterers renderede HTML. Efter: render
igen og kræv **byte-identisk** output. Refaktorering må aldrig ændre en byte.

```bash
cd sources
# baseline FØR:
DND_CHARACTERS_DIR=.local-characters python -c "
import app, hashlib
c=app.app.test_client()
for s in ['aelred','faelyn','tjorn']:
    open(f'/tmp/base_{s}.html','wb').write(c.get('/karakter/'+s).data)"
# … lav ændringen, kør importer hvis data rørt, så:
DND_CHARACTERS_DIR=.local-characters python -c "
import app
c=app.app.test_client()
for s in ['aelred','faelyn','tjorn']:
    assert c.get('/karakter/'+s).data == open(f'/tmp/base_{s}.html','rb').read(), s
print('REGRESSION PASS')"
```

Plus: `python -m pytest test_effects.py -q` skal blive ved at være grøn efter hver
fase (importerne i testen peger på `character`-façaden, så de skal stadig virke).

---

## Faseplan (lav risiko → højere; ét commit pr. fase)

### Fase 1 — Unificér effekt-view-laget (HØJEST værdi, fjerner duplikatet)
Saml det spredte/duplikerede effekt-view i `effects.py`:
- Flyt motoren (resolve_modifiers, effective_ability_scores, resolve_ac_bonuses,
  resolve_target, _combine, save/skill_effect_bonus, conditional_modifiers,
  con_temp_hp) fra `character.py` → `effects.py`. Re-eksportér via façaden.
- Flyt view-hjælperne fra `app.py` → `effects.py`: `collect_active_effects`,
  `ability_breakdown`, `stat_sources`, `delta_row`, `damage_bonus`,
  `collect_riders`, `temp_hp`/`temp_hp_from_modifiers`, `picker_catalogs`,
  `EFFECT_SCALING`. Gør `collect_active_effects` generisk (tag buffs+conditions+db),
  så **både `app.py` OG `companion.py` kalder den samme** — slet
  `companion.py: collect_companion_effects` (det duplikat).
- Verificér: byte-identisk render + grønne tests. Commit.

### Fase 2 — Træk persistens ud
- Flyt alt load/save/snapshot/atomar-skrivning til `persistence.py`. `character.py`
  re-eksporterer. Rent snit (ingen overlap med beregninger). Regression + commit.

### Fase 3 — Træk dataklasser + referencedata ud
- `models.py` (dataklasser + validate). `refdata.py` (racer/sprog/feat-prereqs/
  klassedata). Overvej at flytte `_RACES`/sprog HELT til `data/*.yaml` (det er jo
  data, ikke logik — passer til det eksisterende data-lag). Façade + regression + commit.

### Fase 4 — Træk beregninger ud + slank karakter()
- `rules.py` får alle rene beregninger. `character.py` er nu en tynd façade.
- Træk `app.py: karakter()`s view-model-bygning ud i en funktion (fx
  `build_character_view(char, db) -> dict`) i et passende modul, så route'en bliver
  tynd. Regression + commit.

### Fase 5 — (UDSKUDT, valgfrit) Template CSS/JS ud
- `character.html` er 3.200 linjer HTML+CSS+JS. **Begrænsning:** deploy overskriver
  `static/`, og CSS ligger bevidst inline af den grund (se CLAUDE.md). JS kan dog
  flyttes til en versioneret `static/`-fil HVIS upgrade-scriptet kopierer den med.
  Størst arbejde, lavest hastende — tag den til sidst eller drop den.

---

## Besluttet (skal IKKE spørges om igen)
1. **Façade-mønster**: `character.py` re-eksporterer; kald-steder ændres ikke i
   denne omgang. Migrering til direkte imports er en separat, senere oprydning.
2. **Byte-identisk regression-gate** efter hver fase. Refaktorering ændrer aldrig
   output. Hvis en byte ændrer sig, er det en fejl — find den, lav den ikke om til
   "feature".
3. **Rækkefølge**: Fase 1 først (fjerner den reelle duplikering/bug-risiko), så
   nedefra: persistens → models/refdata → rules/view → (template sidst/aldrig).
4. **Opdatér `flask-dnd-3.5/CLAUDE.md`s filkort** når moduler tilføjes, så det
   matcher virkeligheden (gør det i den fase hvor filen oprettes).
5. **Små godkendte snit, ikke big-bang.** Koden virker og er testdækket; der er
   ingen grund til en risikabel total-omskrivning.

---

## Hvorfor (kort, til Mikkel)
Hver fil bør have ÉT klart ansvar. Lige nu skal man læse 1.700 linjer for at finde
ud af hvordan en karakter GEMMES, fordi det ligger side om side med hvordan AC
BEREGNES og hvordan racer ser ud. Når de tre ting bor hver for sig, kan du åbne
`persistence.py` og se HELE gem-logikken på én skærm. Façaden gør at vi kan flytte
ting uden at røre de mange steder der kalder `char_module.…`, så hver fase er lille
og kan bevises identisk.

---

*Arbejdsdokument — ingen kode ændret. Slet briefet når refaktoreringen er færdig
(jf. tidligere BRIEF-filer). Beslutningerne ovenfor er låst, så faserne kan køre
uden flere spørgsmål.*
