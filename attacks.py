"""Angreb: til-hit/skade-beregning, våben-afledning, TWF, proficiency, monk.

Udspaltet fra rules.py. Importerer kun models + refdata (IKKE rules/items) — rules
importerer til gengæld size_mod_attack herfra til armor_class (én-vejs, ingen cyklus).
"""
import dataclasses
import math
import re

import magic_abilities
from models import AbilityScores, Attack, InventoryItem
from refdata import feat_id, feat_weapon


def double_threat_range(crit: str) -> str:
    """Fordobl et våbens trusselsområde (keen/Improved Critical), SRD.

    "19–20/x2" (område 19-20) → "17–20/x2"; "18–20/x2" → "15–20/x2";
    "x2" (kun 20) → "19–20/x2". Multiplikatoren (x2/x3/x4) er uændret. Uparsbar
    tekst → uændret. Bruger low_ny = 2·low − 21 (fordobler områdets størrelse)."""
    m = re.match(r"\s*(?:(\d+)\s*[–-]\s*20\s*/\s*)?x(\d+)\s*$", crit or "")
    if not m:
        return crit
    low = int(m.group(1)) if m.group(1) else 20
    mult = m.group(2)
    new_low = 2 * low - 21
    return f"{new_low}–20/x{mult}"


def _is_slashing_or_piercing(weapon: dict) -> bool:
    """Keen virker kun på stik-/hugvåben (ikke kølle/bludgeoning), SRD."""
    dt = (weapon.get("damage_type") or "").lower()
    return "slash" in dt or "pierc" in dt


SIZE_MOD_ATTACK = {   # normal størrelses-modifier: til AC og angrebsrul
    "fine": 8, "diminutive": 4, "tiny": 2, "small": 1,
    "medium": 0, "large": -1, "huge": -2, "gargantuan": -4, "colossal": -8,
}


SIZE_MOD_GRAPPLE = {  # særlig størrelses-modifier: grapple/bull rush/trip (IKKE samme som ovenfor)
    "fine": -16, "diminutive": -12, "tiny": -8, "small": -4,
    "medium": 0, "large": 4, "huge": 8, "gargantuan": 12, "colossal": 16,
}


# Default Str-til-skade-multiplier ud fra våbentype (kan overrides pr. inventory-post)
_DEFAULT_STR_MULT = {
    "two-handed": 1.5, "one-handed": 1.0, "light": 1.0, "unarmed": 1.0, "ranged": 0.0,
}


# Ranged Str-til-skade er ikke ét fladt tal — den afhænger af våbentypen (SRD):
# composite bue → fuld Str-bonus til skade (rating-cap håndhæves på ære, ikke i koden);
# regular bue (penalty_only) → kun Str-STRAF tæller, aldrig bonus; kaster-våben (full,
# fx slynge/dart/javelin) → fuld Str som melee; armbrøst/net (none/ukendt) → ingen Str.
# Data-drevet via weapons.ranged_str (se data/weapons.yaml).
_RANGED_STR_MULT = {
    "composite": (1.0, False),
    "full": (1.0, False),
    "penalty_only": (1.0, True),
}


# Default-hænder pr. weapon_class (fallback). Bruges når katalogets `hands` ikke er
# sat — kun ranged er flertydig (slynge=1, langbue=2), så de har eksplicit `hands`.
_WEAPON_HANDS = {
    "light": 1, "one-handed": 1, "two-handed": 2, "unarmed": 0, "ranged": 2,
}


def size_mod_attack(size: str) -> int:
    return SIZE_MOD_ATTACK.get(size.lower(), 0)


def size_mod_grapple(size: str) -> int:
    return SIZE_MOD_GRAPPLE.get(size.lower(), 0)


def _ranged_str(w: dict) -> tuple[float, bool]:
    """(str_damage_mult, str_penalty_only) for et ranged-våben ud fra dets ranged_str-felt."""
    return _RANGED_STR_MULT.get(w.get("ranged_str"), (0.0, False))


