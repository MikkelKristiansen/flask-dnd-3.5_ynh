---
title: Eventyrets titel
subtitle: Et D&D 3.5 eventyr        # valgfri, ren metadata
author: Mikkel Kristiansen          # valgfri
party: [tjorn, faelyn]              # valgfri — PC-slugs; styrer statblokke i sidebjælken
---

<!-- ════════════════ FORMAT-CHEAT-SHEET (denne kommentar vises ikke) ════════════════
  #  = SCENE                     ##  = mærket SEKTION i scenen
  Scene-sektioner (## + nøgleord):
     ## Monstre            encounter-roster:  * Nx @type[id]
     ## Handling           spilteksten (read-aloud + DM-noter)
     ## Rum: <titel>       under-lokation i en dungeon (kompakte felt-punkter)
  Bokse (blokcitat):
     >  →  LÆS HØJT som standard (det spillerne hører)
     >  **Fed caption:** valgfri titel/betingelse på en boks
  Entities inline @type[id] — ÅBENT type-sæt, klikbare i visningen:
     Bestiar (fra database, R2):     @monster[kriger]  @npc[mordekain]
     Dokument-lokale (virker i R1):  @brev[..]  @kort[..]  @gaade[..]  @faelde[..]
  # Dokumenter (appendiks, sidst) — DEFINÉR handouts/kort ÉN gang, referér i scener:
     ## Brev: <titel>   →  > brev-tekst           →  refereres som @brev[titel-slug]
     ## Kort: <titel>   →  ![alt](media/fil.png)  →  refereres som @kort[titel-slug]
     (id = slug af titlen: "Brev fra Mordekain" → brev-fra-mordekain)
  Roster-linje:   * 1x @monster[kriger]        (Nx = antal; feeder kamp-modulet)
  DM-noter:       almindelig tekst uden >      (læses IKKE højt)
  Billede inline: ![alt](media/fil.png)        (engangs-billede uden reference)
════════════════════════════════════════════════════════════════════════════════ -->


# Scene-titel

@kort[scene-kort]

## Monstre
* 1x @monster[kriger]
* 2x @monster[tyv]

## Handling

> Read-aloud: det spillerne hører når scenen åbner. Kan gå over flere linjer,
> så længe hver linje starter med >.

DM-note i almindelig tekst: baggrund, regler, hvad-nu-hvis. Læses ikke højt.
Nævn gerne @npc[mordekain] eller @monster[skelet] inline — så bliver ordet
klikbart i læse-visningen.

Vagthunden laver et Listen-tjek (+4 mod DC 15) for at opdage de ubudne gæster.

> **Hvis tjek klares:** Jeres hund knurrer, og I hører fodtrin udenfor døren.

> **Hvis tjek misses:** En økse hamrer ind i jeres egetræsdør!

De tilfangetagne bærer en seddel: @brev[brev-fra-skurken].


# Dungeon-scene

@kort[kaelderkort]

## Rum: Indgang
* **Fælder:** 1x @faelde[spydfaelde] på døren
* **Beskrivelse:** Rodet rum belyst med en enkelt fakkel.

## Rum: Opbevaringsrum
* **Monstre:** 1x @monster[tyv], 1x @monster[kriger]
* **Beskrivelse:** Vagtrum. @monster[tyv] står bag bordene (+1 AC, cover);
  @monster[kriger] ved indgangen. Kan afsøges for 10 sølv.


# Dokumenter

<!-- Definér breve, kort og andre handouts ÉN gang her; referér dem i scenerne
     med @brev[id] / @kort[id]. Fordi de bor i selve dokumentet, slås de op
     allerede i R1 (modsat @monster/@npc, der kommer fra bestiariet i R2). -->

## Brev: Brev fra skurken
> Til mine lejesvende. Bring mig bogen til den gamle bro ved fuldmåne... — M.

## Kort: Scene-kort
![Byen](media/by.png)

## Kort: Kælderkort
![Kælderen](media/kaelder.png)
