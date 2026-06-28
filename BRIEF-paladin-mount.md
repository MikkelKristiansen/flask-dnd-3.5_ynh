# BRIEF — Paladin's Special Mount (fuld SRD)

Sidste del af Paladin-pakken. Smite Evil + Lay on Hands er bygget (commit
"Paladin: Smite Evil + Lay on Hands"). Mounten er den store del fordi den har sin
**egen** avancement (forskellig fra animal companion) og kræver nyt dyre-data.

Beslutning truffet: **fuld SRD-korrekt** (ikke genbrug af animal-companion-tabellen).

---

## Hvad SRD siger (character-classes-ii.md, "The Paladin's Mount")

- Fås ved **paladin-level 5**. Tilkald 1/dag, full-round; varer 2 timer/level; afsked
  som fri handling. Samme væsen hver gang. Dør den: ingen ny mount i 30 dage / til
  næste level (−1 på attack og våben-skade imens).
- Standard: **heavy warhorse** (Medium paladin) / **warpony** (Small paladin).
- Behandles som magical beast (men beholder dyrets HD/BAB/saves/skills/feats).

**Mount-avancementstabel** (≠ animal companion `_ADVANCEMENT` i companion.py):

| Paladin-level | Bonus HD | Natural Armor | Str | Int | Special |
|---|---|---|---|---|---|
| 5–7   | +2 | +4  | +1 | 6 | Empathic link, improved evasion, share spells, share saving throws |
| 8–10  | +4 | +6  | +2 | 7 | Improved speed (+10 ft.) |
| 11–14 | +6 | +8  | +3 | 8 | Command creatures of its kind |
| 15–20 | +8 | +10 | +4 | 9 | Spell resistance (= paladin-level + 5) |

- Bonus HD er d8, hver med Con-mod. BAB = som cleric af niveau = mountens HD
  (dvs. ¾ × HD — samme som companion-motoren allerede regner). God Fort+Ref,
  dårlig Will (treat as character whose level = HD).

---

## Hvad der mangler i data

`data/animals.yaml` har kun **heavy_horse** (3 HD, ikke kamp-trænet) og **pony**.
Mounten skal være en **heavy warhorse** / **warpony** (kamp-statblok fra SRD
monsters — Str 18, hove som primær-angreb + bid, combat-trænet). Tilføj:
- `heavy_warhorse` (Medium-paladinens standard)
- `warpony` (Small-paladinens standard)
Parse fra `rules/srd-v3.5-md/monsters/monsters-animals.md` (Horse-entry → Warhorse,
heavy). Sæt `companion_ok: 0` så de IKKE dukker op i druide/ranger-companion-vælgeren.

---

## Kode-ændringer (companion.py + app.py)

Genbrugsfladen er stor: companion-statblokken, tilkald/afsked (`/api/companion`),
HP (`/api/companion_hp`), tricks og hele ark-visningen kan genbruges. Det der skal
ændres er **avancementen** og **gating**:

1. **companion.py** — i dag er alt hængt op på `companion_effective_level` (druid/
   ranger) + `_ADVANCEMENT`. Mount har egen tabel. Renest: en separat
   `_MOUNT_ADVANCEMENT` + en gren i `advance_companion`/`build_companion` der vælger
   tabel ud fra om det er en mount (fx et flag på char.companion: `kind: "mount"`),
   ELLER et parallelt `build_mount`. Vurdér i koden hvad der duplikerer mindst.
   Specials (empathic link/improved evasion/command/SR) vises som tekst-labels
   (som companion-specials i dag), ikke fuld mekanik.
2. **app.py** — `can_summon_companion` / `companion_animals` gates på
   `companion_effective_level > 0` (0 for paladin). Tilføj paladin-gating fra
   level 5 og tilbyd kun heavy_warhorse/warpony. Tilkald-flowet (`/api/companion`
   action "summon"/"dismiss") kan ellers genbruges.
3. Mount-referencen på char.companion skal bære `kind: "mount"` så build vælger
   rette avancement. (Tjek at en paladin ikke samtidig kan have en druide-companion
   — ikke relevant, men gating skal være entydig.)

---

## Verifikation

- En level-5+ paladin kan tilkalde en heavy warhorse; statblok matcher SRD
  (HD = base+2, NA +4, Str +1, BAB ¾×HD, saves god/god/dårlig).
- Avancementen skifter ved 8/11/15.
- HP/tilkald/afsked virker via de eksisterende companion-ruter.
- Druide/ranger-companion uændret (regressions-tjek: tjorn/faelyn).
- Tests i companion-stil + version-bump i manifest.toml.

---

## Status — BYGGET 28. jun
- [x] heavy_warhorse + warpony i animals.yaml (companion_ok: false)
- [x] _MOUNT_ADVANCEMENT + delta-refaktor af advance_companion (deles af companion+mount)
      + build-gren på `kind: "mount"` i companion.py
- [x] paladin-gating (mount_eligible, fra lvl 5) + dyre-udvalg + kind-tag i app.py
- [x] tab/labels kind-aware (level_label, companion_noun, tricks skjult for mount)
- [x] tests (mount-avancement, gating, summon/dismiss) + version-bump

Specials vises som tekst-labels (akkumulerende), ikke fuld mekanik — som planlagt.