def weapon_hands(weapon_row: dict, two_handed: bool = False) -> int:
    """Hvor mange hænder optager våbnet? Katalogets `hands` vinder; ellers udled af
    weapon_class. Et enhåndsvåben grebet med to hænder (two_handed) optager 2."""
    hands = weapon_row.get("hands")
    if hands is None:
        hands = _WEAPON_HANDS.get(weapon_row["weapon_class"], 1)
    if two_handed and weapon_row["weapon_class"] in ("light", "one-handed"):
        hands = 2
    return hands


def two_weapon_penalty(off_hand_light: bool, has_twf_feat: bool) -> tuple[int, int]:
    """Straf på (primær hånd, off-hånd) ved two-weapon fighting (SRD-tabel).

    Begge tal er ≤ 0. off_hand_light = off-hånds-våbnet er let (eller en
    dobbeltvåbens-ende). has_twf_feat = har Two-Weapon Fighting (inkl. ranger-stil).
    """
    if has_twf_feat:
        return (-2, -2) if off_hand_light else (-4, -4)
    return (-4, -8) if off_hand_light else (-6, -10)


def _twf_note(penalty: int, is_off_hand: bool) -> str:
    """Kort UI-markør for et TWF-straffet angreb ("−2 TWF (off-hånd)")."""
    if penalty == 0:
        return ""
    hand = "off-hånd" if is_off_hand else "primær"
    return f"{penalty:+d} TWF ({hand})"


def hand_usage(inventory: list[InventoryItem], db) -> dict:
    """Hvor mange hænder optager wielded våben + båret skjold? (Medium = 2 hænder.)

    Returnerer {used, parts: [(navn, hænder)], over}. over=True når used > 2 →
    blød advarsel i UI'en (man kan ikke fysisk holde så meget). Tower shield = 2.
    """
    used = 0
    parts: list[tuple[str, int]] = []
    for item in inventory:
        if item.state == "wielded" and item.ref.startswith("weapons/"):
            w = db.get_weapon(item.ref.split("/", 1)[1])
            if w:
                hands = weapon_hands(w, item.two_handed)
                used += hands
                parts.append((item.name or w["name"], hands))
        elif item.state == "worn" and item.ref.startswith("armor/"):
            a = db.get_armor(item.ref.split("/", 1)[1])
            if a and a.get("type") == "shield":
                hands = 2 if a.get("id") == "tower_shield" else 1
                used += hands
                parts.append((a["name"], hands))
    return {"used": used, "parts": parts, "over": used > 2}


def twf_context(cls: str, level: int, class_features: dict | None,
                feat_ids: list, armor_row: dict | None) -> dict:
    """Saml hvilke TWF-niveauer karakteren har — fodres til derive_attacks.

    Two-Weapon Fighting kommer enten fra feat, eller fra rangerens combat style
    (two-weapon) fra niveau 2 OG i let/ingen rustning. Improved/Greater kommer
    fra feats, eller rangerens stil-opgradering ved niveau 6/11.
    """
    style = (class_features or {}).get("Combat Style", "")
    light_or_none = armor_row is None or armor_row.get("type") == "light"
    ranger_twf = (cls.lower() == "ranger" and "two" in style.lower()
                  and level >= 2 and light_or_none)
    return {
        "has_twf": "two_weapon_fighting" in feat_ids or ranger_twf,
        "has_improved": ("improved_two_weapon_fighting" in feat_ids
                         or (ranger_twf and level >= 6)),
        "has_greater": ("greater_two_weapon_fighting" in feat_ids
                        or (ranger_twf and level >= 11)),
        "ranger_style": ranger_twf,
    }


def weapon_focus_parts(feats: list | None, weapon_name: str) -> list[dict]:
    """Til-hit-dele fra Weapon Focus (+1) / Greater Weapon Focus (+1 mere) på det
    navngivne våben, som [{label,value}].

    Feat-posten bærer det valgte våben ({id: weapon_focus, weapon: 'Battleaxe'});
    matches mod våbnets katalog-navn.
    """
    target = (weapon_name or "").strip().lower()
    if not target:
        return []
    parts = []
    for e in (feats or []):
        if feat_weapon(e).strip().lower() != target:
            continue
        if feat_id(e) == "weapon_focus":
            parts.append({"label": "Weapon Focus", "value": 1})
        elif feat_id(e) == "greater_weapon_focus":
            parts.append({"label": "Gr. Weapon Focus", "value": 1})
    return parts


