"""Dyreledsagerens inventar — hvad Varg bærer, og hvad han kan bære.

Ansvar: oversæt companion["inventory"] til viste rækker + vægt/bæreevne, og
afgør hvilken rustning der sidder på dyret (barding → AC). Intet gemmes; alt
udledes ved render, som resten af companion-laget.

Hvorfor en egen fil og ikke companion.py: den fil har ét klart ansvar — regn
dyrets statblok ud fra basisdyr + effektivt druideniveau. Ejerskab, vægt og
bæreevne er et andet ansvar, og de to har kun ét berøringspunkt (barding-AC'en,
som companion.py henter herfra). Samme opdeling som spell_view.py ud af
character_view.py.

To SRD-regler bor her, fordi de kun gælder dyr:

  Bæreevne: "Quadrupeds can carry heavier loads than bipeds can"
  (monsters-intro-a.md:85) → ×1,5 på alle tre grænser.

  Barding: rustning til et nonhumanoid dyr koster dobbelt (Medium) eller
  firdobbelt (Large) og vejer det samme hhv. det dobbelte
  (equipment.md:419, kolonnen "Nonhumanoid").
"""
import items as items_module
from models import InventoryItem


# Quadruped-multiplikator på bæreevnen. Alle vores companion-dyr med fire ben
# får den; de tobenede (fx hawk, owl) gør ikke.
QUADRUPED_CARRY_FACTOR = 1.5

# Dyr i animals.yaml der IKKE er firbenede. Hellere en kort undtagelsesliste end
# et nyt datafelt på alle rækker — SRD's regel er "fire or more motive limbs".
_BIPEDS = {"hawk", "owl", "eagle", "raven", "bat", "snake_viper_tiny",
           "snake_viper_small", "snake_viper_medium", "snake_constrictor"}

# Barding-multiplikatorer pr. størrelse: (pris, vægt). SRD's tabel for usædvanlige
# skabninger, kolonnen "Nonhumanoid" — en ANDEN kolonne end den humanoide, som
# items.weight_for_size/cost_for_size bruger til spillerkarakterer.
BARDING_MULTIPLIERS = {
    "tiny": (1.0, 0.1), "small": (2.0, 0.5), "medium": (2.0, 1.0),
    "large": (4.0, 2.0), "huge": (8.0, 5.0),
}


def is_quadruped(animal_id: str) -> bool:
    """Bærer dyret last som firbenet? Default ja — de fleste companions er det."""
    return (animal_id or "").lower() not in _BIPEDS


def carry_limits(str_score: int, size: str, animal_id: str) -> dict:
    """Dyrets bæregrænser i pund — som items.carry_limits, men ×1,5 for firbenede."""
    base = items_module.carry_limits(str_score, size)
    if not is_quadruped(animal_id):
        return base
    return {k: round(v * QUADRUPED_CARRY_FACTOR, 1) for k, v in base.items()}


def barding_multipliers(size: str) -> tuple[float, float]:
    """(pris-faktor, vægt-faktor) for barding i den størrelse. Ukendt → Medium."""
    return BARDING_MULTIPLIERS.get((size or "medium").lower(), (2.0, 1.0))


def barding_weight(record: dict, size: str) -> float:
    """Faktisk vægt af et stykke barding — basisvægten × størrelsens vægtfaktor."""
    return round(float(record.get("weight") or 0.0) * barding_multipliers(size)[1], 3)


def barding_modifier(record: dict, size: str) -> dict | None:
    """Barding som butiks-tilvalg — samme form som items.material_modifiers.

    Prisdeltaet er merprisen oven i den humanoide basispris: en Medium nonhumanoid
    betaler ×2, altså basisprisen én gang til. Skjolde kan ikke bardes.
    """
    if not record or record.get("type") == "shield":
        return None
    pris_faktor = barding_multipliers(size)[0]
    base = int(record.get("cost_cp") or 0)
    if not base or pris_faktor <= 1:
        return None
    return {"key": "barding", "label": f"Barding ({size})",
            "delta_cp": int(round(base * (pris_faktor - 1)))}


