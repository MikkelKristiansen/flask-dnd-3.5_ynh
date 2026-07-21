"""Spontane castere (sorcerer/bard): aktive spell-INSTANSER.

Forberedte castere sporer aktive spells pr. slot-indeks i ``spells_prepared`` —
al varigheds-/mode-/ladnings-tracking keyer på ``"level-index"``. Spontane castere
har ingen faste indekser: de caster fra en pulje (``spells_known_used``) og kan
caste SAMME kendte spell flere gange. Hvert varigheds-/summon-kast bliver derfor
en uafhængig instans i ``char.spells_known_active`` nøglet på en stabil ``uid``.

Dette modul holder den uid-baserede sti adskilt fra den fungerende index-baserede
(``spells.derive_spell_effects`` / ``derive_active_utility``); klassificerings-
helperne (``spell_is_utility`` osv.) er rene og genbruges uændret på hver kendt
spell.
"""
from __future__ import annotations

import spells as sp


def next_uid(instances: list, level: int, spell_id: str) -> str:
    """Stabil, unik nøgle for en ny instans: ``f"{level}-{spell_id}-{n}"``.

    ``n`` = største eksisterende løbenummer for samme (level, spell_id) + 1, så
    to kast af samme spell aldrig kolliderer selv efter at én er fjernet."""
    prefix = f"{level}-{spell_id}-"
    n = 0
    for inst in instances or []:
        u = str(inst.get("uid", ""))
        if u.startswith(prefix):
            try:
                n = max(n, int(u[len(prefix):]) + 1)
            except ValueError:
                pass
    return f"{prefix}{n}"


def spell_is_activatable(spell_id: str, spell: dict, caster_level: int, db) -> bool:
    """Er dette et varigheds-/vedvarende spell (ikke øjeblikkeligt)?

    Samme kriterie som prepared-loopets ``three_state``: self_duration, ELLER en
    utility med en ikke-øjeblikkelig varighed, ELLER et vedvarende kamp-spell.
    Sådanne spells aktiveres som en instans i stedet for at rulles én gang."""
    if spell and spell.get("self_duration"):
        return True
    if sp.spell_is_utility(spell_id, db):
        dur = sp.spell_duration(spell or {}, caster_level)
        if dur and not dur["instantaneous"]:
            return True
    if sp.spell_is_sustained_combat(spell_id, caster_level, db):
        return True
    return False


def make_instance(char, spell_id: str, level: int, db) -> dict:
    """Byg en ny aktiv instans for et kendt spell — snapshot af varigheden ved
    kaste-tidspunktet (D&D-regel: caster-niveau fryses ved kast, som summons)."""
    spell = db.get_spell(spell_id) or {}
    inst = {
        "uid": next_uid(char.spells_known_active, level, spell_id),
        "level": level,
        "spell_id": spell_id,
        "kind": "duration",
    }
    snap = sp.spell_duration_snapshot(spell, char.level)
    if snap:
        inst["duration"] = snap
    return inst


def derive_known_active(char, db) -> list[dict]:
    """Render-rækker for de aktive spontane instanser (til "Aktive effekter").

    Én række pr. instans, nøglet på ``uid`` i stedet for level-index. Samme
    felter som ``derive_active_utility``/``derive_spell_effects`` tilsammen:

    - Alle rækker bærer varigheds-trackeren (nedtæller).
    - Vedvarende kamp-spells (Flaming Sphere) er også ``is_effect``: de bærer en
      rulbar skade-formel + save-type/-effekt (DC lægges på i view-laget, som
      kræver caster-evne-modifier). Har et spell flere save-angreb, bruges det
      FØRSTE — de sorcerer-relevante vedvarende spells har præcis ét."""
    out: list[dict] = []
    for inst in (char.spells_known_active or []):
        sid = inst["spell_id"]
        spell = db.get_spell(sid) or {}
        dur = sp.spell_duration(spell, char.level)
        tracker = inst.get("duration")
        row = {
            "uid":          inst["uid"],
            "label":        spell.get("name") or sid,
            "level":        inst["level"],
            "spell_id":     sid,
            "tracker":      tracker,
            "unit_label":   sp.dur_unit_label(tracker["unit"]) if tracker else "",
            "duration_text": (dur or {}).get("computed") or (dur or {}).get("text", ""),
            "concentration": bool(dur and dur.get("concentration")),
            "permanent":    bool(dur and dur.get("permanent")),
            "school":       spell.get("school") or "",
            "is_effect":    False,
        }
        # Vedvarende kamp: første save-angreb → skade/save på rækken (rulbar hver
        # runde mens instansen er aktiv). Almindelige varigheds-buffs har ingen.
        if sp.spell_is_sustained_combat(sid, char.level, db):
            save_row = next((r for r in db.get_spell_attacks(sid)
                             if r.get("kind") == "save"), None)
            if save_row:
                row.update({
                    "is_effect":   True,
                    "damage":      sp.spell_area_damage(save_row, char.level),
                    "dmg_type":    save_row.get("dmg_type") or "",
                    "save_type":   save_row.get("save_type") or "",
                    "save_effect": save_row.get("save_effect") or "",
                    "range":       spell.get("range") or "",
                    "area":        spell.get("target") or "",
                    "duration":    spell.get("duration") or "",
                })
        out.append(row)
    return out