def weapon_specialization_parts(feats: list | None, weapon_name: str) -> list[dict]:
    """Skade-dele fra Weapon Specialization (+2) / Greater Weapon Specialization
    (+2 mere) på det navngivne våben, som [{label,value}]. Samme navne-match som
    weapon_focus_parts — ikke Str-skaleret, tælles fuldt pr. angreb (også off-hånd)."""
    target = (weapon_name or "").strip().lower()
    if not target:
        return []
    parts = []
    for e in (feats or []):
        if feat_weapon(e).strip().lower() != target:
            continue
        if feat_id(e) == "weapon_specialization":
            parts.append({"label": "Weapon Specialization", "value": 2})
        elif feat_id(e) == "greater_weapon_specialization":
            parts.append({"label": "Gr. Weapon Spec", "value": 2})
    return parts


def derive_attacks(inventory: list[InventoryItem], db, size: str = "medium",
                   weapon_prof: dict | None = None,
                   allowed_weapons: set = frozenset(),
                   twf: dict | None = None,
                   feats: list | None = None) -> list[Attack]:
    """Lav Attack-objekter ud fra våben i tilstand 'wielded'.

    Skade/crit/type/range slås op i weapons-kataloget (dmg_s for Small, ellers
    dmg_m). Str-til-skade tages fra posten (str_mult), ellers two_handed-flaget
    (×1,5 for enhåndsvåben), ellers default fra weapon_class. bonus = til-hit.

    weapon_prof (når givet) bruges til at lægge −4 på til-hit for uvante våben;
    item.house_rule eller allowed_weapons fjerner straffen igen.

    Two-weapon fighting: poster med off_hand=True (eller en double=True dobbeltvåbens-
    ende) tæller som off-hånds-angreb → ½ Str + straf efter two_weapon_penalty på
    ALLE wielded angreb. twf (fra twf_context) bestemmer feat-rabatten samt evt.
    ekstra off-hånds-angreb (Improved −5 / Greater −10).
    """
    # Bevar inventar-indekset (idx) — kaste-tilstand gemmes pr. genstand og skal
    # kunne slås til/fra via netop det indeks (/api/weapon_throw).
    wielded: list[tuple[int, InventoryItem, dict]] = []
    for idx, item in enumerate(inventory):
        if item.state != "wielded" or not item.ref.startswith("weapons/"):
            continue
        w = db.get_weapon(item.ref.split("/", 1)[1])
        if w:
            wielded.append((idx, item, w))

    # Er der overhovedet et off-hånds-angreb i spil? (eksplicit flag eller dobbeltvåben)
    off_items = [(it, w) for _idx, it, w in wielded if it.off_hand]
    twf_active = bool(off_items) or any(it.double for _idx, it, _w in wielded)
    if off_items:
        off_light = off_items[0][1]["weapon_class"] == "light"
    else:
        off_light = twf_active  # dobbeltvåbens-ende tæller som let
    has_twf = bool(twf and twf.get("has_twf"))
    prim_pen, off_pen = two_weapon_penalty(off_light, has_twf) if twf_active else (0, 0)

    def dmg(w: dict, which: int = 0) -> str:
        base = (w["dmg_s"] if size.lower() == "small" else w["dmg_m"]) or ""
        parts = base.split("/")
        return parts[which] if which < len(parts) else parts[0]

    _FINESSE_WEAPON_IDS = {"rapier", "whip", "spiked_chain"}

    def make(item, w, name, base_damage, mult, pen, is_off, str_penalty_only=False,
             kind=None, extra_parts=None, skip_prof=False, show_range=True,
             throw_mode=None) -> Attack:
        # kind/show_range/skip_prof/extra_parts tilsidesættes af kaste-tilstanden
        # (samme våben i nærkamp vs. kastet); default = uændret våbenopførsel.
        not_prof = False if skip_prof else not (
            item.house_rule or weapon_proficient(w, weapon_prof, allowed_weapons))
        wclass = w["weapon_class"]
        # Navngiven opdeling af til-hit-bonusen; summen bliver Attack.bonus. Weapon
        # Focus lægges HER på (matches mod våbnets navn) — tidligere gik feat'en tabt.
        parts = []
        if item.bonus:
            parts.append({"label": "masterwork/magi", "value": item.bonus})
        parts += weapon_focus_parts(feats, w["name"])
        if not_prof:
            parts.append({"label": "ikke-proficient", "value": -4})
        if extra_parts:
            parts += extra_parts
        if pen:
            parts.append({"label": "TWF", "value": pen})
        # Skade-side: Weapon Specialization (+2, ikke Str-skaleret) — matches mod
        # samme våbennavn som til-hit-delene ovenfor.
        dmg_parts = weapon_specialization_parts(feats, w["name"])
        # Magisk enhancement på våbnet → +N til skade (SRD). Til-hit-delen kommer via
        # item.bonus ("masterwork/magi") ovenfor, så her lægges KUN skade-siden på —
        # rent additivt: ikke-magiske våben (enhancement=0) er uændrede.
        if item.enhancement:
            dmg_parts.append({"label": "magi (enh.)", "value": item.enhancement})
        # Composite bue med mighty +N-rating: loft på Str-bonussen til skade (SRD).
        # Kun composite-buer har et loft; øvrige våben ignorerer item.mighty.
        str_cap = item.mighty if (w.get("ranged_str") == "composite"
                                  and item.mighty is not None) else None
        # Magiske special abilities (Del A trin 2): energi-riders (flaming → +1d6 ild,
        # rulles separat via bonus_dice) og keen (fordoblet trusselsområde, kun stik/
        # hug). Rent additivt — våben uden abilities er uændrede.
        crit = w["critical"] or "x2"
        bonus_dice = magic_abilities.weapon_riders(item.abilities)
        if magic_abilities.has_keen(item.abilities) and _is_slashing_or_piercing(w):
            crit = double_threat_range(crit)
        return Attack(
            name=name,
            kind=kind or ("ranged" if wclass == "ranged" else "melee"),
            base_damage=base_damage,
            str_damage_mult=mult,
            bonus=sum(p["value"] for p in parts),
            bonus_parts=parts,
            damage_bonus=sum(p["value"] for p in dmg_parts),
            damage_parts=dmg_parts,
            bonus_dice=bonus_dice,
            crit=crit,
            type=w["damage_type"] or "",
            range=f"{w['range_ft']} ft." if (show_range and w["range_ft"]) else "",
            not_proficient=not_prof,
            note=_twf_note(pen, is_off),
            finesse=wclass == "light" or w["id"] in _FINESSE_WEAPON_IDS,
            str_penalty_only=str_penalty_only,
            str_cap=str_cap,
            throw_mode=throw_mode,
        )

    def make_throwable(inv_index, item, w, name) -> Attack:
        """Ét angreb for et kastbart våben i den valgte tilstand (nærkamp/kastet).

        item.thrown: True=kastet, False=nærkamp, None=våbnets natur (nærkampsvåben
        → nærkamp, kastevåben som javelin → kastet). Bærer mode-info til ⇄-knappen.
        Kastet: Dex til-hit (kind=ranged) + fuld Str til skade (½ i off-hånd).
        Nærkamp med et rent kastevåben (javelin/dart): improviseret, −4 (SRD).
        """
        wclass = w["weapon_class"]
        is_off = item.off_hand
        pen = off_pen if is_off else prim_pen
        natural_thrown = wclass == "ranged"
        is_thrown = item.thrown if item.thrown is not None else natural_thrown
        labels = [f"{name} (nærkamp)", f"{name} (kastet)"]
        mode = {"options": labels, "current": 1 if is_thrown else 0,
                "count": 2, "weapon_index": inv_index}
        disp = labels[mode["current"]]
        if is_thrown:
            mult = 0.5 if is_off else (item.str_mult if item.str_mult is not None else 1.0)
            return make(item, w, disp, dmg(w, 0), mult, pen, is_off,
                        kind="ranged", show_range=True, throw_mode=mode)
        if wclass == "ranged":   # kastevåben brugt i nærkamp → improviseret −4
            mult = 0.5 if is_off else 1.0
            return make(item, w, disp, dmg(w, 0), mult, pen, is_off,
                        kind="melee", show_range=False, skip_prof=True,
                        extra_parts=[{"label": "ikke egnet til nærkamp", "value": -4}],
                        throw_mode=mode)
        # nærkampsvåben i nærkamp: normal Str-mult-udledning
        if is_off:
            mult = item.str_mult if item.str_mult is not None else 0.5
        elif item.str_mult is not None:
            mult = item.str_mult
        elif item.two_handed and wclass in ("light", "one-handed"):
            mult = 1.5
        else:
            mult = _DEFAULT_STR_MULT.get(wclass, 1.0)
        return make(item, w, disp, dmg(w, 0), mult, pen, is_off,
                    kind="melee", show_range=False, throw_mode=mode)

    attacks: list[Attack] = []
    off_attacks: list[Attack] = []
    for inv_index, item, w in wielded:
        wclass = w["weapon_class"]
        name = item.name or w["name"]
        # Kastbart våben (thrown=1 i kataloget): ét angreb m/ ⇄-skift nærkamp/kastet.
        if w.get("thrown") and not item.double:
            (off_attacks if item.off_hand else attacks).append(
                make_throwable(inv_index, item, w, name))
        elif item.off_hand:
            mult = item.str_mult if item.str_mult is not None else 0.5
            off_attacks.append(make(item, w, name, dmg(w), mult, off_pen, True))
        elif item.double:
            # Dobbeltvåben brugt som to våben: primær ende (fuld Str) + off-ende (½ Str, let)
            pmult = item.str_mult if item.str_mult is not None else 1.0
            attacks.append(make(item, w, name, dmg(w, 0), pmult, prim_pen, False))
            off_attacks.append(make(item, w, f"{name} (off-hånd)", dmg(w, 1), 0.5, off_pen, True))
        else:
            penalty_only = False
            if item.str_mult is not None:
                mult = item.str_mult
            elif item.two_handed and wclass in ("light", "one-handed"):
                mult = 1.5
            elif wclass == "ranged":
                mult, penalty_only = _ranged_str(w)
            else:
                mult = _DEFAULT_STR_MULT.get(wclass, 1.0)
            attacks.append(make(item, w, name, dmg(w, 0), mult, prim_pen, False,
                                str_penalty_only=penalty_only))

    # Ekstra off-hånds-angreb fra Improved (−5) / Greater (−10) — kloner det første off-angreb.
    if off_attacks and twf:
        template = off_attacks[0]
        extras = []
        if twf.get("has_improved"):
            extras.append((-5, "2. off-hånd"))
        if twf.get("has_greater"):
            extras.append((-10, "3. off-hånd"))
        for extra_pen, lbl in extras:
            off_attacks.append(dataclasses.replace(
                template,
                name=f"{template.name} ({lbl})",
                bonus=template.bonus + extra_pen,
                bonus_parts=template.bonus_parts + [{"label": lbl, "value": extra_pen}],
                note=f"{extra_pen:+d} ekstra off-hånd",
            ))

    return attacks + off_attacks


