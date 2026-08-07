#!/usr/bin/env python3
"""Generér wand-rækker til data/magic_items.yaml ud fra SRD's wand-tabel.

Engangsværktøj (samme rolle som gen_control_e_rows.py) — committes, så det er
muligt at genskabe/udvide rækkerne uden at gætte. Skriver til stdout; blokken
klippes ind i data/magic_items.yaml i wand-sektionen.

    .venv/bin/python scripts/parse_wands.py > /tmp/wands.yaml

SRD siger eksplicit at wands ikke har beskrivelser ("simply storage devices for
spells"), så alt bortset fra den danske description udledes mekanisk af tabellen:

  caster_level = price_gp / (750 * spell_level)     # spell_level 0 -> 375 gp = CL 1
  aura         = styrke(CL) + spellets skole
  charges_max  = 50, slot = null, modifiers = '[]'  # altid, for alle wands

Går divisionen ikke op i et helt tal, er enten spell-niveauet eller prisen læst
forkert — scriptet fejler hellere højlydt end at skrive et forkert CL.
"""
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

SRD = Path.home() / "lokalmidler/Projekter/srd-v3.5-md/magic-items/magic-items-iv-scrolls-staffs-and-wands.md"
REPO = Path(__file__).resolve().parent.parent

# SRD-navn -> spell_id. data/spells.yaml er inkonsistent omkring genitiv-s, så et
# maskinelt slug rammer forbi her. Der er ingen fremmednøgle på magic_items.spell_id:
# et forkert id fejler TAVST (wanden tæller ned uden at kaste noget).
ALIAS = {
    "bear's endurance": "bear_endurance",     # uden s
    "bull's strength": "bull_strength",       # uden s
    "cat's grace": "cat_grace",               # uden s
    "owl's wisdom": "owl_wisdom",             # uden s
    "eagle's splendor": "eagles_splendor",    # MED s
    "fox's cunning": "foxs_cunning",          # MED s
    "greater invisibility": "invisibility_greater",  # omvendt ordstilling
}

# Spells der ikke findes i data/spells.yaml. Wanden kommer med som rent opslag:
# character_view.py:56 sætter kun consumable når der er et spell_id, så 🧪 Brug-
# knappen vises ikke — genstanden opfører sig som en almindelig ting i tasken.
# Visningsnavn og skole kan så ikke slås op i spells.yaml; de står her, så navnet
# og auraen bliver rigtige. (restoration_lesser findes, men det er et ANDET spell
# end SRD's restoration.)
MANGLER_SPELL = {
    "chaos hammer": ("Chaos Hammer", "Evocation"),
    "holy smite": ("Holy Smite", "Evocation"),
    "order's wrath": ("Order’s Wrath", "Evocation"),
    "unholy blight": ("Unholy Blight", "Evocation"),
    "searing light": ("Searing Light", "Evocation"),
    "restoration": ("Restoration", "Conjuration"),
}

# SRD-fodnoter: materialkomponenter lagt oveni prisen, så prisformlen rammer forbi.
# Restoration 21.000 + 5.000, Stoneskin 21.000 + 12.500 — begge CL 7.
CL_OVERRIDE = {"restoration": 7, "stoneskin": 7}

