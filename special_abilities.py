"""Special-evner (natural abilities) for wild shape — opslag + overførsels-regler.

Ét ansvar: oversæt en forms rå special_attacks/special_qualities-fritekst til en
struktureret liste med art (Ex/Su/Sp) og forklaring, og afgør hvilke evner der
RENT FAKTISK kobles på druiden.

RAW (polymorph, jf. wild_shape.py): en almindelig (animal-)form giver KUN formens
Ex special *attacks* — ikke dens special qualities (scent, low-light vision) og
ikke Su/Sp-evner. En elemental-form (druide L16+) giver derimod ALT (Ex+Su+Sp);
formens feats håndteres separat i wild_shape.py.

Regel-DATA ejes af data/special_abilities.yaml (slås op via db); her bor kun
parsingen af fritekst + selve overførsels-logikken.
"""
import re

# Kort "udløses ved X"-tekst pr. rytter-type (vist under evnen i form-blokken).
# Selve rul-matematikken (ekstra angreb / bonus-skade) ligger i wild_shape.py.
RIDER_TRIGGERS = {
    "extra_attacks": "Ekstra angreb mens du holder fat (kræver grapple/charge først)",
    "two_hit": "Automatisk hvis begge angreb rammer samme mål",
    "on_charge": "Når du charger og rammer",
    "on_hit": "Når det udløsende angreb rammer",
    "on_grapple": "Automatisk når du vinder et grapple-check",
    "trample": "Full-round: løb hen over en mindre modstander (Reflex for halv)",
}


def _split_tokens(text: str | None) -> list[str]:
    """Split en fritekst-evneliste på topniveau-kommaer (ikke inde i parenteser).

    'Air mastery, whirlwind (Reflex DC 28)' → ['Air mastery', 'whirlwind (Reflex DC 28)']
    'Poison (Fort DC 14, 1d6 Con)'          → ['Poison (Fort DC 14, 1d6 Con)']  (kommaet er inde i parentes)
    """
    if not text:
        return []
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return [t for t in out if t]


def _slug(label: str) -> str:
    """Udled katalog-slug fra en evne-labels ledende navn.

    'rake 1d6+2' → 'rake' · 'Improved grab' → 'improved_grab' ·
    'Whirlwind (Reflex DC 28)' → 'whirlwind' · 'Low-light vision' → 'low_light_vision'.
    De form-specifikke tal/DC'er bliver i labelen og hører ikke med i slug'en.
    """
    head = re.split(r"[(;]", label, maxsplit=1)[0]   # stop ved parentes/semikolon
    words = []
    for w in head.split():
        if any(c.isdigit() for c in w):              # stop ved første tal-ord (skade/DC)
            break
        words.append(w)
    name = " ".join(words) or head
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def slug_from_label(label: str) -> str:
    """Offentlig indgang til navn→slug-normaliseringen.

    Genbruges af class_features.py (klasseevner) og companion.py (companion-feats/
    -specials), så de tre lag deler præcis samme regel: 'Weapon Focus (Bite)' →
    'weapon_focus', 'Improved Speed (+10 ft.)' → 'improved_speed'.
    """
    return _slug(label)


def ability_dc(hd: int, ability_mod: int) -> int:
    """Save-DC for en medfødt special-evne (SRD): 10 + ½ HD + ability-modifier.

    Gælder Ex/Su-evner hvis DC står som "X-based" (burn er Con-, whirlwind Str-
    baseret). Formlen er verificeret mod SRD-printet for alle væsner i kataloget
    der har en markeret dc_ability — se test_special_ability_dc.py.
    """
    return 10 + hd // 2 + ability_mod


def _retarget_dc(label: str, new_dc: int) -> str:
    """Skriv en ny DC ind i et fritekst-evne-token (kun selve tallet ændres).

    'Burn (1d4 fire, Reflex DC 11)' → 'Burn (1d4 fire, Reflex DC 13)'.
    Skade-terninger og resten af teksten røres ikke — kun tallet efter "DC".
    """
    return re.sub(r"(DC\s*)(\d+)", lambda m: f"{m.group(1)}{new_dc}", label,
                  count=1, flags=re.IGNORECASE)