def _str_damage_bonus(attack: Attack, ability_scores: AbilityScores) -> tuple[int, bool]:
    """Str-bidraget til skade for ét angreb. Returnerer (bonus, capped).

    En Str-STRAF (negativ modifier) multipliceres ALDRIG (Rules Compendium:
    straffe ganges ikke) — derfor skaleres kun en Str-*bonus* af tohånds ×1.5 /
    off-hånds ×0.5. Str 9 (−1) på et tohåndsvåben giver altså −1, ikke −2.
    Derefter: regular bue = kun straf (str_penalty_only), og mighty-loft (str_cap).
    """
    mod = ability_scores.modifier("str")
    str_bonus = mod if mod < 0 else math.floor(mod * attack.str_damage_mult)
    if attack.str_penalty_only:
        str_bonus = min(str_bonus, 0)   # regular bue: kun straf, aldrig bonus
    capped = attack.str_cap is not None and str_bonus > attack.str_cap
    if capped:
        str_bonus = attack.str_cap      # composite mighty +N: loft på Str-bonus
    return str_bonus, capped


def attack_total(attack: Attack, ability_scores: AbilityScores,
                 bab: int, size: str, extra_bonus: int = 0,
                 extra_damage: int = 0, has_finesse: bool = False) -> dict:
    """Beregn til-hit og skade-streng for ét angreb.

    Til-hit: bab + ability-mod (Str for melee, Dex for ranged) + størrelse + bonus
    + extra_bonus (Bless, Magic Fang, Divine Favor, shaken/sickened-straffe).
    Skade: fixed_damage hvis sat (spell/touch — extra_damage tæller ikke, det er
    ikke våbenskade), ellers base_damage + floor(Str-mod · str_damage_mult)
    + attack.damage_bonus (Weapon Specialization — ikke Str-skaleret) + extra_damage.
    Skade-tillægget skjules når totalbonus er 0.
    """
    if attack.kind in ("ranged", "ranged_touch"):
        hit_ability = "dex"
    elif has_finesse and attack.finesse:
        hit_ability = "dex" if ability_scores.modifier("dex") > ability_scores.modifier("str") else "str"
    else:
        hit_ability = "str"
    to_hit = (bab + ability_scores.modifier(hit_ability)
              + size_mod_attack(size) + attack.bonus + extra_bonus)

    if attack.fixed_damage:
        damage = attack.fixed_damage
    else:
        str_bonus, _ = _str_damage_bonus(attack, ability_scores)
        total_bonus = str_bonus + attack.damage_bonus + extra_damage
        if total_bonus == 0:
            damage = attack.base_damage
        else:
            damage = f"{attack.base_damage}{total_bonus:+d}"

    return {"to_hit": to_hit, "damage": damage}


