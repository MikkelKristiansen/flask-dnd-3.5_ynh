#!/usr/bin/env python3
"""
Spell-triage: klassificér SRD-spells i mekanik-kategorierne A-G fra
briefs/STRATEGY-spells.md — ud fra strukturerede felter i data/spells.yaml.

Kører deterministisk, koster ingen tokens. Formålet er at gøre 90% af
sorteringen automatisk og FLAGE de usikre, så mennesket kun review'er dem.

Kategorier (se STRATEGY-spells.md):
  A Passiv buff (ændrer MINE tal)      E Offensiv mod fjende (skade + save-DC)
  B Spell-angreb (jeg ruller)          F Ren utility/varighed
  C Summon (skaber væsen)              G Healing
  D Buff-på-våben

Output: en markdown-triage-tabel + en kort statistik. Muterer IKKE spells.yaml.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "sources"
SPELLS = SRC / "data" / "spells.yaml"
OVERRIDES_FILE = SRC / "data" / "spell_categories.yaml"

try:
    from ruamel.yaml import YAML
    _y = YAML(typ="safe")
    def load(p):
        with open(p) as f: return _y.load(f)
except Exception:
    import yaml
    def load(p):
        with open(p) as f: return yaml.safe_load(f)


_OVERRIDES = None

def overrides():
    """Menneske-verificerede kategorier: spell_id → (bogstav, proveniens).
    Proveniens 'corrected' = aktivt rettet; 'confirmed' = godkendt auto-gæt der var lav.
    Understøtter både det sektionerede format og et fladt (id: bogstav) fald-tilbage."""
    global _OVERRIDES
    if _OVERRIDES is None:
        raw = (load(OVERRIDES_FILE) or {}) if OVERRIDES_FILE.exists() else {}
        _OVERRIDES = {}
        if "corrected" in raw or "confirmed_from_low" in raw:
            for sid, cat in (raw.get("corrected") or {}).items():
                _OVERRIDES[sid] = (cat, "corrected")
            for sid, cat in (raw.get("confirmed_from_low") or {}).items():
                _OVERRIDES[sid] = (cat, "confirmed")
        else:  # fladt format = alt regnes som rettelser
            for sid, cat in raw.items():
                _OVERRIDES[sid] = (cat, "corrected")
    return _OVERRIDES


# ---------- signal-detektorer (hver returnerer True/False + evt. bevis) ----------

# skade kan skrives begge veje: "2d6 points of damage" ELLER "damage equal to 1d6"
DAMAGE_DICE = re.compile(
    r"\b\d+d\d+\b[^.\n]*?\bdamage\b|\bdamage\b[^.\n]{0,30}?\b\d+d\d+\b", re.I)
TOUCH_ATTACK = re.compile(r"\btouch attack\b", re.I)      # en ROLLE, ikke "touched" (levering)
RANGED_ATTACK = re.compile(r"\branged attack\b", re.I)
BONUS_TO_ME = re.compile(
    r"[+\-]\d+\s+\w*\s*(?:bonus|penalty)\b.*?\b(?:to|on)\b|"
    r"\btemporary hit points\b|\bdamage reduction\b|\bresistance to\b|\benergy resistance\b",
    re.I,
)
STAT_WORDS = re.compile(
    r"\b(armor class|\bac\b|attack rolls?|saving throws?|saves?|strength|dexterity|"
    r"constitution|intelligence|wisdom|charisma|skill checks?|hit points?|"
    r"initiative|speed)\b", re.I,
)


def base_school(s):
    return re.sub(r"\s*[\(\[].*", "", s or "").strip()


def full_school(s):
    return (s or "").lower()


def clean(text):
    """Fjern markdown-kursiv (_ord_, *ord*) så \\b-ordgrænser virker i regex."""
    return re.sub(r"[_*]", "", text or "")


def real_save(save):
    """En 'rigtig' save = imposet på et mål (ikke harmless, ikke tom, ikke rent 'no').
    Læser FØRSTE klausul: 'None; see text' og 'None and Will negates' → primær None.
    Returnerer (bool, er_kun_see_text)."""
    s = (save or "None").strip().lower()
    # første klausul (før ';', ' or ', ' and ')
    first = re.split(r";| or | and |,", s)[0].strip()
    if first in ("none", "no", "", "see text"):
        return False, False
    if "harmless" in first:
        return False, False
    if "see text" in first and not re.search(r"negat|half|partial", first):
        return True, True   # rigtig save men uklar type → lav konfidens
    return True, False


def is_summon(name, school, desc):
    sc = full_school(school)
    if "summoning" in sc or "calling" in sc:
        return "school:conj-summon/call"
    if re.match(r"^(summon|animate dead|create undead|create greater undead|"
                r"planar ally|planar binding|gate|lesser planar|greater planar)",
                name, re.I):
        return "name:summon-like"
    if re.search(r"\byou summon\b|\bsummons? (a|an|one|1d|2d|\d)\b|"
                 r"\bcalls? (a|an|forth)\b|appears? in an unoccupied square", desc, re.I):
        return "desc:summons-creature"
    return None


def is_healing(name, school, desc):
    if "healing" in full_school(school):
        return "school:conj-healing"
    if re.match(r"^(cure|mass cure|heal\b|regenerat|restoration|mass heal)", name, re.I):
        return "name:cure/heal"
    if re.search(r"\bcures?\b.*\d+d\d+|\bheals?\b.*\d+d\d+|regain(s)? .*hit points", desc, re.I):
        return "desc:cures-hp"
    return None


AREA_WORDS = re.compile(r"\b(radius|spread|burst|cone|\d+-?ft\.? line|line of|wall of)\b", re.I)

def is_attack_roll(name, school, desc, target, rng, has_damage):
    """B = angrebsrullet er KERNE-leveringen. Udeluk area-spells hvor 'touch attack'
    kun er en randbemærkning (Fireball rammer en åbning; Animate Rope på afstand)."""
    # en 'ray' = altid ranged touch attack som kerne (også dem der giver penalty, ikke HP-skade)
    if re.match(r"^ray of\b", name, re.I) or re.match(r"^ray\b", (target or ""), re.I):
        if TOUCH_ATTACK.search(desc) or RANGED_ATTACK.search(desc) or has_damage:
            return "target/name:ray → ranged touch attack"
    if TOUCH_ATTACK.search(desc) or RANGED_ATTACK.search(desc):
        area = AREA_WORDS.search(target or "") or AREA_WORDS.search(desc[:200])
        touch_range = (rng or "").strip().lower().startswith("touch")
        if area and not touch_range:
            return None                       # area-spell → angreb er randbemærkning
        if touch_range or has_damage:
            return "desc:touch/ranged-attack-roll (kerne)"
    return None


WEAPON_WORDS = re.compile(
    r"\b(your|the|each|this|target) (weapon|arrow|arrows|ammunition|bolt|bolts|"
    r"blade|sword|melee weapon|projectile)\b", re.I)

def is_weapon_buff(name, school, desc):
    if re.match(r"^(magic weapon|greater magic weapon|magic stone|flame arrow|"
                r"align weapon|keen edge|bless weapon|holy sword|greater magic fang|"
                r"magic fang|weapon of|lead blades)", name, re.I):
        return "name:weapon-buff"
    if WEAPON_WORDS.search(desc) and re.search(
            r"\benhancement bonus\b|\bgain(s)?\b.*\bbonus\b|\bdeals?\b.*\bextra\b.*damage|"
            r"\b\+\d+\b.*\b(weapon|attack|damage)\b", desc, re.I):
        return "desc:weapon gains bonus/damage"
    return None


def targets_me_or_ally(target, rng, save):
    t = (target or "").lower()
    r = (rng or "").lower()
    if "personal" in r or "you" == t.strip() or t.startswith("you ") or "you or" in t:
        return True
    if "harmless" in (save or "").lower():
        return True
    if re.search(r"\b(creature|creatures|ally|allies) touched\b", t) or \
       re.search(r"\btouched\b", t):
        return True
    return False


def is_passive_buff(name, school, desc, target, rng, save):
    if not BONUS_TO_ME.search(desc):
        return None
    if not STAT_WORDS.search(desc):
        return None
    # skal gavne MIG/allieret, ikke straffe en fjende
    if targets_me_or_ally(target, rng, save):
        return "desc:bonus-to-my-stats + target:self/ally"
    # buff der kan castes på allierede men target-felt utydeligt
    if re.search(r"\bmorale bonus\b|\benhancement bonus\b|\bdeflection bonus\b|"
                 r"\bresistance bonus\b|\binsight bonus\b|\bsacred bonus\b|"
                 r"\bcompetence bonus\b|\barmor bonus\b|temporary hit points",
                 desc, re.I):
        return "desc:named-buff-bonus"
    return None


# ---------- klassificér ét spell (prioriteret rækkefølge = flowchartet) ----------

def classify(sp):
    # menneske-verificeret kategori vinder altid over auto-gæt
    ov = overrides().get(sp.get("id"))
    if ov:
        cat, prov = ov
        if prov == "confirmed":
            return cat, "godkendt·var-lav", "menneske-godkendt auto-gæt (oprindeligt lav sikkerhed)"
        return cat, "verificeret", "menneske-rettet (data/spell_categories.yaml)"

    name = sp.get("name", "")
    school = sp.get("school", "")
    desc = clean(sp.get("description", "") or "")
    target = sp.get("target", "") or ""
    rng = sp.get("range", "") or ""
    save = sp.get("save", "") or "None"

    has_save, see_text = real_save(save)
    has_damage = bool(DAMAGE_DICE.search(desc))

    # 1-4: distinkte mekanik-signaler (tjekkes før den generiske save-split)
    c = is_summon(name, school, desc)
    if c:
        return "C", "høj", f"C={c}"
    g = is_healing(name, school, desc)
    if g:
        return "G", "høj", f"G={g}"
    b = is_attack_roll(name, school, desc, target, rng, has_damage)
    if b:
        return "B", "høj", f"B={b}"
    d = is_weapon_buff(name, school, desc)
    if d:
        conf = "høj" if d.startswith("name:") else "lav"
        return "D", conf, f"D={d}"

    # Divination uden skade = informations-utility, ikke offensiv — selv med Will-save
    if "divination" in full_school(school) and not has_damage:
        return "F", "lav", "F=divination-utility (save ignoreret)"

    # 5: rigtig save-DC mod et mål → E (offensiv skade/kontrol/debuff mod fjende)
    if has_save:
        conf = "lav" if see_text else "høj"
        kind = "skade" if has_damage else "kontrol/debuff"
        return "E", conf, f"E=save:{save[:20]} ({kind})"

    # ingen rigtig save herfra: harmless-buff, no-save-skade, eller ren utility
    a = is_passive_buff(name, school, desc, target, rng, save)
    if a:
        conf = "høj" if "self/ally" in a else "lav"
        return "A", conf, f"A={a}"

    # skade uden save og uden angrebsrul (Magic Missile, Acid Fog) → auto-hit-angreb ≈ B
    if has_damage:
        return "B", "lav", "B=skade uden save/angrebsrul (auto-hit?)"

    # ellers: ingen tal, ingen save, ingen skade → ren utility/varighed
    return "F", "høj", "F=ingen save/skade/angreb → utility"


# ---------- kør ----------

CAT_NAMES = {
    "A": "Passiv buff", "B": "Spell-angreb", "C": "Summon", "D": "Buff-på-våben",
    "E": "Offensiv/fjende", "F": "Utility/varighed", "G": "Healing",
}

def levels_str(sp):
    parts = []
    for cls, key in [("Wiz", "level_wizard"), ("Sor", "level_wizard"),  # sor/wiz deler
                     ("Clr", "level_cleric"), ("Drd", "level_druid"),
                     ("Brd", "level_bard"), ("Rgr", "level_ranger"),
                     ("Pal", "level_paladin")]:
        pass
    out = []
    for label, key in [("Wiz", "level_wizard"), ("Clr", "level_cleric"),
                       ("Drd", "level_druid"), ("Brd", "level_bard"),
                       ("Rgr", "level_ranger"), ("Pal", "level_paladin")]:
        v = sp.get(key)
        if v not in (None, "", []):
            out.append(f"{label}{v}")
    return " ".join(out) or "—"


def main():
    data = load(SPELLS)
    rows = []
    from collections import Counter
    counts = Counter()
    for sp in data:
        cat, conf, ev = classify(sp)
        counts[cat] += 1
        rows.append((cat, conf, sp.get("name", ""), levels_str(sp),
                     base_school(sp.get("school", "")),
                     (sp.get("save") or "None"), ev))

    rows.sort(key=lambda r: (r[0], r[2].lower()))

    out = HERE.parent / "briefs" / "spell-triage.md"
    lines = []
    lines.append("# Spell-triage (auto-genereret) — kategorier A-G\n")
    lines.append("Genereret af `scripts/triage_spells.py` ud fra `data/spells.yaml`. "
                 "Muterer ikke data. Se `briefs/STRATEGY-spells.md` for kategori-definitioner.\n")
    lines.append("**Arbejdsgang:** stol på `høj`-konfidens rækker; review kun `lav`. "
                 "Ret evt. kolonnen `kat` i hånden — signalerne viser hvorfor scriptet gættede.\n")
    lines.append("## Fordeling\n")
    lines.append("| Kat | Betydning | Antal |")
    lines.append("|-----|-----------|-------|")
    for c in "ABCDEFG":
        lines.append(f"| {c} | {CAT_NAMES[c]} | {counts.get(c,0)} |")
    n_low = sum(1 for r in rows if r[1] == "lav")
    n_corr = sum(1 for r in rows if r[1] == "verificeret")
    n_conf = sum(1 for r in rows if r[1] == "godkendt·var-lav")
    lines.append(f"\n**{len(rows)} spells i alt · {n_corr} menneske-rettet · "
                 f"{n_conf} godkendt (var lav — verificér ved spiltest) · "
                 f"{n_low} stadig `lav`.** Menneske-sandhed i `data/spell_categories.yaml`.\n")

    lines.append("## Sådan review'er du (spar tid)\n")
    lines.append("- **`høj`-konfidens: stol på dem.** Stikprøve bekræftede at fx hele "
                 "B-høj (touch/ray-angreb) og G (healing) er rene.\n")
    lines.append("- **`lav`-konfidens: kun disse skal øjne på.** Typiske mønstre:\n")
    lines.append("  - Utility-spells der nævner *falde-skade* o.l. → auto-gættet **B**, "
                 "flip til **F** (Fly, Teleport, Air Walk, Meld Into Stone).\n")
    lines.append("  - Ægte no-save-skade → **B** er rigtigt (Magic Missile, Meteor Swarm).\n")
    lines.append("  - Divination med Will-save → sat til **F** (utility); som regel rigtigt.\n")
    lines.append("## Kendte begrænsninger (rod i kilde-data, ikke i scriptet)\n")
    lines.append("Under triagen fandt scriptet nogle **datafejl i `data/spells.yaml`** værd at rette:\n")
    lines.append("- Nogle klassiske *harmless* buffs mangler `(harmless)` i `save`-feltet, "
                 "så de fejlklassificeres som **E** i stedet for **A/F** "
                 "(fx *Enlarge/Reduce Person*, *Animal Growth*, *Sanctuary*). "
                 "SRD har `(harmless)` — feltet bør suppleres.\n")
    lines.append("- Enkelte enchantments mangler `save` HELT i data (fx *Charm Monster* "
                 "burde være `Will negates`) → lander fejlagtigt i **F**. Bør tilføjes.\n")
    lines.append("- `Wall of *`/konjurationer med `save: See text` er sat til **F**; "
                 "afgør selv om en enkelt hører til **E**.\n")
    lines.append("## Alle spells\n")
    lines.append("| kat | konf | navn | niveauer | skole | save | signaler |")
    lines.append("|-----|------|------|----------|-------|------|----------|")
    for cat, conf, name, lvl, school, save, ev in rows:
        ev_s = ev.replace("|", "/")
        save_s = str(save).replace("|", "/")[:24]
        lines.append(f"| {cat} | {conf} | {name} | {lvl} | {school} | {save_s} | {ev_s} |")

    out.write_text("\n".join(lines) + "\n")
    print(f"Skrev {out}")
    print("Fordeling:", dict(sorted(counts.items())))
    print(f"Rettet: {n_corr} · godkendt-var-lav: {n_conf} · stadig lav: {n_low}/{len(rows)}")


if __name__ == "__main__":
    main()
