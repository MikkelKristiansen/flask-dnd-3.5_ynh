"""Mekanisk effekt-motor + effekt-view-lag for D&D 3.5 karakterark.

To ansvar, samme emne — derfor samme modul:

* **Motoren** reducerer rå modifier-data til nettobonus pr. target (SRD-stacking)
  og kaskaderer ability-ændringer ud i alle afledte tal. Princip: effekter er rå
  data; nettobonusset udregnes ved render, gemmes aldrig.
* **View-laget** oversætter en karakters (eller companions) aktive buffs/tilstande
  til de breakdown-strukturer skabelonen viser (▲/▼-markører, kilde-tooltips,
  ryttere, midlertidigt HP, effekt-vælgerens kataloger).

Begge bor her, så hovedkarakteren OG companion deler præcis samme effekt-håndtering
(`collect_active_effects`) i stedet for to næsten-identiske kopier.

``character.py`` re-eksporterer motorens offentlige navne (façade), så de mange
``char_module.resolve_modifiers``/``effective_ability_scores``-kald fortsat virker.
"""
from __future__ import annotations

import re

import db

# ---------------------------------------------------------------------------
# Mekaniske effekter — modifiers → nettobonus pr. target (buffs & tilstande).
#
# Princip: effekter er rå data; nettobonusset udregnes ved render, gemmes aldrig.
# Ability-ændringer (str..cha) føres gennem effective_ability_scores og kaskaderer
# automatisk ud i ALLE afledte tal (angreb, skade, saves, skills, grapple, init,
# AC). Direkte bonusser (ac/save_*/attack/...) lægges på i deres egen beregning.
# ---------------------------------------------------------------------------

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

# Bonustyper der STACKER med sig selv (flere kilder lægges sammen). Alle øvrige
# navngivne typer (enhancement, morale, deflection, …) stacker ikke: kun den
# højeste bonus / værste straf af hver type tæller. "penalty" er vores
# pseudo-type for generiske tilstandsstraffe og stacker (jf. SRD: utypede
# straffe lægges sammen).
_STACKING_TYPES = {"dodge", "circumstance", "untyped", "penalty"}


def _combine(values: list[int], btype: str) -> int:
    """Kombinér flere modifier-værdier af SAMME type efter SRD-stacking.

    Stacking-typer (dodge/circumstance/untyped/penalty) summeres. Øvrige
    navngivne typer stacker ikke: den højeste bonus + den værste straf tæller
    (en bonus og en straf af samme type tælles hver for sig).
    """
    if btype in _STACKING_TYPES:
        return sum(values)
    pos = [v for v in values if v > 0]
    neg = [v for v in values if v < 0]
    return (max(pos) if pos else 0) + (min(neg) if neg else 0)


def resolve_modifiers(mods: list[dict]) -> dict[str, int]:
    """Reducér en liste af modifiers til nettobonus pr. target (SRD stacking).

    Grupér pr. (target, bonustype), kombinér hver gruppe med _combine, og læg
    grupperne for samme target sammen. only_vs-modifiers udelades (betingede →
    vises som note, ikke i tallet); value 0 / manglende target ignoreres.

    Returnerer {target: net_int}. En ren funktion uden sideeffekter — al den
    fiddly stacking er isoleret her og dækket af unit-tests.
    """
    grouped: dict[tuple[str, str], list[int]] = {}
    for m in mods or []:
        if m.get("only_vs"):
            continue
        target = m.get("target")
        if not target:
            continue
        try:
            value = int(m.get("value", 0))
        except (TypeError, ValueError):
            continue
        if value == 0:
            continue
        btype = str(m.get("type", "untyped")).lower()
        grouped.setdefault((target, btype), []).append(value)

    net: dict[str, int] = {}
    for (target, btype), values in grouped.items():
        net[target] = net.get(target, 0) + _combine(values, btype)
    return net


def damage_dice(mods: list[dict], kind: str) -> list[dict]:
    """Ekstra skade-TERNINGER en buff lægger på et våbenangreb (Flame Arrow: +1d6 ild).

    Modsat resolve_modifiers (flade heltal) bærer disse en terning i `die` frem for
    `value`, så de ikke ryger i heltals-nettet. Scope'es som de flade damage-targets:
      damage_die         → alle våbenangreb
      damage_die_ranged  → kun ranged (Flame Arrow rammer ammunition)
      damage_die_melee   → kun nærkamp
    Returnerer [{die, type}] i den rækkefølge de står. only_vs udelades (betinget).
    """
    if kind in ("melee", "melee_touch"):
        ok = {"damage_die", "damage_die_melee"}
    elif kind in ("ranged", "ranged_touch"):
        ok = {"damage_die", "damage_die_ranged"}
    else:
        ok = {"damage_die"}
    out = []
    for m in mods or []:
        if m.get("only_vs") or m.get("target") not in ok or not m.get("die"):
            continue
        out.append({"die": str(m["die"]), "type": m.get("damage_type") or ""})
    return out