def attack_to_hit_breakdown(attack: Attack, ability_scores: AbilityScores,
                            bab: int, size: str, extra_bonus: int = 0,
                            has_finesse: bool = False) -> dict:
    """Navngiven opdeling af til-hit-bonusen (til hover). Summen = attack_total's to_hit.

    Samme komponenter som attack_total lægger sammen: BAB + ability-mod (Str melee /
    Dex ranged, eller den bedste af de to ved Weapon Finesse) + størrelse + attack.bonus
    (Weapon Focus/masterwork/magi/proficiens-straf/TWF — bundtet i modellen) + effekter.
    BAB og ability vises altid; øvrige dele kun når de ≠ 0.
    """
    if attack.kind in ("ranged", "ranged_touch"):
        hit_ability = "dex"
    elif has_finesse and attack.finesse:
        hit_ability = "dex" if ability_scores.modifier("dex") > ability_scores.modifier("str") else "str"
    else:
        hit_ability = "str"
    ability_mod = ability_scores.modifier(hit_ability)
    size_m = size_mod_attack(size)

    parts = [{"label": "BAB", "value": bab},
             {"label": hit_ability.upper(), "value": ability_mod}]
    if size_m:
        parts.append({"label": "størrelse", "value": size_m})
    # Navngivne våben-/feat-dele (Weapon Focus, masterwork/magi, ikke-prof., TWF) hvis
    # angrebet bærer dem (udledte våben); ellers vises attack.bonus som én linje.
    if attack.bonus_parts:
        parts += [dict(p) for p in attack.bonus_parts]
    elif attack.bonus:
        parts.append({"label": "våben (ikke-prof.)" if attack.not_proficient else "våben/magi",
                      "value": attack.bonus})
    if extra_bonus:
        parts.append({"label": "effekter", "value": extra_bonus})
    return {"total": bab + ability_mod + size_m + attack.bonus + extra_bonus, "parts": parts}


