"""magic_gear — ren overlay-motor for magiske våben/rustning/skjolde (SRD v3.5).

Ét ansvar: tag en BASE-genstand (en våben-/rustnings-række, som fra kataloget) og
en magisk enhancement-bonus, og returnér de afledte tal UI'et/DM'en skal bruge:
det magiske navn, kamp-modifikatorerne og den samlede markedspris.

Som `dm_encounter` er dette REN logik — ingen I/O, ingen DB, intet regel-opslag
udefra. Det gør motoren hermetisk testbar og neutral: den kan wires til BÅDE
karakter-butikken (catalog.py) og DM-modulet senere, uden at motoren ændres.

Enhancement-formlen (én kvadrering + to konstanter) bor som KODE her, ligesom
materiale-modifikatorerne i `items.material_modifiers`. Special abilities er derimod
DUSINVIS af navngivne entries med noter → et data-katalog (`data/magic_abilities.yaml`,
indlæst af `magic_abilities.py`). Motoren her forbliver ren: den får de allerede-
opslåede ability-dicts som argument, præcis som den får en våben-dict.

Kilde: SRD 'Magic Items II (Armor and Weapons)'.

Special abilities (flaming/keen på våben; fortification/resistance på rustning/skjold)
prissættes som "effektiv bonus" (enhancement + sum af bonus-abilities, cap +10) ELLER
et fast gp-tillæg — dét (pris + navn) er denne motors ansvar. De MEKANISKE effekter
lever et andet sted: energi-riders (flaming → +1d6 ild) og keen (crit-fordobling) wires
i attacks.py via `magic_abilities.mechanic`-feltet (trin 2). Betingede/komplekse
abilities (holy/bane/wounding/vorpal …) forbliver rene noter.
"""
from __future__ import annotations

# Højeste rene enhancement-bonus (til-hit/AC/skade). Special abilities kan give en
# højere EFFEKTIV bonus til prisberegning, men aldrig til de faktiske kamptal.
ENH_MAX = 5
# Loft på effektiv bonus (enhancement + sum af bonus-prissatte abilities), SRD.
ENH_EFF_MAX = 10

# Masterwork-komponentens gp-pris pr. genstandstype. Alt magisk grej ER masterwork.
_MW_COST_GP = {"weapons": 300, "armor": 150, "shield": 150}

# Enhancement-prisen er (enhed × bonus²) gp: våben 2.000, rustning/skjold 1.000.
_ENH_UNIT_GP = {"weapons": 2000, "armor": 1000, "shield": 1000}


def _check_bonus(bonus: int) -> None:
    if not isinstance(bonus, int) or not (1 <= bonus <= ENH_MAX):
        raise ValueError(f"enhancement-bonus skal være 1-{ENH_MAX}, fik {bonus!r}")


def bonus_equivalent(abilities: list | None) -> int:
    """Sum af de bonus-prissatte abilities' effektive-bonus-værdier (flat-abilities
    tæller 0 her — de er et fast gp-tillæg, ikke en bonus)."""
    return sum(int(a["price"]["value"]) for a in (abilities or [])
               if a.get("price", {}).get("type") == "bonus")


def flat_gp(abilities: list | None) -> int:
    """Sum af de fast-prissatte abilities' gp-tillæg."""
    return sum(int(a["price"]["value"]) for a in (abilities or [])
               if a.get("price", {}).get("type") == "flat")


def effective_bonus(enhancement: int, abilities: list | None = None) -> int:
    """Enhancement + bonus-abilities → den bonus PRISEN beregnes fra (ikke kamptallene)."""
    return enhancement + bonus_equivalent(abilities)


def _check_effective(enhancement: int, abilities: list | None) -> None:
    _check_bonus(enhancement)
    eff = effective_bonus(enhancement, abilities)
    if eff > ENH_EFF_MAX:
        raise ValueError(
            f"effektiv bonus (enh + abilities) må max være +{ENH_EFF_MAX}, fik +{eff}")