# Danske beskrivelser. Kort og konkret: hvad wanden gør ved bordet. For de fem uden
# spell_id skal teksten være fyldig nok til at DM'en kan køre effekten manuelt.
BESKRIVELSE = {
    "acid arrow": "Ranged touch: 2d4 syreskade nu og igen hvert af de følgende runder (1 runde pr. 3 CL).",
    "bear's endurance": "Aktivér for +4 enhancement til Constitution i 1 min./CL.",
    "bull's strength": "Aktivér for +4 enhancement til Strength i 1 min./CL.",
    "burning hands": "Vifte af ild i en 15-fods kegle: 1d4 pr. CL (maks. 5d4) ildskade, Ref halv.",
    "call lightning": "Kald ét lyn pr. runde ned fra himlen: 3d6 elektricitetsskade, Ref halv. Kræver frit udsyn til himlen.",
    "cat's grace": "Aktivér for +4 enhancement til Dexterity i 1 min./CL.",
    "chaos hammer": "Kaos-eksplosion i en 20-fods sfære: 1d8 pr. 2 CL (maks. 5d8) mod lovlige væsner, plus 1 runde forvirret. Will halv + ingen forvirring. Kaotiske væsner rammes ikke.",
    "charm animal": "Charmér ét dyr: det ser dig som en betroet ven i 1 time pr. CL. Will negerer.",
    "charm monster": "Charmér ét levende væsen uanset type: det ser dig som en betroet ven i 1 dag pr. CL. Will negerer.",
    "charm person": "Charmér én humanoid: den ser dig som en betroet ven i 1 time pr. CL. Will negerer.",
    "color spray": "Farvekegle på 15 fod: bevidstløs, forblindet og lamslået efter HD. Will negerer.",
    "contagion": "Melee touch: offeret pådrager sig en sygdom efter dit valg, uden inkubationstid. Fort negerer.",
    "cure critical wounds": "Aktivér for at helbrede 4d8+CL skade ved berøring.",
    "cure light wounds": "Aktivér for at helbrede 1d8+1 skade.",
    "cure moderate wounds": "Aktivér for at helbrede 2d8+CL skade ved berøring.",
    "cure serious wounds": "Aktivér for at helbrede 3d8+CL skade ved berøring.",
    "darkness": "Slukker alt lys i en 20-fods radius om en berørt genstand: skyggefuldt, i 10 min./CL.",
    "daylight": "Berørt genstand lyser som dagslys i 60 fods radius i 10 min./CL.",
    "delay poison": "Berørt væsen er immun over for giftens virkning i 1 time pr. CL. Fjerner ikke giften — udskyder den.",
    "detect magic": "Afsøg en 60-fods kegle for magiske auraer: styrke og skole efter 3 runders koncentration.",
    "detect secret doors": "Afsøg en 60-fods kegle for skjulte døre og rum i op til 3 runders koncentration.",
    "dimensional anchor": "Ranged touch: låser målet fast i planet i 1 min./CL — ingen teleport, blink eller planeskift.",
    "dispel magic": "Ophæv magi: slå 1d20 + CL (maks. +10) mod 11 + modstanderens CL, pr. effekt.",
    "eagle's splendor": "Aktivér for +4 enhancement til Charisma i 1 min./CL.",
    "enlarge person": "Berørt humanoid vokser en størrelseskategori i 1 min./CL: +2 Str, -2 Dex, -1 på angreb og AC.",
    "false life": "Giver dig 1d10+CL (maks. +10) midlertidige hitpoints i 1 time pr. CL.",
    "fear": "30-fods kegle: alle væsner flygter panisk i 1 runde pr. CL. Will negerer (rystede i 1 runde i stedet).",
    "fireball": "Eksplosion i en 20-fods radius på op til lang afstand: 1d6 pr. CL (maks. 10d6) ildskade, Ref halv.",
    "fox's cunning": "Aktivér for +4 enhancement til Intelligence i 1 min./CL.",
    "ghoul touch": "Melee touch: offeret lammes i 1d6+2 runder og udsender en kvalmende stank. Fort negerer.",
    "greater invisibility": "Berørt væsen bliver usynligt i 1 runde pr. CL — og forbliver det selv ved angreb.",
    "hold person": "Lammer én humanoid i 1 runde pr. CL. Will negerer, ny redning hver runde.",
    "holy smite": "Hellig eksplosion i en 20-fods sfære: 1d8 pr. 2 CL (maks. 5d8) mod onde væsner, plus 1 runde blændet. Will halv + ingen blænding. Gode væsner rammes ikke.",
    "ice storm": "Hagl over en 20-fods cylinder: 3d6 stumpskade + 2d6 kuldeskade, ingen redning. Halverer bevægelse i området.",
    "inflict critical wounds": "Melee touch: 4d8+CL negativ energi-skade. Will halv. Helbreder udøde.",
    "invisibility": "Berørt væsen bliver usynligt i 1 min./CL — bryder ved angreb.",
    "keen edge": "Fordobler et skærende våbens trusselsområde i 10 min./CL. Stacker ikke med Improved Critical.",
    "knock": "Åbner én låst, spærret eller fastkilet dør, kiste eller lås på afstand. Virker ikke på arcane lock uden CL-tjek.",
    "levitate": "Berørt væsen eller genstand svæver lodret op og ned, 20 fod pr. runde, i 10 min./CL.",
    "light": "Berørt genstand lyser som en fakkel (20 fods radius) i 10 min./CL.",
    "lightning bolt": "Lynstråle 120 fod frem: 1d6 pr. CL (maks. 10d6) elektricitetsskade til alle i linjen, Ref halv.",
    "magic missile": "Peg og aktivér: affyr én missil for 1d4+1 kraftskade (rammer automatisk).",
    "major image": "Illusion med lyd, lugt og varme, som du kan styre ved at koncentrere dig. Will afslører ved undersøgelse.",
    "mirror image": "1d4+1 pr. 3 CL (maks. 8) spejlbilleder omgiver dig i 1 min./CL og opsuger angreb.",
    "neutralize poison": "Fjerner al gift i et berørt væsen eller gør en portion gift ufarlig, permanent.",
    "order's wrath": "Lovens kraft i en 20-fods terning: 1d8 pr. 2 CL (maks. 5d8) mod kaotiske væsner, plus 1 runde omtåget. Will halv. Lovlige væsner rammes ikke.",
    "owl's wisdom": "Aktivér for +4 enhancement til Wisdom i 1 min./CL.",
    "poison": "Melee touch: 1d10 Con nu og igen efter 1 minut. Fort negerer begge gange.",
    "polymorph": "Forvandler et villigt væsen til en anden skabning (op til CL HD) i 1 min./CL. Beholder mentale evner og hitpoints.",
    "ray of enfeeblement": "Ranged touch: 1d6+1 pr. 2 CL (maks. +5) Strength-straf i 1 min./CL. Kan ikke sænke Str under 1.",
    "restoration": "Fjerner permanent evnetab, negative niveauer og udmattelse. Kræver 100 gp diamantstøv pr. brug.",
    "searing light": "Ranged touch: 1d8 pr. 2 CL (maks. 5d8) skade. Mod udøde 1d6 pr. CL, mod lys-sårbare 1d8 pr. CL.",
    "shatter": "Sprænger skøre genstande i en 5-fods sfære, eller én genstand på op til 1 pund pr. CL. Will negerer.",
    "shocking grasp": "Melee touch: 1d6 pr. CL (maks. 5d6) elektricitetsskade. +3 på angrebet mod mål i metalrustning.",
    "silence": "Total stilhed i en 20-fods radius i 1 runde pr. CL — ingen verbale komponenter, ingen lyd ud eller ind.",
    "slow": "Ét væsen pr. CL bevæger sig og handler halvt så hurtigt i 1 runde pr. CL: -1 angreb, AC og Ref. Will negerer.",
    "stoneskin": "Berørt væsen får skadereduktion 10/adamantine, indtil 10 point pr. CL er absorberet (maks. 150). Kræver 250 gp diamantstøv pr. brug.",
    "suggestion": "Plant et fornuftigt klingende forslag hos ét væsen i 1 time pr. CL. Will negerer.",
    "summon monster i": "Tilkalder ét væsen fra SM I-listen; det kæmper for dig i 1 runde pr. CL.",
    "summon monster ii": "Tilkalder ét væsen fra SM II-listen; det kæmper for dig i 1 runde pr. CL.",
    "summon monster iii": "Tilkalder ét væsen fra SM III-listen; det kæmper for dig i 1 runde pr. CL.",
    "summon monster iv": "Tilkalder ét væsen fra SM IV-listen; det kæmper for dig i 1 runde pr. CL.",
    "unholy blight": "Vanhellig eksplosion i en 20-fods sfære: 1d8 pr. 2 CL (maks. 5d8) mod gode væsner, plus 1 runde kvalm. Will halv. Onde væsner rammes ikke.",
    "wall of fire": "Ildmur, 20 fod lang pr. CL: 2d6+CL skade ved gennemgang, 2d4 inden for 10 fod. Varer koncentration + 1 runde pr. CL.",
    "wall of ice": "Ismur eller -kuppel, 1 tomme tyk pr. CL. Skal hugges igennem (3 hp pr. tomme pr. CL).",
    "web": "Klæbrigt spind fylder en 20-fods radius i 10 min./CL. Ref negerer, ellers fastholdt; Str- eller Escape Artist-tjek for at slippe fri.",
}


