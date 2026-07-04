"""Spell-mekanik: skade-skalering, save-DC, slots og udledning af spell-angreb/
-effekter fra spells der står på "I brug".

Udspaltet fra rules.py (som var vokset til 1377 linjer med mange ansvar). Denne fil
har ét ansvar: reglerne for hvordan spells producerer tal på arket. Ren beregning —
ingen I/O udover det `db`-objekt der gives som argument.

Kategorierne (se briefs/STRATEGY-spells.md):
  B  spell-angreb jeg ruller  → spell_attacks-rækker m/ til-hit (derive_spell_attacks)
  E  offensiv mod fjende      → save-DC + skade (derive_spell_effects, spell_area_damage)
"""
import re

from models import Attack


def spell_charge_key(level: int, index: int) -> str:
    """Nøgle til spell_charges-dict'en for en spell på (level, index)."""
    return f"{level}-{index}"


def spell_attack_damage(row: dict, caster_level: int) -> str:
    """Udregn skade-strengen for et katalog-spell-angreb (gemmes aldrig).

    base_damage + min(floor(caster_level * dmg_per_level / dmg_per_level_div),
                      dmg_per_level_max) + dmg_bonus.
    Produce Flame (1d6, +1/niv, cap 5) ved niveau 2 → "1d6+2".
    Flame Blade (1d8, +1/2 niv, cap 10) ved niveau 5 → "1d8+2".
    Magic Stone (1d6, +1 flad) → "1d6+1".
    """
    bonus = int(row.get("dmg_bonus") or 0)
    per = int(row.get("dmg_per_level") or 0)
    if per:
        div = int(row.get("dmg_per_level_div") or 1)
        lvl_bonus = (caster_level * per) // div
        cap = row.get("dmg_per_level_max")
        if cap is not None:
            lvl_bonus = min(lvl_bonus, int(cap))
        bonus += lvl_bonus
    base = row["base_damage"]
    return f"{base}{bonus:+d}" if bonus else base


def spell_area_damage(row: dict, caster_level: int) -> str:
    """Skade-streng for et kategori-E (område/save) spell — TERNING-skalering.

    Modsat spell_attack_damage (flad +bonus pr. niveau) skalerer blast-spells
    ANTALLET af terninger: Fireball 1d6 pr. casterniveau, cappet ved 10 terninger.
      Fireball (1d6, 1/niveau, cap 10) ved CL 5  → "5d6";  ved CL 12 → "10d6".
      Cone of Cold (1d6, 1/niveau, cap 15) ved CL 9 → "9d6".
    Rene save-effekter uden skade (Sleep/Web) har tom base_damage → "".
    Uden dice_per_level falder vi tilbage til den flade motor (fast eller +bonus).
    """
    base = row.get("base_damage")
    if not base:
        return ""
    per = int(row.get("dice_per_level") or 0)
    if not per:
        return spell_attack_damage(row, caster_level)
    m = re.match(r"(\d+)d(\d+)", str(base))
    mult, faces = (int(m.group(1)), int(m.group(2))) if m else (1, 6)
    dice = caster_level * per
    cap = row.get("dice_per_level_max")
    if cap is not None:
        dice = min(dice, int(cap))
    dice = max(dice, 1) * mult
    bonus = int(row.get("dmg_bonus") or 0)
    expr = f"{dice}d{faces}"
    return f"{expr}{bonus:+d}" if bonus else expr


def _spell_attack_rows_to_show(rows: list[dict], selected: int) -> list[tuple]:
    """Reducér en spells katalog-rækker til de rækker der faktisk skal vises.

    Rækker uden mode_group vises hver for sig (mode=None). Rækker der deler et
    mode_group er gensidigt udelukkende tilstande af ét angreb → kun den valgte
    (`selected`, klampet) vises, med en mode-dict {options, current, count} så
    UI'en kan tegne en ⇄-skifteknap. Forudsætter ét mode_group pr. spell (nok til
    Produce Flame); `selected` gemmes pr. (level,index) i char.spell_modes.
    """
    out: list[tuple] = []
    group: list[dict] = []
    for r in rows:
        if r.get("mode_group"):
            group.append(r)
        else:
            out.append((r, None))
    if group:
        cur = max(0, min(selected, len(group) - 1))
        mode = {"options": [g["label"] for g in group],
                "current": cur, "count": len(group)}
        out.append((group[cur], mode))
    return out


def derive_spell_attacks(char: "Character", db) -> list[dict]:
    """Lav angreb ud fra spells der står på "I brug" via spell_attacks-kataloget.

    Hver post: {attack, level, index, spell_id, charges_max, charges_remaining,
    alt_note, mode}. charges_max=None betyder ubegrænset (ingen nedtælling).
    mode=None for almindelige angreb; ellers {options, current, count} til ⇄-skift.
    """
    out: list[dict] = []
    for lvl, indices in (char.spells_active or {}).items():
        prepared = char.spells_prepared.get(lvl, [])
        for idx in indices:
            if not (0 <= idx < len(prepared)):
                continue
            sid = prepared[idx]
            key = spell_charge_key(lvl, idx)
            selected = char.spell_modes.get(key, 0)
            # kind=save = kategori E (område/save) → håndteres af derive_spell_effects, ikke her
            attack_rows = [r for r in db.get_spell_attacks(sid) if r.get("kind") != "save"]
            for r, mode in _spell_attack_rows_to_show(attack_rows, selected):
                atk = Attack(
                    name=r["label"],
                    kind=r["kind"],
                    str_damage_mult=0,
                    # spell_area_damage håndterer BÅDE flad +bonus (Produce Flame) OG
                    # terning-skalering (Shocking Grasp 1d6/niveau); falder tilbage til
                    # spell_attack_damage når der ikke er dice_per_level.
                    fixed_damage=spell_area_damage(r, char.level),
                    bonus=int(r.get("to_hit") or 0),
                    crit=r.get("crit") or "x2",
                    type=r.get("dmg_type") or "",
                    range=f"{r['range_ft']} ft." if r.get("range_ft") else "",
                    source="spell",
                )
                charges_max = r.get("charges")
                remaining = (char.spell_charges.get(key, charges_max)
                             if charges_max else None)
                out.append({
                    "attack": atk, "level": lvl, "index": idx, "spell_id": sid,
                    "charges_max": charges_max, "charges_remaining": remaining,
                    "alt_note": r.get("alt_note") or "",
                    "mode": mode,
                })
    return out