def resolve_ac_bonuses(combat_ac: dict, ac_modifiers: list[dict]) -> dict[str, int]:
    """Saml AC-bonusser pr. type (karakterens combat-felter + aktive effekter).

    AC kan ikke koges ned til ét tal som resolve_modifiers gør, fordi touch- og
    flat-footed-AC behandler typerne forskelligt (touch ignorerer natural; flat-
    footed mister dodge). Derfor stackes pr. type her og returneres delt op i de
    parametre armor_class() forventer: natural/deflection/dodge/misc.

    combat_ac: {'natural', 'deflection', 'dodge', 'misc'} fra char.combat.
    ac_modifiers: modifiers med target == 'ac' (typede). only_vs udelades.
    Ukendte AC-typer (luck/insight/sacred …) lægges i misc (de stacker indbyrdes).

    'armor'/'shield'-typer (Mage Armor, Shield-spell) returneres SEPARÉT som
    armor_effect/shield_effect — de hører til rustnings-/skjold-pladsen i
    armor_class (tæller IKKE i touch-AC, stacker IKKE med båret rustning/skjold),
    så de må ikke ende i misc (som rammer touch).
    """
    by_type: dict[str, list[int]] = {}
    seed = (("natural", combat_ac.get("natural", 0)),
            ("deflection", combat_ac.get("deflection", 0)),
            ("dodge", combat_ac.get("dodge", 0)),
            ("untyped", combat_ac.get("misc", 0)))
    for btype, value in seed:
        if value:
            by_type.setdefault(btype, []).append(int(value))
    for m in ac_modifiers or []:
        if m.get("only_vs") or m.get("target") != "ac":
            continue
        try:
            value = int(m.get("value", 0))
        except (TypeError, ValueError):
            continue
        if value:
            by_type.setdefault(str(m.get("type", "untyped")).lower(), []).append(value)

    net = {t: _combine(v, t) for t, v in by_type.items()}
    return {
        "natural": net.pop("natural", 0),
        "deflection": net.pop("deflection", 0),
        "dodge": net.pop("dodge", 0),
        "armor_effect": net.pop("armor", 0),
        "shield_effect": net.pop("shield", 0),
        "misc": sum(net.values()),   # untyped + alle øvrige typer
    }


# Mål-præfikser for saves: en modifier kan ramme alle saves (save_all) eller én.
SAVE_TARGETS = {"fortitude": "save_fort", "reflex": "save_ref", "will": "save_will"}


def resolve_target(mods: list[dict], *targets: str) -> int:
    """Nettobonus til ÉT konkret mål, hvor flere alias-targets deler stacking.

    Fx får et Will-save bidrag fra både ``save_all`` og ``save_will``; en
    resistance-bonus fra hver af dem stacker IKKE (samme type), så de skal
    kombineres SAMMEN — ikke summes hver for sig. Derfor grupperes på tværs af
    alle aliasserne pr. type og kombineres med _combine. only_vs udelades.
    """
    want = set(targets)
    by_type: dict[str, list[int]] = {}
    for m in mods or []:
        if m.get("only_vs") or m.get("target") not in want:
            continue
        try:
            value = int(m.get("value", 0))
        except (TypeError, ValueError):
            continue
        if value:
            by_type.setdefault(str(m.get("type", "untyped")).lower(), []).append(value)
    return sum(_combine(vs, t) for t, vs in by_type.items())


def save_effect_bonus(mods: list[dict], which: str) -> int:
    """Effekt-bonus til ét save (save_all + det specifikke) med korrekt stacking."""
    return resolve_target(mods, "save_all", SAVE_TARGETS.get(which, "save_all"))


def skill_effect_bonus(mods: list[dict], skill_id: str) -> int:
    """Effekt-bonus til én skill (skill_all + skill:<id>) med korrekt stacking."""
    return resolve_target(mods, "skill_all", f"skill:{skill_id}")


def conditional_modifiers(mods: list[dict]) -> list[dict]:
    """De betingede (only_vs) modifiers — vises som noter, ikke i overskriftstallet."""
    return [m for m in (mods or []) if m.get("only_vs")]


def con_temp_hp(base, eff, level: int) -> int:
    """Midlertidigt HP fra en hævet Con (Bear's Endurance m.fl.).

    SRD: en midlertidig Con-stigning giver temp-HP = Hit Dice × stigningen i
    Con-modifier (Bear's +4 Con = +2 mod → 2 HP pr. HD). Single-class: HD = level.
    Kun en Con-STIGNING tæller (en Con-skade reducerer i stedet HP — ikke modelleret).
    """
    con_delta = eff.modifier("con") - base.modifier("con")
    return max(0, con_delta) * max(1, level)


