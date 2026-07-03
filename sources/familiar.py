"""Familiar-regler for Wizard/Sorcerer (SRD) — bygget oven på companion-motoren.

En familiar genbruger companion-statblok-motoren (advance_companion), men afviger
på tre SRD-punkter, der håndteres her:
  • ingen bonus-HD; naturlig rustning og Int stiger efter MESTERENS niveau (tabel),
  • familiarens maks-HP = HALVDELEN af mesterens maks-HP (ikke afledt af dens HD),
  • specials akkumulerer (Alertness, share spells … → deliver touch, speak with master …).

Selve statblok-udregningen (BAB/saves/AC/angreb) lånes uændret fra companion.py.
Mester-bonussen (toad +3 HP, rat +2 Fort …) bor i data/familiars.yaml og lægges på
MESTERENS ark i character_view — ikke her.
"""
from companion import advance_companion
from effects import collect_active_effects, collect_riders

# Klasser der får en familiar via Summon Familiar (Sp). Begge fra level 1.
FAMILIAR_CLASSES = {"wizard", "sorcerer"}


def familiar_eligible(cls: str, level: int) -> bool:
    """Kan klassen tilkalde en familiar? (Wizard/Sorcerer fra level 1.)"""
    return (cls or "").lower() in FAMILIAR_CLASSES and level >= 1


# (min_master_level, special) — akkumuleres: familiaren beholder tidligere evner.
_FAMILIAR_SPECIALS = [
    (1,  "Alertness"),
    (1,  "Improved Evasion"),
    (1,  "Share Spells"),
    (1,  "Empathic Link"),
    (3,  "Deliver Touch Spells"),
    (5,  "Speak with Master"),
    (7,  "Speak with Animals of Its Kind"),
    (11, "Spell Resistance (mester-level + 5)"),
    (13, "Scry on Familiar"),
]


def _familiar_specials(master_level: int) -> list[str]:
    """Akkumulerede familiar-specials ved et givet mesterniveau (SRD)."""
    return [name for lvl, name in _FAMILIAR_SPECIALS if master_level >= lvl]


def familiar_deltas(master_level: int) -> dict:
    """Familiar-avancement → normaliseret companion-delta (til advance_companion).

    SRD: naturlig rustning +⌈lvl/2⌉ og Int = 5+⌈lvl/2⌉ (level 1-2 → +1 / Int 6,
    19-20 → +10 / Int 15). Ingen bonus-HD, ingen Str/Dex-stigning, ingen tricks.
    """
    step = (master_level + 1) // 2          # 1-2→1, 3-4→2, … 19-20→10
    return {"bonus_hd": 0, "na_bonus": step,
            "str_bonus": 0, "dex_bonus": 0,
            "int_set": 5 + step, "bonus_tricks": 0,
            "specials": _familiar_specials(master_level),
            "level_label": f"familiar (mester-level {master_level})"}


def build_familiar(char, db) -> dict | None:
    """Byg familiar-statblok fra char.companion (kind == 'familiar') eller None.

    Genbruger advance_companion; overstyrer derefter maks-HP til ½ af mesterens
    (SRD) og markerer statblokken som familiar. Effekter (buffs/tilstande) på
    familiaren kører gennem samme motor som companion/hovedkarakter.
    """
    comp = char.companion or {}
    if comp.get("kind") != "familiar":
        return None
    animal_id = comp.get("animal")
    animal = db.get_animal(animal_id) if animal_id else None
    if not animal:
        return None

    active_modifiers, sources = collect_active_effects(
        comp.get("buffs"), comp.get("conditions"), db)
    riders = collect_riders(sources)
    stat = advance_companion(animal, familiar_deltas(char.level), db,
                             active_modifiers, riders)
    stat["kind"] = "familiar"
    stat["name"] = comp.get("name") or animal["name"]
    stat["tricks"] = []          # familiaren er et Int-væsen — bruger ikke tricks (delt template)
    # SRD: familiarens HP = halvdelen af mesterens maks-HP (rundet ned, mindst 1).
    stat["hp_max"] = max(1, int(char.hp_max) // 2)
    hp_cur = comp.get("hp_current")
    stat["hp_current"] = stat["hp_max"] if hp_cur is None else min(int(hp_cur), stat["hp_max"])
    stat["conditions"] = [(cid, db.get_condition(cid)) for cid in (comp.get("conditions") or [])]
    stat["buffs"] = list(comp.get("buffs") or [])
    return stat
