"""magic_gear — ren overlay-motor for magiske våben/rustning/skjolde (SRD v3.5).

Ét ansvar: tag en BASE-genstand (en våben-/rustnings-række, som fra kataloget) og
en magisk enhancement-bonus, og returnér de afledte tal UI'et/DM'en skal bruge:
det magiske navn, kamp-modifikatorerne og den samlede markedspris.

Som `dm_encounter` er dette REN logik — ingen I/O, ingen DB, intet regel-opslag
udefra. Det gør motoren hermetisk testbar og neutral: den kan wires til BÅDE
karakter-butikken (catalog.py) og DM-modulet senere, uden at motoren ændres.

Præcedens: materiale-modifikatorer bor som kode i `items.material_modifiers` — magisk
enhancement bor tilsvarende her, ikke i en data-fil.

Kilde: SRD 'Magic Items II (Armor and Weapons)'.

NÆSTE LAG (ikke bygget endnu): special abilities (flaming/keen/frost på våben;
fortification/resistance på rustning). De prissættes som "effektiv bonus" (enhancement
+ sum af ability-bonusser, capped +10) ELLER et fast gp-tillæg — et ekstra `spec`-
argument oven på enhancement-bonussen her.
"""
from __future__ import annotations

# Højeste rene enhancement-bonus (special abilities kan senere give effektiv +10).
ENH_MAX = 5

# Masterwork-komponentens gp-pris pr. genstandstype. Alt magisk grej ER masterwork.
_MW_COST_GP = {"weapons": 300, "armor": 150, "shield": 150}

# Enhancement-prisen er (enhed × bonus²) gp: våben 2.000, rustning/skjold 1.000.
_ENH_UNIT_GP = {"weapons": 2000, "armor": 1000, "shield": 1000}


def _check_bonus(bonus: int) -> None:
    if not isinstance(bonus, int) or not (1 <= bonus <= ENH_MAX):
        raise ValueError(f"enhancement-bonus skal være 1-{ENH_MAX}, fik {bonus!r}")


def added_cost_cp(kind: str, bonus: int) -> int:
    """Det magien LÆGGER TIL basisprisen (masterwork + enhancement), i kobber.

    kind: 'weapons' | 'armor' | 'shield'. Prisen afhænger kun af typen og bonussen,
    ikke af den konkrete genstand — derfor sit eget lille opslag.
    """
    _check_bonus(bonus)
    if kind not in _MW_COST_GP:
        raise ValueError(f"ukendt genstandstype: {kind!r}")
    gp = _MW_COST_GP[kind] + _ENH_UNIT_GP[kind] * bonus * bonus
    return gp * 100


def enhance_weapon(weapon: dict, bonus: int) -> dict:
    """Base-våben + enhancement → overlay-felter til visning/beregning.

    Enhancement-bonussen gælder BÅDE angreb og skade. Masterwork-våbnets +1 til
    angreb stacker ikke med enhancement (derfor eksponeres kun `attack_bonus`).
    """
    add = added_cost_cp("weapons", bonus)
    return {
        "name": f"+{bonus} {weapon['name']}",
        "enhancement": bonus,
        "attack_bonus": bonus,
        "damage_bonus": bonus,
        "masterwork": True,
        "added_cost_cp": add,
        "total_cost_cp": (weapon.get("cost_cp") or 0) + add,
        "caster_level": 3 * bonus,
    }


def as_inventory_item(base_ref: str, bonus: int) -> dict:
    """Magisk item (base-ref + enhancement) → InventoryItem-kwargs (uden display-navn;
    kalderen sætter '+N <navn>' fra den opslåede base).

    Ren: afgør kun feltmapningen ud fra tabellen i ref. Rustning/skjold bruger
    `enhancement` (→ AC + navn via items.py). Våben bærer `enhancement` som mærkat OG
    `bonus` (til-hit); +N SKADE i angrebs-rækken er endnu ikke wired (trin 2 MVP). Loot
    lander i rygsækken — spilleren udstyrer det selv.
    """
    _check_bonus(bonus)
    table = base_ref.partition("/")[0]
    if table not in ("weapons", "armor"):
        raise ValueError(f"kun weapons/armor kan gøres magiske, fik {base_ref!r}")
    kwargs = {"ref": base_ref, "enhancement": bonus, "state": "backpack"}
    if table == "weapons":
        kwargs["bonus"] = bonus                # til-hit; +N skade wires senere
    return kwargs


def enhance_armor(armor: dict, bonus: int) -> dict:
    """Base-rustning eller -skjold + enhancement → overlay-felter.

    Enhancement-bonussen er et AC-tillæg (stacker med base armor/shield-bonus). Alt
    magisk grej er masterwork → rustningstjek-straffen (ACP) forbedres med 1.
    Skjolde prissættes som rustning; typen udledes af `type == 'shield'`.
    """
    kind = "shield" if armor.get("type") == "shield" else "armor"
    add = added_cost_cp(kind, bonus)
    return {
        "name": f"+{bonus} {armor['name']}",
        "enhancement": bonus,
        "ac_bonus": bonus,
        "acp_reduction": 1,       # masterwork: armor check penalty 1 mindre
        "masterwork": True,
        "added_cost_cp": add,
        "total_cost_cp": (armor.get("cost_cp") or 0) + add,
        "caster_level": 3 * bonus,
    }
