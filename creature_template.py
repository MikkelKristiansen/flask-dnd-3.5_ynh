"""Celestial/Fiendish-skabeloner til summonede væsner (Summon Monster) — SRD v3.5.

Ansvar: læg en skabelon (celestial/fiendish) oven på et RÅT katalog-væsen og
returnér en modificeret væsen-dict, som summon.py bygger statblok af. Samme
overlay-mønster som materiale-modifikatorer i udrustningsbutikken
(catalog.apply_material_overlay): data (refdata.creature_templates) beskriver hvad
skabelonen giver, og koden her skalerer det efter væsenets Hit Dice og fletter det
ind i de BESKRIVENDE felter — navne-præfiks, special_qualities (darkvision, DR,
energiresistens, SR) og special_attacks (smite). Ability scores, HP, AC og angreb
røres IKKE (skabelonen ændrer dem ikke i SRD).
"""
import refdata


def _tier_value(tiers, hd: int) -> int:
    """Den HØJESTE [min_hd, værdi]-tier hvor min_hd ≤ hd; 0 hvis ingen matcher."""
    val = 0
    for min_hd, value in (tiers or []):
        if hd >= min_hd:
            val = value
    return val


def _prepend(existing, added: str) -> str:
    """Flet skabelon-tekst ind FORAN eksisterende special-tekst (uden dobbelt-';')."""
    existing = (existing or "").strip()
    if existing and added:
        return f"{added}; {existing}"
    return added or existing


def display_name(base_name: str, template_key: str | None) -> str:
    """Vis-navn til picker/fane: 'Celestial Dog' / basis-navn hvis ingen skabelon."""
    if not template_key:
        return base_name
    tmpl = (refdata.creature_templates().get("templates") or {}).get(template_key)
    prefix = tmpl["name_prefix"] if tmpl else template_key.capitalize()
    return f"{prefix} {base_name}"


def apply_template(animal: dict, template_key: str | None) -> dict:
    """Returnér en KOPI af væsenet med skabelonen lagt på (uændret hvis None/ukendt).

    Kun de beskrivende felter ændres — resten af dict'en deles med originalen, hvilket
    er sikkert fordi summon.py kun læser dem.
    """
    if not template_key:
        return animal
    data = refdata.creature_templates()
    tmpl = (data.get("templates") or {}).get(template_key)
    if not tmpl:
        return animal
    scaling = data.get("scaling") or {}
    hd = animal.get("base_hd") or 0

    out = dict(animal)
    out["name"] = f"{tmpl['name_prefix']} {animal['name']}"

    quals = []
    if tmpl.get("darkvision"):
        quals.append(f"darkvision {tmpl['darkvision']} ft.")
    dr = _tier_value(scaling.get("dr"), hd)
    if dr:
        quals.append(f"DR {dr}/magic")
    resist = _tier_value(scaling.get("resist"), hd)
    energies = tmpl.get("resist_energies") or []
    if resist and energies:
        quals.append(f"resistance to {'/'.join(energies)} {resist}")
    sr_bonus = scaling.get("sr_bonus") or 0
    if sr_bonus:
        quals.append(f"SR {hd + sr_bonus}")
    out["special_qualities"] = _prepend(animal.get("special_qualities"), ", ".join(quals))

    smite = tmpl.get("smite")
    if smite:
        bonus = min(hd, scaling.get("smite_max") or hd)
        out["special_attacks"] = _prepend(
            animal.get("special_attacks"),
            f"smite {smite} 1/day (+{bonus} damage vs {smite})")
    return out