def _entry(token: str, source: str, db, hd: int | None = None,
           scores=None) -> dict:
    """Byg én struktureret evne ud fra et fritekst-token (beriget fra kataloget).

    Er BÅDE hd og scores givet, og har evnen en dc_ability i kataloget, bliver
    save-DC'en i labelen GENBEREGNET fra de (evt. buffede) ability scores. Uden
    dem vises DC'en præcis som skrevet i væsenets data — det rå SRD-print.
    """
    slug = _slug(token)
    rec = db.get_special_ability(slug) if slug else None
    rec = rec or {}
    label = token
    dc_ability = rec.get("dc_ability")
    dc = None
    if dc_ability and hd is not None and scores is not None:
        dc = ability_dc(hd, scores.modifier(dc_ability))
        label = _retarget_dc(label, dc)
    return {
        "slug": slug,
        "label": label,                              # form-specifik (beholder tal/DC)
        "name": rec.get("name") or token,
        "kind": rec.get("kind"),                     # ex | su | sp | None (ukendt)
        "category": rec.get("category"),
        "description": rec.get("description"),
        "buff_id": rec.get("buff_id"),
        "rider_type": rec.get("rider_type"),         # engangs-angrebsrytter (eller None)
        "rider_count": rec.get("rider_count"),
        "dc_ability": dc_ability,                    # str/con/… (None = fast DC)
        "dc": dc,                                    # genberegnet DC (None = ikke beregnet)
        "source": source,                            # 'attack' | 'quality'
    }


def describe_ability_list(text, source: str, db, hd: int | None = None,
                          scores=None) -> list:
    """Parse en fritekst-evneliste til strukturerede, katalog-berigede tokens.

    Genbruges af summon.py/companion for at gøre et væsens special_attacks/
    special_qualities klikbare: hvert token får {slug, label, description, kind, …}
    (samme form som gained/reference i resolve_form_abilities). Ukendte evner (ikke
    i kataloget) får description=None og vises som ren tekst uden tooltip.

    hd + scores (valgfri): væsenets hit dice og EFFEKTIVE ability scores. Gives de,
    genberegnes save-DC'er for evner med en dc_ability, så en buff der hæver Str/Con
    (Augment Summoning, Bull's Strength) også hæver DC'en — ellers ville statblokken
    vise en Con 14-krop med en Con 10-DC. Udelades de, er adfærden som før: DC'en
    står som skrevet i data.

    Til forskel fra resolve_form_abilities gælder INGEN polymorph-overførselsregel
    her — et summonet/companion-væsen ER selve skabningen og har alle sine evner.
    """
    return [_entry(tok, source, db, hd, scores) for tok in _split_tokens(text)]


def resolve_form_abilities(special_attacks, special_qualities, form_type, db) -> dict:
    """→ {'gained': [...], 'reference': [...]} for en wild-shapet form.

    gained    = evner der kobles på druiden i formen.
    reference = formens øvrige evner, vist gråt (fås ikke pr. RAW).

    form_type 'elemental' → alt kobles på; alt andet behandles som animal-form
    (kun Ex special attacks; ukendt art antages at være en Ex special attack).
    """
    elemental = (form_type or "animal") == "elemental"
    gained, reference = [], []

    def place(token: str, source: str):
        e = _entry(token, source, db)
        if elemental:
            keep = True
        elif source == "attack":
            keep = e["kind"] in (None, "ex")
        else:
            keep = False                             # special qualities overføres ikke
        (gained if keep else reference).append(e)

    for tok in _split_tokens(special_attacks):
        place(tok, "attack")
    for tok in _split_tokens(special_qualities):
        place(tok, "quality")
    return {"gained": gained, "reference": reference}