def attack_damage_breakdown(attack: Attack, ability_scores: AbilityScores,
                            extra_damage: int = 0) -> dict:
    """Navngiven opdeling af skaden (til hover). Parallel til til-hit-opdelingen.

    Skade = terning + floor(Str-mod · str_damage_mult) + damage_parts (Weapon
    Specialization — ikke Str-skaleret) + effekter — ELLER fixed_damage (spell/touch:
    kilden sætter tallet, Str/feat/effekter tæller ikke).
    Hver del har enten "die" (terning-streng, vises råt) eller "value" (heltal, vises
    med fortegn); "total" er hele skade-strengen, præcis som attack_total bygger den.
    """
    if attack.fixed_damage:
        return {"total": attack.fixed_damage,
                "parts": [{"label": "kilde (fast)", "die": attack.fixed_damage}]}

    parts = [{"label": "terning", "die": attack.base_damage}]
    str_bonus, capped = _str_damage_bonus(attack, ability_scores)
    if str_bonus != 0:
        # Vis multiplikatoren når den ikke er 1 (tohånds ×1.5, off-hånd ×0.5), så
        # spilleren kan se hvorfor Str-bidraget afviger fra sin rå modifier.
        label = "STR" if attack.str_damage_mult == 1.0 else f"STR ×{attack.str_damage_mult:g}"
        if capped:
            label += f" (mighty +{attack.str_cap})"
        parts.append({"label": label, "value": str_bonus})
    if attack.damage_parts:
        parts += [dict(p) for p in attack.damage_parts]
    if extra_damage:
        parts.append({"label": "effekter", "value": extra_damage})

    total_bonus = str_bonus + attack.damage_bonus + extra_damage
    total = attack.base_damage if total_bonus == 0 else f"{attack.base_damage}{total_bonus:+d}"
    return {"total": total, "parts": parts}


