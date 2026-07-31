# Beslutninger

Her ligger de valg der er truffet i projektet, og — vigtigere — **hvad der blev
forkastet og hvorfor**.

Formålet er snævert: at forhindre at et valg genåbnes om et år, fordi
begrundelsen er glemt. Koden viser *hvad* der blev gjort. Den viser aldrig hvad
der blev overvejet og valgt fra.

## Sådan læses en beslutning

Hver fil har fire afsnit: **Problem**, **Beslutning**, **Forkastet**,
**Konsekvens**. Afsnittet *Forkastet* er det vigtigste — det er der, værdien
ligger om et år.

Numrene er **stabile og genbruges aldrig**. Omgøres en beslutning senere, får
den nye sit eget nummer, og den gamle får `Status: afløst af NNNN` og bliver
stående. Historikken slettes ikke.

Er der intet forkastet, var det ikke en beslutning — så hører beskrivelsen
hjemme i [Arkitektur](../arkitektur/index.md) i stedet.

## Registret

| Nr. | Beslutning | Status | Kort |
|---|---|---|---|
| [0001](0001-gem-aldrig-beregnede-tal.md) | Gem aldrig beregnede tal | gældende | Karakterfilen har kun grunddata; alle totaler udledes ved hver visning |
| [0002](0002-flad-filstruktur.md) | Flad filstruktur i repo-roden | gældende | Ingen `src/`, ingen pakke-mapper — filerne skilles ad efter ansvar, ikke efter mappe |
| [0003](0003-databasen-er-genereret.md) | Databasen er genereret, ikke redigeret | gældende | `srd35.db` er en build-artefakt; `data/*.yaml` er kilden til sandheden |

!!! note "Registret vokser"
    Der er flere trufne valg end der står her — de destilleres fra
    arbejdsdokumenterne efterhånden. En beslutning skrives kun ned når der
    findes belæg for begrundelsen i kode, commit eller notat. Et gættet
    "hvorfor" er værre end ingenting, fordi det ser lige så troværdigt ud.