def hent_tabelrækker() -> list[tuple[str, int | None, int]]:
    """(spell-navn, heightened-niveau eller None, pris_i_gp) pr. række i wand-tabellen.

    Fire rækker er heightened-varianter ("Charm person, heightened (3rd-level
    spell)"). Mål-niveauet står i halen efter kursiven og SKAL bruges: prisformlen
    regner med det hævede niveau, ikke spellets eget.
    """
    tekst = SRD.read_text(encoding="utf-8")
    tabel = tekst.split("## Wands")[1].split("## Wand Descriptions")[0]
    # Restoration og Stoneskin har <sup>1</sup>-fodnoter mellem navn og pris, så
    # mellemrummet mellem </i> og <td> skal være frit (.*?), ikke tomt.
    mønster = r"<i>([^<]+)</i>(.*?)</td><td>([\d,]+) gp</td>"
    ud = []
    for navn, hale, pris in re.findall(mønster, tabel):
        ht = None
        if "heightened" in hale:
            m = re.search(r"\((\d+)(?:st|nd|rd|th)[- ]level", hale)
            if not m:
                sys.exit(f"FEJL: heightened uden niveau i {navn!r} / {hale!r}")
            ht = int(m.group(1))
        ud.append((navn.strip().rstrip(","), ht, int(pris.replace(",", ""))))
    return ud