def _resolve(item: InventoryItem, db, size: str) -> dict:
    """Som items.resolve_item, men med barding-vægt for rustning på dyret.

    resolve_item skalerer efter den HUMANOIDE tabel (Large ×2, Small ×½). Et
    stykke barding følger nonhumanoid-kolonnen, så rustning regnes om her.
    """
    r = items_module.resolve_item(item, db, size)
    if r.get("source") == "armor" and r.get("record"):
        unit = barding_weight(r["record"], size)
        r["unit_weight"] = unit
        r["weight"] = round(unit * item.qty, 3)
    return r


def worn_armor(inventory: list[InventoryItem], db) -> dict | None:
    """Den rustning dyret HAR PÅ (state=worn), eller None.

    Kun én tæller — som for spillerkarakterer, hvor _enforce_armor_slots holder
    styr på det. Skjolde giver ikke mening på et dyr og springes over.
    """
    for item in inventory:
        if item.state != "worn" or not (item.ref or "").startswith("armor/"):
            continue
        rec = db.get_armor(item.ref.partition("/")[2])
        if rec and rec.get("type") != "shield":
            return rec
    return None


def build(companion: dict, db) -> dict:
    """Vargs udstyrs-visning: rækker, vægt, bæregrænser, belastning, advarsler.

    `companion` er den byggede statblok fra companion.build_companion (den kender
    dyrets effektive Str og størrelse), ikke den rå gemte dict.
    """
    raw = companion.get("inventory") or []
    inventory = [i if isinstance(i, InventoryItem) else InventoryItem(**i) for i in raw]
    size = companion.get("size") or "medium"
    animal_id = companion.get("animal_id") or ""
    str_score = (companion.get("abilities") or {}).get("str", 10)

    rækker, vægt = [], 0.0
    for idx, item in enumerate(inventory):
        r = _resolve(item, db, size)
        if r["carried"]:
            vægt += r["weight"]
        # Egen rækkebygger frem for character_view._inv_row: den fil importerer
        # companion (cirkulær import), og Vargs rækker har ikke brug for våben-
        # felterne (off_hand, mighty, str_mult) — et dyr svinger ikke våben.
        rækker.append({
            "index": idx,
            "name": r["name"],
            "weight": r["unit_weight"],
            "total_weight": r["weight"],
            "qty": item.qty,
            "state": item.state,
            "notes": item.notes,
            "ref": item.ref,
            "is_armor": r.get("source") == "armor",
            "carried": r["carried"],
        })

    grænser = carry_limits(str_score, size, animal_id)
    belastning = items_module.encumbrance_level(str_score, vægt, size)
    if is_quadruped(animal_id):
        # encumbrance_level kender ikke quadruped-faktoren; afgør ud fra grænserne.
        belastning = ("Light" if vægt <= grænser["light"]
                      else "Medium" if vægt <= grænser["medium"]
                      else "Heavy" if vægt <= grænser["heavy"] else "Overloaded")

    rustning = worn_armor(inventory, db)
    # SRD equipment.md:613: "A barded animal cannot be used to carry any load
    # other than the rider and normal saddlebags." Vi ADVARER frem for at spærre
    # — hvor grænsen går for "saddeltasker" er et bordvalg, ikke et regnestykke.
    last = round(vægt - (barding_weight(rustning, size) if rustning else 0), 1)
    advarsler = []
    if rustning and last > 0:
        navn = companion.get("name") or "Dyret"
        advarsler.append(
            f"{navn} bærer {last:g} lb ud over sin barding. SRD: et dyr i barding "
            f"kan kun bære rytter og almindelige saddeltasker.")
    if belastning in ("Heavy", "Overloaded"):
        advarsler.append(
            f"Belastning: {belastning.lower()} — {vægt:g} lb af "
            f"{grænser['light']:g} lb let last.")

    return {
        "rows": rækker,
        "weight": round(vægt, 1),
        "limits": grænser,
        "enc": belastning,
        "quadruped": is_quadruped(animal_id),
        "armor": rustning,
        "warnings": advarsler,
    }
