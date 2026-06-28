# BRIEF — Split af `character.html`

`templates/character.html` er ~3.873 linjer / 195 KB og blander tre ansvar i én fil:
udseende (CSS), struktur (HTML) og opførsel (JS). Denne brief beskriver hvordan den
deles op, hvorfor det er lav risiko, og hvordan det verificeres.

---

## Udgangspunkt (målt)

| Blok | Linjer (ca.) | Jinja-udtryk | Skal hen |
|---|---|---|---|
| `<style>` (linje 7–472) | 465 | **0** | `static/character.css` (uændret) |
| HTML-body (473–1791) | 1.319 | 438 | **bliver** i `character.html` |
| `<script>` (1792–3871) | 2.079 | **48** | `static/character.js` (uden Jinja) + data-bro |

Nøglefund: de 48 Jinja-udtryk i JS'en er næsten alle **ren data-injektion** på formen
`const X = {{ data|tojson }};`. Det er ikke logik flettet sammen med Jinja — derfor
kan ~97 % af koden flyttes ordret.

---

## Målstruktur

```
sources/
├── static/                     ← NY mappe (Flask serverer den automatisk på {script_root}/static/)
│   ├── character.css           ← de 465 CSS-linjer, flyttet uændret
│   └── character.js            ← ~2.000 linjer JS-logik, nul Jinja
└── templates/
    └── character.html          ← HTML-body + lille inline "data-bro" + to <link>/<script>-tags
```

---

## Data-broen (kernen)

En lille inline `<script>` BLIVER i templaten og samler AL server-data ét sted, så
den eksterne `.js` (der ikke ser Jinja) kan læse den:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='character.css') }}">
...
<script>
  window.DND = {
    base: "{{ request.script_root }}",
    char: "{{ name }}",
    hpMax: {{ char.hp_max }},
    spellsUsed: {{ char.spells_used|tojson }},
    attacks: {{ attacks_json|tojson }},
    /* … alle 48 data-felter samlet her, inkl. companion-/summon-/spell-blokke … */
  };
</script>
<script src="{{ url_for('static', filename='character.js') }}"></script>
```

Øverst i `character.js` destruktureres broen, så resten af logikken er uændret:

```js
const { base, char, hpMax, attacks /* … */ } = window.DND;     // konstante
let { hpCurrent, spellsUsed, conditions /* … */ } = window.DND; // muterbare
// … resten af de ~2.000 linjer kopieres ind ordret …
```

De få `{% if companion %}` / `{% for %}`-blokke i JS'en bygger også kun
datastrukturer — de flyttes ind i `window.DND`-objektet (Jinja-løkken kører i
templaten, resultatet bliver almindelig JS-data i broen).

---

## YunoHost / deploy

- Flask serverer `sources/static/` automatisk; nginx proxyer hele `/dnd/` ned til
  appen, så `/dnd/static/character.js` rammer Flask. Ingen `conf/`-ændring nødvendig.
- Upgrade-scriptets `cp -r sources/.` tager `static/` med. Ingen manifest-ressourcer
  at tilføje.

---

## Rækkefølge (kan committes hver for sig)

1. **CSS ud** — flyt `<style>`-indholdet til `static/character.css`, indsæt `<link>`.
   Helt isoleret (0 Jinja). Eget commit.
2. **JS ud** — byg `window.DND`-broen, flyt logikken til `static/character.js`,
   destrukturér øverst. Eget commit.
3. **(Valgfrit, senere)** HTML-body'en (1.319 linjer) kan deles i Jinja-partials
   (`{% include %}` pr. fane). Separat, mindre opgave — ikke nødvendig nu.

---

## Verifikation

- Render templaten før/efter og diff det samlede output (HTML+CSS+JS) — funktionelt
  identisk.
- Browser-smoketjek af arket: HP, spells, inventory, companion, conditions/buffs.
- Husk version-bump i `manifest.toml` før deploy.

---

## Status

- [ ] CSS → `static/character.css`
- [ ] JS → `static/character.js` + data-bro
- [ ] (valgfrit) HTML-partials