def grapple_total(bab: int, str_score: int, size: str) -> int:
    """Grapple-modifier: bab + Str-mod + den SÆRLIGE grapple-størrelses-modifier."""
    return bab + (str_score - 10) // 2 + size_mod_grapple(size)


def initiative_total(ability_scores: AbilityScores, feats: list, misc: int = 0,
                     effect_bonus: int = 0) -> int:
    """Initiativ: Dex-mod + Improved Initiative (+4 hvis feat'en haves) + misc
    + effekt-bonus (fx deafened −4)."""
    feat_bonus = 4 if "improved_initiative" in {feat_id(f).lower() for f in feats} else 0
    return ability_scores.modifier("dex") + feat_bonus + misc + effect_bonus


def monk_unarmed_attacks(level: int, size: str, flurry_penalty: int,
                         greater_flurry: bool, flurry_active: bool,
                         base_damage: str) -> list[Attack]:
    """Monkens unarmed strike og eventuelle flurry-ekstra-angreb.

    Primær: ét unarmed strike ved fuld bonus. Når flurry_active: tilføj 1 ekstra
    flurry-række (2 ved Greater Flurry). Straffen vises i ekstra-rækkernes note —
    design Mulighed A: primær-rækken vises ved fuld bonus, info-sektionen forklarer
    at straffen gælder alle angreb. base_damage er forudberegnet (fx fra refdata).
    """
    attacks: list[Attack] = []

    # Primær unarmed strike — altid til stede
    attacks.append(Attack(
        name="Unarmed strike",
        kind="melee",
        base_damage=base_damage,
        str_damage_mult=1.0,
        bonus=0,
        crit="x2",
        type="bludgeoning",
        not_proficient=False,
        note="",
        finesse=True,   # Weapon Finesse kan bruges på unarmed
    ))

    if flurry_active:
        # Flurry-straf-note til ekstra-rækkerne
        if flurry_penalty < 0:
            flurry_note = f"flurry: {flurry_penalty:+d} til alle angreb"
        else:
            flurry_note = "flurry"

        attacks.append(Attack(
            name="Unarmed strike (flurry)",
            kind="melee",
            base_damage=base_damage,
            str_damage_mult=1.0,
            bonus=flurry_penalty,
            crit="x2",
            type="bludgeoning",
            not_proficient=False,
            note=flurry_note,
            finesse=True,
        ))

        if greater_flurry:
            attacks.append(Attack(
                name="Unarmed strike (flurry 2)",
                kind="melee",
                base_damage=base_damage,
                str_damage_mult=1.0,
                bonus=flurry_penalty,
                crit="x2",
                type="bludgeoning",
                not_proficient=False,
                note=flurry_note,
                finesse=True,
            ))

    return attacks