def niveau_og_cl(spell: dict, pris_gp: int) -> tuple[int, int]:
    """Find det (spell_level, caster_level) SRD prissatte wanden efter.

    Prisen er spell_level × caster_level × 750 gp, men *hvilket* spell-niveau er
    ikke givet: Suggestion er bard 2 og wizard 3, og SRD regner med wizard-3
    (11.250 = 3 × 5 × 750). Så prøv hvert klasseniveau spellet har, og behold dem
    hvor divisionen går op OG det resulterende CL er lovligt — mindste caster
    level for et spell af niveau n er 2n-1. Er der flere, vinder det laveste CL.
    """
    klasser = ("wizard", "cleric", "druid", "bard", "ranger", "paladin")
    niveauer = {spell.get(f"level_{k}") for k in klasser} - {None}
    if not niveauer:
        raise ValueError(f"{spell['id']}: intet klasseniveau i spells.yaml")

    kandidater = []
    for sl in sorted(niveauer):
        nævner = 750 * sl if sl > 0 else 375
        if pris_gp % nævner:
            continue
        cl = pris_gp // nævner
        if cl >= max(1, 2 * sl - 1):
            kandidater.append((cl, sl))
    if not kandidater:
        # spells.yaml har ikke nødvendigvis alle klasser: daylight står som wizard 3,
        # men er også bard/paladin 2, og SRD prissatte wanden efter 2. Prisen er den
        # autoritative kilde, så fald tilbage til at prøve alle lovlige spell-niveauer.
        for sl in range(0, 5):
            nævner = 750 * sl if sl > 0 else 375
            if pris_gp % nævner:
                continue
            cl = pris_gp // nævner
            if cl >= max(1, 2 * sl - 1):
                kandidater.append((cl, sl))
        if kandidater:
            cl, sl = min(kandidater)
            print(f"  ⓘ {spell['id']}: klasseniveau gættet til {sl} ud fra prisen "
                  f"({pris_gp} gp → CL {cl}); spells.yaml har kun {sorted(niveauer)}",
                  file=sys.stderr)
            return sl, cl
        raise ValueError(
            f"{spell['id']}: {pris_gp} gp passer ikke til noget niveau i {sorted(niveauer)}"
        )
    cl, sl = min(kandidater)
    return sl, cl


def aura(cl: int, skole: str) -> str:
    """SRD's aura-trappe: CL 1-5 faint, 6-11 moderate, 12-20 strong."""
    styrke = "Faint" if cl <= 5 else ("Moderate" if cl <= 11 else "Strong")
    return f"{styrke} {skole.split('[')[0].strip().lower()}"


def slug(tekst: str) -> str:
    """Slug uden apostrof-hul: "Order's Wrath" -> orders_wrath, ikke order_s_wrath."""
    return re.sub(r"[^a-z0-9]+", "_", tekst.lower().replace("’", "").replace("'", "")).strip("_")


