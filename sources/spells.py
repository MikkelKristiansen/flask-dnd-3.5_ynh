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
    div = int(row.get("dice_per_level_div") or 1)
    dice = (caster_level * per) // div          # div=2 → 1 terning pr. 2 niveauer (Vampiric Touch)
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
                    # spell_attack_damage når der ikke er dice_per_level. Tom skade
                    # (debuff-stråler: Ray of Enfeeblement) → "—" (effekten står i alt_note).
                    fixed_damage=spell_area_damage(r, char.level) or "—",
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
                    "shots": spell_shots(r, char.level),
                    "auto_hit": bool(r.get("auto_hit")),
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


def spell_shots(row: dict, caster_level: int) -> int:
    """Antal missiler/stråler et spell-angreb affyrer ved et givet casterniveau.

    shots (basis, tom=1) + ét ekstra pr. shots_div niveauer fra og med shots_from,
    cappet ved shots_max.
      Magic Missile (1, from 1, div 2, max 5): CL1→1, CL3→2, CL9→5, CL11→5.
      Scorching Ray (1, from 3, div 4, max 3): CL5→1, CL7→2, CL11→3.
    Uden shots-felter → 1 (almindeligt enkelt-angreb).
    """
    base = int(row.get("shots") or 1)
    frm = row.get("shots_from")
    if frm is None:
        return base
    div = int(row.get("shots_div") or 1)
    total = base + max(0, caster_level - int(frm)) // div
    cap = row.get("shots_max")
    return min(total, int(cap)) if cap is not None else total


def multiply_damage(expr: str, n: int) -> str:
    """Gang et skade-udtryk op med antal skud: "1d4+1" ×3 → "3d4+3".

    Bruges når et angrebsspell affyrer flere missiler/stråler der hver ruller
    basis-skaden (Magic Missile, Scorching Ray). Ganger både terning-antal og
    fladt bonus. Uden match (tomt/uparseligt) → uændret.
    """
    if n <= 1:
        return expr
    m = re.match(r"(\d+)d(\d+)([+-]\d+)?$", (expr or "").strip())
    if not m:
        return expr
    dice = int(m.group(1)) * n
    bonus = int(m.group(3) or 0) * n
    return f"{dice}d{m.group(2)}" + (f"{bonus:+d}" if bonus else "")


def spell_cast_info(spell_id: str, caster_level: int, db) -> dict | None:
    """Info til ⚡ Kast-knappen for et ØJEBLIKKELIGT angrebsspell (kategori B).

    Modsat self_duration-spells (Produce Flame), der holdes "I brug" og vises som
    en varig angrebsrække, kastes et instantaneous angreb her-og-nu: rul skaden,
    brug slotten. Returnerer det knappen behøver, eller None hvis spellet ikke er
    et kategori-B-angreb (så ingen Kast-knap — save/område-spells håndteres ikke her).

      Magic Missile CL1 → {damage: "1d4+1", shots: 1, roll_expr: "1d4+1", auto_hit: True}
      Magic Missile CL3 → {..., shots: 2, roll_expr: "2d4+2"}
      Scorching Ray CL7 → {damage: "4d6", shots: 2, roll_expr: "8d6", auto_hit: False}
    """
    atk_rows = [r for r in db.get_spell_attacks(spell_id) if r.get("kind") != "save"]
    if not atk_rows:
        return None
    r = atk_rows[0]
    per_shot = spell_area_damage(r, caster_level)  # håndterer flad + terning-skalering
    if not per_shot:
        return None
    shots = spell_shots(r, caster_level)
    return {
        "kind": "attack",
        "damage": per_shot,
        "shots": shots,
        "roll_expr": multiply_damage(per_shot, shots),
        "auto_hit": bool(r.get("auto_hit")),
        "dmg_type": r.get("dmg_type") or "",
    }


def spell_save_cast_info(spell_id: str, caster_level: int, db) -> dict | None:
    """Kast-info til et ØJEBLIKKELIGT kategori-E-spell (område/save: Fireball, Sleep).

    Modsat kategori B (spell_cast_info) er der intet til-hit — modstanderen slår en
    save mod en DC. Vi giver skade-strengen (skaleret; tom for rene save-effekter som
    Sleep) + save-type/-effekt. Selve DC'en lægges på i VIEW-laget (kræver caster-mod
    + Spell Focus, som ikke kendes her). None hvis spellet ikke har en save-række.

      Fireball CL5 → {damage: "5d6", save_type: "reflex", save_effect: "half", ...}
      Sleep        → {damage: "",   save_type: "will",   save_effect: "negates", ...}
    """
    save_rows = [r for r in db.get_spell_attacks(spell_id) if r.get("kind") == "save"]
    if not save_rows:
        return None
    r = save_rows[0]
    return {
        "kind": "save",
        "damage": spell_area_damage(r, caster_level),
        "dmg_type": r.get("dmg_type") or "",
        "save_type": r.get("save_type") or "",
        "save_effect": r.get("save_effect") or "",
    }


