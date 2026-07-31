# 0001: Gem aldrig beregnede tal

**Status:** gældende · **Besluttet:** juni 2026 (skrevet ned i `c72e9d9`, 21. juni)

## Problem

Et D&D 3.5-karakterark er næsten udelukkende afledte tal. En Fort-save er ikke
et tal man har — den er klassens basis + Con-modifier + item-bonusser + aktive
effekter, og hvert af de led kan ændre sig midt i en kamp.

Den nærliggende model er at gemme det færdige tal i karakterens fil, sådan som
et papirark gør det. Spørgsmålet var, om arket skulle gemme totaler eller kun
grunddata.

## Beslutning

Karakterens YAML-fil indeholder **kun grunddata** — 26 nøgler med basisværdier.
Alle totaler udledes ved hver visning af `rules`, `attacks`, `spells` og
`effects`. Der caches intet.

Princippet står i `rules.py`'s egen docstring, så det møder enhver der åbner
filen:

> Kerneprincip: gem aldrig beregnede totaler — udled dem fra base + udstyr +
> effekter ved hver render.

Det gælder også de sekundære væsner: for en companion, familiar eller summonet
væsen gemmes kun *hvilket* dyr, hvilket niveau og hvornår det blev tilkaldt.

## Forkastet

**At gemme beregnede totaler i karakterfilen.** To grunde:

1. **Hver regelændring ville kræve en migrering.** Rettes en formel, er alle
   gemte totaler forkerte indtil hver eneste karakterfil er skrevet om. Med
   afledte tal er alle karakterer rettet ved næste sideopdatering.
2. **Gemte totaler kan blive uenige med reglerne, uden at nogen opdager det.**
   En glemt opdatering giver ikke en fejlmeddelelse — den giver et forkert tal
   der ser rigtigt ud. Det opdages i bedste fald midt i en kamp.

Det andet punkt er det tungtvejende. Den slags fejl er stille, og en stille fejl
i et regelsystem er dyrere end en langsom beregning.

## Konsekvens

**For dig der arbejder i koden:**

- **Intet må caches.** Hvert kald til `/karakter/<navn>` regner alt forfra.
  Fristes du til at gemme et udregnet tal "bare lige her", bryder du princippet.
- **Regnefunktionerne skal være rene** — ingen I/O ud over det `db`-objekt der
  gives med som argument. Det er derfor regelmotoren kan testes uden at starte
  Flask, og derfor 702 tests kører på ~30 sekunder.
- **Effekter kaskaderer gratis.** `Bull's Strength` giver +4 Str, og til-hit,
  skade, Climb/Jump/Swim, bæreevne og muligvis AC følger med af sig selv. Intet
  af det skal vedligeholdes.
- **En udløbet effekt forsvinder af sig selv.** Der er ikke noget at rulle
  tilbage.

Prisen er reel, men lille: arket regnes på millisekunder, fordi referencedata
enten ligger indekseret i SQLite eller som dicts i hukommelsen.

Se [Regelmotor](../arkitektur/regelmotor.md) for hvordan de fire moduler deler
arbejdet, og [Dataflow](../arkitektur/dataflow.md) for vejen fra YAML til skærm.