def weapon_proficient(weapon_row: dict | None, weapon_prof: dict | None,
                      allowed: set = frozenset()) -> bool:
    """Er man proficient med våbnet? Via kategori, eksplicit liste eller house-rule.

    weapon_prof=None → ingen proficiency-data for klassen → behandl som proficient
    (vi straffer ikke noget vi ikke kender reglerne for).
    """
    if not weapon_row or weapon_prof is None:
        return True
    wid = weapon_row.get("id", "")
    if wid in allowed:
        return True
    if weapon_row.get("category") in (weapon_prof.get("categories") or []):
        return True
    return wid in (weapon_prof.get("weapons") or [])


def armor_proficient(armor_row: dict | None, armor_prof: dict | None,
                     allowed: set = frozenset()) -> bool:
    """Er man proficient med rustningen/skjoldet? Tower shield er en egen tilladelse.

    armor_prof=None → ingen data → behandl som proficient (ingen straf).
    """
    if not armor_row or armor_prof is None:
        return True
    aid = armor_row.get("id", "")
    if aid in allowed:
        return True
    if armor_row.get("type") == "shield":
        if aid == "tower_shield":
            return bool(armor_prof.get("tower_shield"))
        return bool(armor_prof.get("shields"))
    return armor_row.get("type") in (armor_prof.get("types") or [])


def proficiency_violations(weapon_prof: dict | None, armor_prof: dict | None,
                           inventory: list, db, allowed_weapons: set = frozenset(),
                           allowed_armor: set = frozenset()) -> dict:
    """Navne på equipped grej man IKKE er proficient med (til advarsler på arket).

    Returnerer {"weapons": [navne], "armor": [navne]}. En genstand med
    house_rule=True regnes altid som tilladt (DM-undtagelse). Kun wielded våben
    og worn rustning/skjold tjekkes.
    """
    bad_weapons: list[str] = []
    bad_armor: list[str] = []
    for item in inventory:
        if item.house_rule:
            continue
        if item.state == "wielded" and item.ref.startswith("weapons/"):
            w = db.get_weapon(item.ref.split("/", 1)[1])
            if w and not weapon_proficient(w, weapon_prof, allowed_weapons):
                bad_weapons.append(item.name or w["name"])
        elif item.state == "worn" and item.ref.startswith("armor/"):
            a = db.get_armor(item.ref.split("/", 1)[1])
            if a and not armor_proficient(a, armor_prof, allowed_armor):
                bad_armor.append(item.name or a["name"])
    return {"weapons": bad_weapons, "armor": bad_armor}


def armor_attack_penalty(armor_prof: dict | None, inventory: list, db,
                         allowed_armor: set = frozenset()) -> int:
    """Ekstra angrebs-straf (≤0) fordi man bærer uvant rustning/skjold.

    SRD: bærer man rustning man ikke er proficient med, rammer dens tjekstraf
    (ACP) også alle angreb. Summerer ACP for hver uvant, ikke-house-ruled del.
    """
    penalty = 0
    for item in inventory:
        if item.house_rule or item.state != "worn" or not item.ref.startswith("armor/"):
            continue
        a = db.get_armor(item.ref.split("/", 1)[1])
        if a and not armor_proficient(a, armor_prof, allowed_armor):
            penalty += int(a.get("armor_check", 0) or 0)
    return penalty