def main() -> None:
    yaml = YAML(typ="safe")
    spells = {s["id"]: s for s in yaml.load((REPO / "data/spells.yaml").open())}
    ved_navn = {s["name"].lower().replace("’", "'"): s for s in spells.values()}

    poster: list[tuple[str, str, list[str]]] = []   # (sortérnavn, id, yaml-linjer)
    set_ider: set[str] = set()
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

    for navn, heightened, pris_gp in hent_tabelrækker():
        # "Magic missile (5th)" -> grundnavn + eksplicit CL fra parentesen
        grundnavn = re.sub(r"\s*\(\d+(st|nd|rd|th)\)", "", navn).strip()
        nøgle = grundnavn.lower().replace("’", "'")

        spell = None
        if nøgle in MANGLER_SPELL:
            sid = None
            visningsnavn, skole = MANGLER_SPELL[nøgle]
        else:
            sid = ALIAS.get(nøgle) or slug(grundnavn)
            spell = spells.get(sid) or ved_navn.get(nøgle)
            if spell is None:
                sys.exit(f"FEJL: intet spell for {grundnavn!r} (prøvede {sid!r})")
            sid = spell["id"]
            # Navnet tages fra spells.yaml, ikke fra SRD-tabellen: tabellen bruger
            # sætnings-kapitalisering ("Cure light wounds"), katalogets øvrige
            # genstande Title Case ("Wand of Cure Light Wounds").
            visningsnavn, skole = spell["name"], spell["school"]

        # caster_level: udled af prisen, med SRD-fodnoterne som undtagelse.
        if nøgle in CL_OVERRIDE:
            cl = CL_OVERRIDE[nøgle]
        elif heightened:
            # Prisen følger det HÆVEDE niveau, ikke spellets eget.
            if pris_gp % (750 * heightened):
                sys.exit(f"FEJL: heightened {grundnavn} {pris_gp} gp går ikke op")
            cl = pris_gp // (750 * heightened)
        elif spell is None:
            # Uden spell-række kender vi ikke niveauet; alle seks er 4.-niveau-
            # spells i SRD, og CL står i navnets parentes hvor den afviger.
            m = re.search(r"\((\d+)(?:st|nd|rd|th)\)", navn)
            cl = int(m.group(1)) if m else pris_gp // (750 * 4)
        else:
            try:
                _, cl = niveau_og_cl(spell, pris_gp)
            except ValueError as e:
                sys.exit(f"FEJL: {grundnavn}: {e}")

        # id: grundvarianten beholder sit korte navn (så de to eksisterende wands
        # bevarer deres id'er); højere CL og heightened får suffiks.
        basis = f"wand_of_{sid or slug(visningsnavn)}"
        if heightened:
            wid = f"{basis}_heightened_{ordinal[heightened]}"
            suffiks = f" (heightened {ordinal[heightened]})"
        elif basis in set_ider:
            wid, suffiks = f"{basis}_cl{cl}", f" (CL {cl})"
        else:
            wid, suffiks = basis, ""
        if wid in set_ider:
            sys.exit(f"FEJL: dublet-id {wid}")
        set_ider.add(wid)

        beskrivelse = BESKRIVELSE.get(nøgle)
        if not beskrivelse:
            sys.exit(f"FEJL: ingen dansk beskrivelse for {grundnavn!r}")

        linjer = [
            f"- id: {wid}",
            f"  name: Wand of {visningsnavn}{suffiks}",
            "  category: wand",
            "  slot: null",
            f"  price_cp: {pris_gp * 100}",
            f"  caster_level: {cl}",
            f"  aura: {aura(cl, skole)}",
            "  weight: 0",
            "  modifiers: '[]'",
            f"  spell_id: {sid}" if sid
            else "  spell_id: null   # TODO: spellet mangler i data/spells.yaml",
            "  charges_max: 50",
            f'  description: "{beskrivelse}"',
        ]
        poster.append((f"{visningsnavn} {cl:02d}", wid, linjer))

    # Alfabetisk (og CL-stigende inden for samme spell) — nemmest at slå op i.
    for _, _, linjer in sorted(poster):
        print("\n".join(linjer))
    print(f"\n# {len(set_ider)} wands", file=sys.stderr)


if __name__ == "__main__":
    main()