# ── Kategori F: ren utility/varighed (Fly, Invisibility, Detect …) ──────────
# En F-spell har ingen tal at beregne — arket skal bare kunne resolve den ved bordet:
# er den aktiv, hvor længe endnu, og hvad gør den. Varigheds-teksten står som prosa i
# spells.yaml ("10 min./level (D)"); spell_duration parser den til et tal der skalerer
# med casterniveau. Uparsbart → rå tekst som note (gætter ALDRIG et tal).

# Enheds-labels til den beregnede varigheds-streng (ental, flertal).
_DUR_UNIT_LABEL = {
    "round": ("runde", "runder"),
    "min":   ("min", "min"),
    "hour":  ("time", "timer"),
    "day":   ("dag", "dage"),
}


def _dur_norm_unit(token: str) -> str:
    """SRD-enheds-token → intern enhed (min./minute → min, o.l.)."""
    t = token.lower().rstrip(".")
    if t in ("min", "minute", "minutes"):
        return "min"
    if t in ("hour", "hours"):
        return "hour"
    if t in ("day", "days"):
        return "day"
    return "round"


def _dur_computed(value: int, unit: str) -> str:
    """Beregnet varigheds-streng på dansk: (5, "min") → "5 min"; (1, "hour") → "1 time"."""
    sing, plur = _DUR_UNIT_LABEL[unit]
    return f"{value} {sing if value == 1 else plur}"


def _dur_result(text: str, **over) -> dict:
    """Basis-varighedsdict med defaults; over-skriver de felter der er sat."""
    base = {
        "text": text, "computed": None, "value": None, "unit": None,
        "per_level": False, "dismissible": "(d)" in text.lower(),
        "instantaneous": False, "permanent": False, "concentration": False,
        "special": False,
    }
    base.update(over)
    return base


def spell_duration(spell: dict, caster_level: int) -> dict | None:
    """Parser spellets `duration`-felt → struktureret varighed, skaleret med niveau.

    Returnerer None hvis feltet er tomt. Ellers en dict med altid: text (rå), computed
    (beregnet dansk streng el. None), dismissible ((D)), + flag/tal. Gætter ALDRIG på
    uparsbar tekst — så falder computed tilbage til None og text vises som note.

      "10 min./level" @ CL5 → value=50, unit=min, computed="50 min", per_level=True
      "24 hours"            → value=24, unit=hour, computed="24 timer", per_level=False
      "1 round/level (D)" @ CL2 → computed="2 runder", dismissible=True
      "Concentration, up to 1 min./level (D)" @ CL4 → concentration+dismissible, "4 min"
      "Instantaneous" → instantaneous=True, computed=None
      "Permanent" / "See text" → permanent/special, computed=None
    """
    raw = (spell.get("duration") or "").strip()
    if not raw:
        return None
    low = raw.lower()
    # SRD skriver konsekvent "One day/level" med ord — normalisér til tal (ikke et gæt,
    # "one" er entydigt) så det rammer /level-parseren nedenfor som "1 day/level".
    if low.startswith("one "):
        low = "1 " + low[4:]

    if low.startswith("instantaneous"):
        return _dur_result(raw, instantaneous=True)
    if low.startswith("permanent"):
        return _dur_result(raw, permanent=True)

    # Concentration, up to N unit/level → koncentration MEN med et loft vi kan skalere.
    m = re.match(r"concentration,?\s*up to\s*(\d+)\s*([a-z]+)\.?\s*/\s*level", low)
    if m:
        unit = _dur_norm_unit(m.group(2))
        value = int(m.group(1)) * caster_level
        return _dur_result(raw, concentration=True, per_level=True,
                           value=value, unit=unit, computed=_dur_computed(value, unit))
    if low.startswith("concentration"):
        return _dur_result(raw, concentration=True)

    # N unit/level (skalerer med niveau) — den store TRACKER-kandidat-gruppe.
    m = re.match(r"(\d+)\s*([a-z]+)\.?\s*/\s*level", low)
    if m:
        unit = _dur_norm_unit(m.group(2))
        value = int(m.group(1)) * caster_level
        return _dur_result(raw, per_level=True, value=value, unit=unit,
                           computed=_dur_computed(value, unit))

    # Fast varighed: N unit (uden /level) — "24 hours", "7 rounds", "1 minute".
    m = re.match(r"(\d+)\s*([a-z]+)", low)
    if m and "/level" not in low and _dur_norm_unit(m.group(2)) in _DUR_UNIT_LABEL:
        unit = _dur_norm_unit(m.group(2))
        value = int(m.group(1))
        return _dur_result(raw, value=value, unit=unit,
                           computed=_dur_computed(value, unit))

    # "See text" og alt andet uparsbart → vis rå tekst som note, intet gættet tal.
    return _dur_result(raw, special=True)