def derive_spell_effects(char: "Character", db) -> list[dict]:
    """Kategori E (område/save): spells på "I brug" der rammer FJENDER med en
    save-DC frem for et til-hit-rul (Fireball, Lightning Bolt, Sleep, Web).

    Arket er ikke en kampsimulator — vi modellerer ikke fjenden. Vi viser bare de
    tal man skal bruge ved bordet: skade-formel (skaleret), skadetype, save-type +
    effekt, rækkevidde, area og varighed. Save-DC lægges på i view-laget (kræver
    caster-evne-modifier + Spell Focus). Rene save-effekter uden skade → damage "".
    """
    out: list[dict] = []
    for lvl, indices in (char.spells_active or {}).items():
        prepared = char.spells_prepared.get(lvl, [])
        for idx in indices:
            if not (0 <= idx < len(prepared)):
                continue
            sid = prepared[idx]
            spell = db.get_spell(sid) or {}
            for r in db.get_spell_attacks(sid):
                if r.get("kind") != "save":
                    continue
                out.append({
                    "label":       r["label"],
                    "spell_id":    sid,
                    "level":       lvl,
                    "index":       idx,
                    "damage":      spell_area_damage(r, char.level),
                    "dmg_type":    r.get("dmg_type") or "",
                    "save_type":   r.get("save_type") or "",
                    "save_effect": r.get("save_effect") or "",
                    "school":      spell.get("school") or "",
                    "range":       spell.get("range") or "",
                    "area":        spell.get("target") or "",
                    "duration":    spell.get("duration") or "",
                })
    return out


def spell_max_charges(spell_id: str, db) -> int | None:
    """Største ladnings-tal blandt en spells katalog-angreb (None hvis ingen)."""
    vals = [r["charges"] for r in db.get_spell_attacks(spell_id) if r.get("charges")]
    return max(vals) if vals else None


def active_spell_keys(spells_prepared: dict, spells_active: dict, db) -> set:
    """Identiteter for spells der står på 'I brug' — spell-id og navn, lowercased.

    Et betinget spell-angreb (Attack.requires) vises når dets 'requires' matcher
    et af disse — dvs. når den spell der skaber angrebet er aktiv (varighed kører).
    Erstatter den tidligere buff-baserede oplåsning.
    """
    keys: set[str] = set()
    for lvl, indices in (spells_active or {}).items():
        prepared = (spells_prepared or {}).get(lvl, [])
        for idx in indices:
            if 0 <= idx < len(prepared):
                sid = str(prepared[idx]).strip().lower()
                if sid:
                    keys.add(sid)
                row = db.get_spell(prepared[idx])
                if row and row.get("name"):
                    keys.add(str(row["name"]).strip().lower())
    return keys


def wis_bonus_spells(wis_score: int) -> dict[int, int]:
    """Returns extra spell slots per spell level from high Wisdom (D&D 3.5 table).

    For WIS modifier m, spell level L gets (m - L) // 4 + 1 bonus slots when m >= L.
    """
    mod = (wis_score - 10) // 2
    if mod <= 0:
        return {}
    bonus: dict[int, int] = {}
    for slot_level in range(1, 10):
        if mod >= slot_level:
            bonus[slot_level] = (mod - slot_level) // 4 + 1
    return bonus


def spell_slots_total(
    class_level_data: dict, wis_score: int
) -> dict[int, int]:
    """Returns total spell slots per level including Wisdom bonus.

    WIS bonus only applies to levels where the class already has ≥1 base slot,
    and never to level-0 cantrips (per D&D 3.5 rules).
    """
    base = {i: class_level_data[f"spells_{i}"] for i in range(10)}
    bonus = wis_bonus_spells(wis_score)
    return {
        lvl: base[lvl] + (bonus.get(lvl, 0) if lvl > 0 else 0)
        for lvl in range(10)
        if base[lvl] > 0
    }


def spell_save_dc(spell_level: int, cast_modifier: int, focus_bonus: int = 0) -> int:
    """Save-DC en modstander skal slå for at modstå et spell: 10 + spell-niveau +
    caster-evne-modifier (+ evt. Spell Focus-bonus for spellets skole)."""
    return 10 + spell_level + cast_modifier + focus_bonus


def spell_like_dc(spell_level: int, cha_modifier: int, extra: int = 0) -> int:
    """Save-DC for en spell-like ability: 10 + spell level + Cha-modifier.

    Gnomens SLA'er er Cha-baserede (SRD). `extra` rummer fx gnomens +1 til
    DC for illusionsskoler. (Flyttet fra refdata.py — ren spell-regel; se
    briefs/BRIEF-rules-split-spells.md. spell_focus_bonus blev i refdata pga.
    feat-koblingen.)
    """
    return 10 + spell_level + cha_modifier + extra
