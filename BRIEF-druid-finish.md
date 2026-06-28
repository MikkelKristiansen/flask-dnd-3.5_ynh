# BRIEF — Druid-finish (resten): Wild Shape-rest + SNA IV-IX

Planteformer er bygget (commit "Druid Wild Shape: planteformer"). Tilbage står ren
DATA: et par wild-shape-former + de store Summon Nature's Ally-lister. Motoren er
færdig — alt herunder er væsen-statblokke i `data/animals.yaml` + lister i
`data/summon_lists.yaml`. **Verificér hver statblok mod SRD** (`rules/srd-v3.5-md/
monsters/`), som vi altid har gjort — gæt aldrig på tal.

Husk efter dataændringer: `python importer.py` (genbyg srd35.db) + version-bump.

---

## Del A — Wild Shape, sidste rester (lille)

1. **Huge elementaler** (air/earth/fire/water, 16 HD) — bruges af både wild shape
   (lvl 20) og SNA VI. Følg formatet for de eksisterende `elemental_*_large` i
   animals.yaml. `good_saves` KRÆVES pr. element (luft/ild: `["ref"]`, jord/vand:
   `["fort"]`).
2. **Elementar-størrelses-nuance (valgfri korrekthed):** SRD giver huge elemental
   wild shape først ved druide-20, men `classes.yaml` → druid.wild_shape.sizes har
   `huge` fra 15, så en 16-HD huge elemental ville være tilgængelig fra lvl 16
   (HD ≤ level). Reelt edge case (kræver lvl 16+). Hvis det skal være helt SRD:
   indfør per-type størrelses-gating (elementar-størrelser adskilt fra dyre-
   størrelser) i wild_shape.py — ellers lad det ligge og notér det.

---

## Del B — SNA IV-IX (stor: ~35 nye statblokke)

Hver SNA-liste i `summon_lists.yaml` peger på id'er i `animals.yaml`. Nedenfor er
SRD-tabellen pr. niveau. ✓ = findes allerede; ✗ = skal tilføjes. Outsidere/genier/
sprites (`type: outsider`/`fey`) og dinosaurer (`type: animal`) — sæt korrekt
`type` (driver BAB) + `companion_ok: false`. ¹ = kun vand-miljø (spil-note, ikke
mekanisk håndhævet).

**SNA IV (4th):** brown_bear✓, crocodile_giant✓, deinonychus✓, dire_ape✓,
dire_boar✓, dire_wolverine✓, elemental_*_medium✓ (×4), shark_huge✓, viper_huge✓,
tiger✓ — mangler: ✗arrowhawk_juvenile, ✗salamander_flamebrother [NE],
✗sea_cat¹, ✗tojanida_juvenile¹, ✗unicorn [CG], ✗xorn_minor

**SNA V (5th):** elemental_*_large✓ (×4) — mangler: ✗arrowhawk_adult,
✗bear_polar, ✗dire_lion, ✗elasmosaurus¹, ✗griffon, ✗janni, ✗rhinoceros,
✗satyr_piping (satyr m. pipes — satyr findes på SNA III uden pipes), ✗snake_giant_constrictor,
✗nixie, ✗tojanida_adult¹, ✗whale_orca¹

**SNA VI (6th):** ✗dire_bear, ✗elemental_*_huge (×4 — se Del A), ✗elephant,
✗girallon, ✗megaraptor, ✗octopus_giant¹, ✗pixie, ✗salamander_average,
✗whale_baleen¹, ✗xorn_average

**SNA VII (7th):** ✗arrowhawk_elder, ✗dire_tiger, ✗elemental_*_greater (×4),
✗djinni, ✗invisible_stalker, ✗pixie_sleep (variant), ✗squid_giant¹,
✗triceratops, ✗tyrannosaurus, ✗whale_cachalot¹, ✗xorn_elder

**SNA VIII (8th):** ✗dire_shark¹, ✗roc, ✗salamander_noble, ✗tojanida_elder

**SNA IX (9th):** ✗elemental_*_elder (×4), ✗grig, ✗pixie_memory (variant),
✗unicorn_celestial_charger

### Praktiske noter
- **Pixie-varianter**: SRD lister pixie tre gange (uden/med sleep-arrows/med
  sleep+memory). Modellér som separate id'er ELLER ét id + en note — pixie-
  varianterne deler statblok. Pragmatisk: ét `pixie` + notér arrow-varianten.
- **Elementaler** (Huge/Greater/Elder ×4 elementer = 12 statblokke) er den største
  bidder. Statblokke i `rules/srd-v3.5-md/monsters/monsters-d-de.md` (Elemental).
- **Anbefalet rækkefølge**: elementaler først (12 stk, fast mønster) → så
  dyr/dinosaurer (nemme, ¾ BAB) → så outsidere/genier/sprites (1·HD BAB, SR/SLA
  som tekst). Hver SNA-liste kan committes for sig efterhånden som dens væsner er
  inde.
- Filtrér aldrig disse ind i companion-/wild-shape-vælgeren utilsigtet:
  `companion_ok: false`, og kun `type: animal/plant/elemental` er wild-shape-bare
  (outsidere/fey er hverken companion eller wild shape — kun SNA).

---

## Verifikation
- Generér/åbn en høj-niveau druide, kast SNA af hvert niveau, tjek væsen-listen er
  komplet og statblokkene (HP/AC/angreb) matcher SRD via summon.py-beregningen.
- Wild shape: huge elementaler synlige for lvl 20-druide.
- Tests i summon-stil (test_summon.py) for et par nye væsner pr. niveau.

## Status
- [x] Planteformer (Shambling Mound, Assassin Vine) — wild shape lvl 12
- [ ] Del A: huge elementaler (+ evt. størrelses-gating-nuance)
- [ ] Del B: SNA IV-rester + V + VI + VII + VIII + IX
