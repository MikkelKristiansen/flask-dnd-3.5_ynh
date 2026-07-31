# Værktøj

Egne værktøjer i repoet: scripts til data-arbejde, og en Emacs-integration til
at skrive eventyr.

---

## `scripts/`

Alle køres fra repo-roden med venv'ens interpreter.

### `gen_docs.py` — genererer referencesiderne

Bygger [Datamodel](../arkitektur/datamodel.md) og [Ruter](../arkitektur/ruter.md)
ud af koden selv.

!!! danger "Skal køre med APPENS `.venv`, ikke `.venv-docs`"
    Den læser ruterne ud af `app.url_map` — det kørende systems sandhed, frem
    for regex over `@route`-dekoratorer — og har derfor brug for flask og
    ruamel.

    `docs/build.sh` kalder den automatisk og **fejler højlydt** hvis appens
    venv mangler. `docs/serve.sh` springer generering over.

De genererede sider har et `<!-- GENERERET … REDIGÉR IKKE -->`-banner. Ret
kilden i stedet: kolonne-kommentarer i `data/schema.sql` og docstrings på
view-funktionerne.

### `lav-kodeord-hash.py` — scrypt-hashes til de to kodeord

```bash
.venv/bin/python scripts/lav-kodeord-hash.py
```

Tast de to kodeord (spiller og DM), og skriv de tre udskrevne linjer i
`/etc/flask_dnd.env` på serveren (`chmod 600`, ejet af root). Kodeordene læses
med `getpass`, så de **hverken vises på skærmen eller havner i
shell-historikken**. Se [Drift › Adgangskontrol](../drift/index.md#adgangskontrol).

### `triage_spells.py` — klassificér spells deterministisk

Sorterer SRD-spells i mekanik-kategorierne A–G ud fra **strukturerede felter i
`data/spells.yaml`**, ikke ud fra prosa. Kører deterministisk og koster ingen
tokens. Formålet er at gøre ~90 % af sorteringen automatisk og **flage de
usikre**, så et menneske kun gennemgår dem.

!!! note "`data/spell_categories.yaml` er ikke driftsdata"
    Filen bruges **kun** af dette script — appen læser den aldrig. Den ligger i
    `data/` og ligner derfor noget appen bruger. Det gør den ikke.

### `triage_review_sheet.py` — review-arket til de usikre

Trækker kun `lav`-konfidens-spells ud af triagen og præsenterer dem kompakt med
et beskrivelses-uddrag. Genbruger `classify()` fra `triage_spells.py` og
indeholder **ingen egen logik** — de to kan ikke komme ud af trit.

Skriver til `briefs/spell-triage-review.md` (gitignoreret).

### `gen_control_e_rows.py` — spell_attacks for kontrol-spells

Genererer `spell_attacks`-rækker for kategori E-spells uden skade
(Charm, Hold, Dominate, Bane m.fl.): de rammer med en save-DC, men ruller ingen
skade. `save_type` og `save_effect` udledes **deterministisk** af det
`save`-felt der allerede står i `spells.yaml` — ingen SRD-genlæsning, intet
gætteri.

---

## `editor/` — Emacs-integration til eventyr

Eventyr skrives som markdown med `@type[id]`-referencer til bestiaret. Modulet
gør den skrivning støttet i stedet for at kræve opslag.

| Fil | Hvad |
|---|---|
| `dnd-adventure-mode.el` | major mode: font-lock, completion på `@monster[…]`, eldoc, flymake, snippets |
| `dnd-browse.el` | `M-x dnd-browse` — browser over 10 tabeller i `srd35.db` |
| `snippets/` | yasnippet-skabeloner |
| `CHEATSHEET.md` | installation, tastatur, reference-syntaks, fejlsøgning |

📖 **[`editor/CHEATSHEET.md`](https://github.com/MikkelKristiansen/flask-dnd-3.5_ynh/blob/main/editor/CHEATSHEET.md)**
er den fulde vejledning — installation i din init, tastaturgenveje,
`@type[id]`-syntaksen, snippets og fejlsøgning. Den gentages ikke her.

Kort: `dnd-browse` slår op i det seedede bestiar, så completion og eldoc viser
**de rækker der faktisk er i databasen** — ikke en håndholdt liste. Har du lige
tilføjet et monster (se [Opskrifter](opskrifter.md)), er det tilgængeligt efter
en reseed.