def dur_unit_label(unit: str) -> str:
    """Kort dansk enheds-label til nedtælleren (flertalsform): min → "min",
    hour → "timer", round → "runder", day → "dage"."""
    return _DUR_UNIT_LABEL.get(unit, (unit, unit))[1]


def spell_duration_snapshot(spell: dict, caster_level: int) -> dict | None:
    """Snapshot til live-nedtælleren ved aktivering: {left, max, unit} for en
    TIDSBESTEMT varighed (skaleret med niveau). None hvis der ikke er et fast tal at
    tælle ned (øjeblikkelig, permanent, ren koncentration uden loft, uparsbar) — de
    vises stadig statisk, men uden −/+-knapper. Varigheden fryses ved kast (D&D-regel:
    caster-niveau på kaste-tidspunktet), så vi gemmer max separat fra left.
    """
    dur = spell_duration(spell, caster_level)
    if not dur or dur["value"] is None or dur["unit"] is None:
        return None
    if dur["permanent"] or dur["instantaneous"]:
        return None
    v = int(dur["value"])
    return {"left": v, "max": v, "unit": dur["unit"]}


def spell_is_utility(spell_id: str, db) -> bool:
    """Er spellet kategori F (ren utility) i RUNTIME-forstand — dvs. producerer det
    ingen tal andre steder på arket? F = residual: intet spell-angreb/-effekt
    (`spell_attacks`, kategori B/E), ingen buff-post (`effects`, kategori A), og ingen
    summon (kategori C). Så er der kun status + varighed + note tilbage at vise.
    """
    if db.get_spell_attacks(spell_id):          # B (angreb) eller E (save)
        return False
    if db.get_effect(spell_id):                 # A (passiv buff m/ tal)
        return False
    import refdata
    if refdata.summon_family(spell_id) is not None:   # C (summon)
        return False
    return True


def derive_active_utility(char: "Character", db) -> list[dict]:
    """Kategori F på "I brug": utility-spells uden tal → status + beregnet varighed.

    Parallel til derive_spell_effects/-attacks, men F har intet at beregne. Vi viser
    navn + skaleret varighed (fra spell_duration) + evt. (D)-mærkat. Øjeblikkelige
    F-spells (Knock, de fleste Detect) filtreres fra — de har ingen varighed at vise.
    """
    out: list[dict] = []
    for lvl, indices in (char.spells_active or {}).items():
        prepared = char.spells_prepared.get(lvl, [])
        for idx in indices:
            if not (0 <= idx < len(prepared)):
                continue
            sid = prepared[idx]
            if not spell_is_utility(sid, db):
                continue
            spell = db.get_spell(sid) or {}
            dur = spell_duration(spell, char.level)
            if dur is None or dur["instantaneous"]:
                continue                        # intet varigt at vise
            # Live-nedtæller: brug det gemte snapshot (nedtalt af brugeren) hvis det
            # findes; ellers et friskt snapshot til visning (persisteres først ved
            # første klik). None for koncentration/permanent/uparsbar → statisk visning.
            key = spell_charge_key(lvl, idx)
            tracker = (char.spell_durations or {}).get(key) \
                or spell_duration_snapshot(spell, char.level)
            import refdata
            out.append({
                "label":       spell.get("name") or sid,
                "spell_id":    sid,
                "level":       lvl,
                "index":       idx,
                "note":        refdata.spell_note(sid),
                "computed":    dur["computed"],
                "duration_text": dur["text"],
                "dismissible": dur["dismissible"],
                "concentration": dur["concentration"],
                "permanent":   dur["permanent"],
                "tracker":     tracker,
                "unit_label":  dur_unit_label(tracker["unit"]) if tracker else "",
                "school":      spell.get("school") or "",
                "range":       spell.get("range") or "",
                "area":        spell.get("target") or "",
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