def added_cost_cp(kind: str, bonus: int, abilities: list | None = None) -> int:
    """Det magien LÆGGER TIL basisprisen (masterwork + enhancement + abilities), i kobber.

    kind: 'weapons' | 'armor' | 'shield'. Bonus-abilities hæver den effektive bonus
    (kvadreret pris); flat-abilities lægges til som fast gp. Uden abilities er
    resultatet identisk med den rene enhancement-pris (bagudkompatibelt).
    """
    _check_effective(bonus, abilities)
    if kind not in _MW_COST_GP:
        raise ValueError(f"ukendt genstandstype: {kind!r}")
    eff = effective_bonus(bonus, abilities)
    gp = _MW_COST_GP[kind] + _ENH_UNIT_GP[kind] * eff * eff + flat_gp(abilities)
    return gp * 100


def magic_name(bonus: int, base_name: str, abilities: list | None) -> str:
    """"+1 Flaming Keen Longsword" — enhancement, så ability-adjektiver, så basisnavn."""
    adjectives = " ".join(a["name"] for a in (abilities or []))
    parts = [f"+{bonus}"] + ([adjectives] if adjectives else []) + [base_name]
    return " ".join(parts)


def enhance_weapon(weapon: dict, bonus: int, abilities: list | None = None) -> dict:
    """Base-våben + enhancement (+ evt. special abilities) → overlay-felter.

    Enhancement-bonussen gælder BÅDE angreb og skade. Masterwork-våbnets +1 til
    angreb stacker ikke med enhancement (derfor eksponeres kun `attack_bonus`).
    Abilities påvirker pris + navn (TRIN 1); deres mekaniske effekter wires senere.
    """
    abilities = abilities or []
    add = added_cost_cp("weapons", bonus, abilities)
    return {
        "name": magic_name(bonus, weapon["name"], abilities),
        "enhancement": bonus,
        "attack_bonus": bonus,
        "damage_bonus": bonus,
        "abilities": abilities,
        "masterwork": True,
        "added_cost_cp": add,
        "total_cost_cp": (weapon.get("cost_cp") or 0) + add,
        "caster_level": 3 * effective_bonus(bonus, abilities),
    }


def as_inventory_item(base_ref: str, bonus: int, ability_ids: list | None = None) -> dict:
    """Magisk item (base-ref + enhancement + evt. ability-id'er) → InventoryItem-kwargs
    (uden display-navn; kalderen sætter navnet fra den opslåede base).

    Ren: afgør kun feltmapningen ud fra tabellen i ref. Rustning/skjold bruger
    `enhancement` (→ AC + navn via items.py). Våben bærer `enhancement` (→ +N skade via
    attacks.py) OG `bonus` (→ +N til-hit). Abilities gemmes som id-liste (TRIN 1: navn/
    note/pris; mekanik senere). Loot lander i rygsækken — spilleren udstyrer det selv.
    """
    _check_bonus(bonus)
    table = base_ref.partition("/")[0]
    if table not in ("weapons", "armor"):
        raise ValueError(f"kun weapons/armor kan gøres magiske, fik {base_ref!r}")
    kwargs = {"ref": base_ref, "enhancement": bonus, "state": "backpack"}
    if ability_ids:
        kwargs["abilities"] = list(ability_ids)
    if table == "weapons":
        kwargs["bonus"] = bonus                # til-hit (+N skade kommer via enhancement)
    return kwargs


def enhance_armor(armor: dict, bonus: int, abilities: list | None = None) -> dict:
    """Base-rustning eller -skjold + enhancement (+ evt. abilities) → overlay-felter.

    Enhancement-bonussen er et AC-tillæg (stacker med base armor/shield-bonus). Alt
    magisk grej er masterwork → rustningstjek-straffen (ACP) forbedres med 1.
    Skjolde prissættes som rustning; typen udledes af `type == 'shield'`.
    """
    abilities = abilities or []
    kind = "shield" if armor.get("type") == "shield" else "armor"
    add = added_cost_cp(kind, bonus, abilities)
    return {
        "name": magic_name(bonus, armor["name"], abilities),
        "enhancement": bonus,
        "ac_bonus": bonus,
        "abilities": abilities,
        "acp_reduction": 1,       # masterwork: armor check penalty 1 mindre
        "masterwork": True,
        "added_cost_cp": add,
        "total_cost_cp": (armor.get("cost_cp") or 0) + add,
        "caster_level": 3 * effective_bonus(bonus, abilities),
    }