def effective_ability_scores(base, active_modifiers: list[dict]):
    """Base ability scores + ability-target modifiers → effektive scores.

    Kun ability-targets (str..cha) anvendes her; direkte bonusser håndteres i
    deres egne beregninger. Scores klampes til ≥ 0 (ability-skade kan ikke gøre
    en evne negativ). Når der ingen ability-modifiers er, returneres de samme
    værdier som base — så afledte tal er bit-uændrede uden aktive effekter.
    """
    net = resolve_modifiers(active_modifiers)
    return AbilityScores(**{
        a: max(0, getattr(base, a) + net.get(a, 0)) for a in ABILITIES
    })


# ---------------------------------------------------------------------------
# View-lag — aktive effekter → breakdown-strukturer til skabelonen.
#
# Fælles for hovedkarakter og companion: begge slår deres buffs/tilstande op i
# samme effekt-katalog via collect_active_effects, så rettelser ét sted gælder
# begge (ingen duplikeret motor-wiring).
# ---------------------------------------------------------------------------

# Niveau-skalering for buffs uden eksplicit value. +1 luck pr. 3 casterniveauer
# (min +1, max +5) for Divine Favor.
EFFECT_SCALING = {
    "divine_favor": lambda char: max(1, min(5, char.level // 3)),
}

# Default-mængde for redigerbar ability-skade (prompt-forslag).
_DAMAGE_DEFAULT = 2

# Rækkefølge for ability-skade i vælgeren (Str..Cha frem for alfabetisk).
_ABILITY_ORDER = {a: i for i, a in enumerate(ABILITIES)}


def collect_active_effects(buffs, conditions, db, scale=None):
    """Slå aktive buffs/tilstande op i effekt-kataloget → (modifiers, sources).

    Generisk over kilde: ``buffs`` og ``conditions`` er rå lister (en karakters
    eller en companions), ``db`` er katalog-modulet. Buffs identificeres via deres
    spell_id, tilstande via deres id. En buff-instans kan bære et 'value'-override
    (fx valgt ability-skade), der erstatter værdien i katalogets modifiers; ellers
    skaleres niveau-afhængige effekter via ``scale`` (en callable sid→værdi|None;
    None for companions, der ikke har et karakter-niveau). ``modifiers`` er den
    flade liste til resolve_modifiers; ``sources`` bevarer pr.-effekt-info
    (navn/kind/modifiers/riders) til breakdown- og rytter-visningen. Effekter uden
    katalog-match (fritekst-buffs, endnu-umekaniske tilstande) er ren tracking og
    bidrager ikke med tal.
    """
    modifiers: list[dict] = []
    sources: list[dict] = []

    def add(effect, instance_value=None):
        if not effect:
            return
        mods = effect.get("modifiers") or []
        if instance_value is not None:
            mods = [{**md, "value": instance_value} for md in mods]
        modifiers.extend(mods)
        sources.append({"name": effect["name"], "kind": effect.get("kind"),
                        "modifiers": mods, "riders": effect.get("riders") or []})

    for b in buffs or []:
        sid = b.get("spell_id")
        if not sid:
            continue
        val = b.get("value")
        if val is not None:
            instance_value = int(val)
        elif scale is not None:
            instance_value = scale(sid)
        else:
            instance_value = None
        add(db.get_effect(sid), instance_value)
    for cid in conditions or []:
        add(db.get_effect(cid))
    return modifiers, sources


def collect_character_effects(char, db):
    """Aktive effekter for en HOVEDkarakter (med niveau-skalering).

    Tynd indpakning om collect_active_effects, der binder karakterens niveau til
    EFFECT_SCALING — companion bruger samme motor uden skalering.
    """
    def scale(sid):
        fn = EFFECT_SCALING.get(sid)
        return fn(char) if fn else None
    return collect_active_effects(char.buffs, char.conditions, db, scale=scale)


def ability_breakdown(sources):
    """Pr. ability (str..cha): liste af {name, value} der bidrager til den.

    Bruges til ▲/▼-breakdown i visningen. Kun ability-targets (de der kaskaderer);
    only_vs-modifiers udelades — de hører ikke til i overskriftstallet.
    """
    out: dict[str, list] = {a: [] for a in ABILITIES}
    for src in sources:
        for m in src["modifiers"]:
            t = m.get("target")
            if t in out and not m.get("only_vs"):
                out[t].append({"name": src["name"], "value": int(m.get("value", 0))})
    return out


def temp_hp_from_modifiers(active_modifiers, base=None, eff=None, level=1) -> int:
    """Samlet midlertidigt HP: faste hp_temp-modifiers (Virtue) + Con-afledt temp-HP
    (Bear's Endurance). Temp-HP STACKER ikke (SRD) — den højeste kilde gælder."""
    sources = [int(m.get("value", 0)) for m in (active_modifiers or [])
               if m.get("target") == "hp_temp" and not m.get("only_vs")]
    if base is not None and eff is not None:
        sources.append(con_temp_hp(base, eff, level))
    return max(sources) if sources else 0


def temp_hp(char, db) -> int:
    """Midlertidigt HP for en karakter ud fra dens aktive effekter (fast + Con-afledt)."""
    mods, _ = collect_character_effects(char, db)
    eff = effective_ability_scores(char.ability_scores, mods)
    return temp_hp_from_modifiers(mods, char.ability_scores, eff, char.level)


def collect_riders(sources):
    """Aktive ryttere → mekaniske flag (lose_dex/half_speed) + en visningsliste.

    Mekaniske ryttere anvendes i beregningen OG vises som flag; rene noter (uden
    type) vises kun som påmindelse/advarsel. flags bærer effektnavn + kind, så de
    kan farves (tilstand=rød, buff=grøn) i visningen.
    """
    lose_dex = half_speed = False
    flags = []
    for src in sources:
        for r in src.get("riders") or []:
            rtype = (r.get("type") or "").lower()
            if rtype == "lose_dex":
                lose_dex = True
            elif rtype == "half_speed":
                half_speed = True
            # roll_only (Guidance) håndteres af tap-to-apply, ikke som flag.
            note = r.get("note")
            if note and rtype != "roll_only":
                flags.append({"name": src["name"], "kind": src.get("kind"), "note": note})
    return {"lose_dex": lose_dex, "half_speed": half_speed, "flags": flags}


def damage_bonus(damage: str) -> int:
    """Træk den efterstillede flade skade-bonus ud af en skade-streng ("1d8+4" → 4).

    Bruges kun til at vælge ▲/▼-retning når en effekt ændrer skade. Ingen +N → 0.
    """
    m = re.search(r"([+-]\d+)\s*$", damage or "")
    return int(m.group(1)) if m else 0


def stat_sources(effect_sources, targets, ability=None):
    """Navngivne effekt-kilder der påvirker et afledt tal: direkte targets + evt.
    den ability tallet bygger på (ability-buffs vises med deres rå ability-værdi,
    da det er dér de kommer ind via kaskaden). only_vs udelades."""
    out = []
    for src in effect_sources:
        for m in src["modifiers"]:
            if m.get("only_vs"):
                continue
            t = m.get("target")
            if t in targets or (ability and t == ability):
                out.append({"name": src["name"], "value": int(m.get("value", 0))})
    return out


def delta_row(name, eff_val, base_val, sources=None):
    """Et afledt tal med basis-værdi → ▲/▼-markør. sources (liste af {name,value})
    giver en breakdown-tekst i tooltippen, så man kan se hvilke effekter der bidrog."""
    row = {"name": name, "val": eff_val, "base": base_val,
           "changed": eff_val != base_val, "up": eff_val > base_val}
    if sources:
        row["detail"] = " · ".join(f"{s['name']} {s['value']:+d}" for s in sources)
    return row


def picker_catalogs():
    """Byg buff- og ability-skade-katalogerne til effekt-vælgeren ud fra effects-
    tabellen (kilden til sandheden). Erstatter de tidligere hardkodede lister.

    buff-kataloget sorteres efter navn; ability-skade efter Str..Cha-rækkefølgen.
    """
    buffs, damage = [], []
    for e in db.get_all_effects():
        picker = e.get("picker")
        entry = {"name": e["name"], "spell_id": e["id"],
                 "affects": e.get("affects") or [], "note": e.get("note") or "",
                 "category": e.get("category") or ""}
        if picker == "buff":
            buffs.append(entry)
        elif picker == "damage":
            entry.update(editable=bool(e.get("editable")), negative=bool(e.get("negative")),
                         value=_DAMAGE_DEFAULT, prompt=e.get("prompt") or "Værdi?")
            damage.append(entry)
    buffs.sort(key=lambda b: b["name"].lower())
    damage.sort(key=lambda d: _ABILITY_ORDER.get((d["affects"] or ["zzz"])[0], 99))
    return buffs, damage


# Importér AbilityScores SIDST: character.py re-eksporterer denne motors navne
# (façade), så de to moduler er gensidigt afhængige. Ved at vente til alle navne
# her er defineret undgår vi at character.py's façade-import rammer et halv-
# initialiseret modul — uanset hvilket modul der importeres først.
from character import AbilityScores  # noqa: E402
