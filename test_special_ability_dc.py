"""Save-DC'er på medfødte special-evner + Weapon Finesse-valget (SRD v3.5).

Kør: python -m pytest test_special_ability_dc.py   (fra repo-roden)

Tre ting sikres:

  1. DC-formlen 10 + ½HD + ability-mod reproducerer SRD-printet for HVER evne i
     kataloget der er markeret med en dc_ability. Det er vagten mod en forkert
     markering: sætter nogen dc_ability: cha på burn, falder testen med det samme,
     fordi de rå DC'er i animals.yaml så ikke længere kan genskabes.

  2. En buff der hæver Str/Con (Augment Summoning) slår igennem BÅDE på DC'en og
     på til-hit — det var to konkrete fejl: en augmenteret Small Fire Elemental
     viste Con 14 sammen med en Con 10-DC, og slog med Dex selv om Str var højere.

  3. Companion-fanen regner på samme måde. Her flytter DC'en sig af TO grunde:
     druide-niveauet giver bonus-HD (½HD-leddet stiger), og dyret kan være buffet
     (Bear's Endurance på en vipers Con-baserede gift).
"""
import re

import companion
import db
import special_abilities as sa
import summon


def _mod(score: int) -> int:
    return (score - 10) // 2


def _dc_in(label: str) -> int | None:
    m = re.search(r"DC\s*(\d+)", label, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _marked_abilities() -> dict[str, str]:
    """Alle katalog-evner der har en dc_ability: {slug: ability}."""
    out = {}
    for a in db.get_all_animals():
        for tok in sa._split_tokens(a.get("special_attacks")):
            slug = sa._slug(tok)
            rec = db.get_special_ability(slug) or {}
            if rec.get("dc_ability"):
                out[slug] = rec["dc_ability"]
    return out


# ── 1. Formlen skal kunne genskabe det rå SRD-print ─────────────────────────

def test_formula_reproduces_every_printed_dc():
    """Uden buffs skal hver markeret evne give præcis den DC der står i data.

    Det er den egentlige validering af dc_ability-markeringerne: DC'erne i
    animals.yaml er skrevet af fra SRD, så hvis 10 + ½HD + mod rammer dem alle,
    er både formlen og valget af ability rigtigt.
    """
    marked = _marked_abilities()
    assert marked, "ingen evner er markeret med dc_ability — er databasen seedet?"

    checked = 0
    for animal in db.get_all_animals():
        for tok in sa._split_tokens(animal.get("special_attacks")):
            slug = sa._slug(tok)
            if slug not in marked:
                continue
            printed = _dc_in(tok)
            if printed is None:
                continue
            expected = sa.ability_dc(animal["base_hd"], _mod(animal[marked[slug]]))
            assert printed == expected, (
                f"{animal['id']}/{slug}: data siger DC {printed}, "
                f"formlen giver {expected} (ability {marked[slug]})")
            checked += 1
    assert checked >= 40, f"forventede mindst 40 DC'er at tjekke, fandt {checked}"


def test_unbuffed_summon_matches_raw_statblock():
    """Uden augment skal et summonet væsens viste DC være det rå SRD-tal."""
    s = summon.build_summon({"creature": "elemental_fire_small"}, db)
    assert _dc_in(s["special_attacks"][0]["label"]) == 11


# ── 2. Augment Summoning skal slå igennem på DC og til-hit ──────────────────

def test_augment_raises_con_based_dc():
    """Small Fire Elemental: burn er Con-baseret → Con 10→14 løfter DC 11→13."""
    s = summon.build_summon(
        {"creature": "elemental_fire_small", "augment": True}, db)
    assert s["abilities"]["con"] == 14
    burn = s["special_attacks"][0]
    assert burn["dc_ability"] == "con"
    assert burn["dc"] == 13                    # 10 + ½·2 HD + Con-mod 2
    assert _dc_in(burn["label"]) == 13         # og teksten viser samme tal


def test_augment_raises_str_based_dc():
    """Small Air Elemental: whirlwind er Str-baseret → Str 10→14 løfter DC 11→13."""
    s = summon.build_summon(
        {"creature": "elemental_air_small", "augment": True}, db)
    whirl = [e for e in s["special_attacks"] if e["slug"] == "whirlwind"][0]
    assert whirl["dc_ability"] == "str"
    assert _dc_in(whirl["label"]) == 13


def test_dc_rewrite_keeps_the_rest_of_the_label():
    """Kun DC-tallet må ændres — skade-terningen i teksten skal stå urørt."""
    s = summon.build_summon(
        {"creature": "elemental_fire_small", "augment": True}, db)
    assert s["special_attacks"][0]["label"] == "Burn (1d4 fire, Reflex DC 13)"


def test_unmarked_ability_keeps_its_printed_dc():
    """Evner uden dc_ability rører buffs ikke — de står som skrevet i data.

    Avoralens fear aura er Cha-baseret, og Augment Summoning giver hverken Cha
    eller noget andet der ændrer den. Vagten mod at genberegningen løber løbsk og
    skriver nye tal ind i evner vi ikke har markeret.
    """
    s = summon.build_summon({"creature": "avoral", "augment": True}, db)
    aura = [e for e in s["special_attacks"] if e["slug"] == "fear_aura"][0]
    assert aura["dc_ability"] is None
    assert aura["dc"] is None
    assert _dc_in(aura["label"]) == 17          # uændret fra animals.yaml


# ── 3. Companion: DC'en følger bonus-HD OG buffs ────────────────────────────

def _companion(creature_id, bonus_hd=0, modifiers=None):
    """Byg et ledsager-statblok direkte fra et basis-dyr (uden karakter-lag)."""
    deltas = {"bonus_hd": bonus_hd, "na_bonus": 0, "bonus_tricks": 0,
              "specials": [], "str_bonus": 0, "dex_bonus": 0,
              "int_set": None, "level_label": "test"}
    return companion.advance_companion(
        db.get_animal(creature_id), deltas, db, modifiers or [])


def test_companion_dc_matches_srd_at_base():
    """Uden bonus-HD og buffs skal en Medium Viper vise SRD's Fort DC 11."""
    s = _companion("viper_medium")
    assert s["total_hd"] == 2
    assert _dc_in(s["special_attacks"][0]["label"]) == 11


def test_companion_dc_follows_bonus_hd():
    """Companion-bonus-HD hæver DC'en: 2 → 4 HD giver ½HD 1 → 2, altså DC 11 → 12."""
    s = _companion("viper_medium", bonus_hd=2)
    assert s["total_hd"] == 4
    assert _dc_in(s["special_attacks"][0]["label"]) == 12


def test_companion_dc_follows_con_buff():
    """Bear's Endurance (+4 Con) hæver den Con-baserede gift-DC med 2."""
    bear = [{"target": "con", "type": "enhancement", "value": 4}]
    s = _companion("viper_medium", bonus_hd=2, modifiers=bear)
    assert s["abilities"]["con"] == 15
    assert _dc_in(s["special_attacks"][0]["label"]) == 14      # 10 + 2 + 2


def test_companion_abilities_are_structured_like_summon():
    """Companion-fanen skal have samme klikbare form som summon-fanen."""
    s = _companion("viper_medium")
    entry = s["special_attacks"][0]
    assert entry["slug"] == "poison"
    assert entry["description"]                    # katalog-tekst → tooltip
    assert isinstance(s["special_qualities"], list)


# ── 4. Weapon Finesse er et valg, ikke en tvang ─────────────────────────────

def test_finesse_creature_switches_to_str_when_augmented():
    """Small Fire Elemental (Dex 13): uden augment slås med Dex, med augment Str.

    SRD: Weapon Finesse lader dig bruge Dex "instead of" Str — væsenet tager den
    bedste. Str 14 (+2) slår Dex 13 (+1), så til-hit går +3 → +4.
    """
    raw = summon.build_summon({"creature": "elemental_fire_small"}, db)
    aug = summon.build_summon(
        {"creature": "elemental_fire_small", "augment": True}, db)

    assert raw["attacks"][0]["to_hit"] == 3     # bab1 + Dex1 + size1
    assert raw["attacks"][0]["hit_parts"][1]["label"] == "DEX"

    assert aug["attacks"][0]["to_hit"] == 4     # bab1 + Str2 + size1
    assert aug["attacks"][0]["hit_parts"][1]["label"] == "STR"
    assert aug["attacks"][0]["damage"] == "1d4+3"   # eneste primære → ×1,5 Str


def test_finesse_creature_keeps_dex_when_dex_still_higher():
    """Small Air Elemental (Dex 17): Str 14 (+2) slår ikke Dex 17 (+3) → +5 begge veje.

    Modstykket til testen ovenfor: buffen må ikke tvinge Str igennem når Dex er bedst.
    """
    raw = summon.build_summon({"creature": "elemental_air_small"}, db)
    aug = summon.build_summon(
        {"creature": "elemental_air_small", "augment": True}, db)
    assert raw["attacks"][0]["to_hit"] == 5     # bab1 + Dex3 + size1
    assert aug["attacks"][0]["to_hit"] == 5     # uændret — Dex er stadig bedst
    assert aug["attacks"][0]["hit_parts"][1]["label"] == "DEX"
    assert aug["attacks"][0]["damage"] == "1d4+3"   # skade bruger ALTID Str
