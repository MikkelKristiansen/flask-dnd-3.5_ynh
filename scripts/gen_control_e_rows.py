#!/usr/bin/env python3
"""
Generér spell_attacks-rækker for KONTROL-E spells (kategori E uden skade):
Charm/Hold/Dominate/Bane m.fl. rammer en fjende med en save-DC, men ruller ingen
skade. Deres save_type/save_effect kan udledes DETERMINISTISK fra det `save`-felt
der allerede står i spells.yaml — ingen SRD-genlæsning, intet gætteri.

Modsat skade-E (30 stk, kræver terning-udtræk → Sonnet) er dette rent maskineri.

To ting scriptet gør:
  1. Emitterer klar-til-indsæt YAML-rækker for de ÆGTE kontrol-E.
  2. FLAGGER de falske-E (harmless-buffs uden '(harmless)' i data, samt illusions
     med 'disbelief'-save) — de skal IKKE have en save-række, men høre til A/F.
     De foreslås til override-filen i stedet, til menneskelig bekræftelse.

Output: briefs/control-e-rows.md (YAML-blok + suspekt-tabel). Muterer intet.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import triage_spells as t

DONE = {"fireball", "lightning_bolt", "cone_of_cold", "sleep", "web"}
SAVE_EFFECTS = ("half", "negates", "partial")

# Kurateret: spells SRD giver en rigtig save, men som mekanisk er utility/buff — ikke
# fjende-kontrol. De deterministiske signaler kan ikke fange dem (saven er reel), så
# de er en menneske-vurdering. Får ingen save-række; hører til F.
CURATED_UTILITY = {
    "sanctuary": "defensiv buff — beskytter den ramte mod at blive angrebet",
    "awaken": "gør egen dyr/træ sansende — utility, ikke fjende-kontrol",
    "shadow_walk": "transport gennem Skyggeplanet — utility",
    "seeming": "illusions-forklædning af gruppe — utility",
    "veil": "illusions-forklædning — utility",
}
SRD_DIR = HERE.parent / "rules" / "srd-v3.5-md" / "spells"


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def srd_harmless_names() -> set:
    """Navne (normaliseret) på spells hvis SRD-save siger '(harmless)'.

    spells.yaml tabte '(harmless)'-mærket ved bootstrap, så harmless-buffs (Enlarge
    Person, Animal Growth …) fejl-klassificeres som E. SRD-markdown er den kanoniske
    kilde og har stadig mærket — vi henter sandheden derfra, gætter ikke."""
    out = set()
    for f in SRD_DIR.glob("spells-*.md"):
        for block in re.split(r"\n## ", f.read_text(encoding="utf-8")):
            m = re.search(r"\*\*Saving Throw:\*\*\s*(.+)", block)
            if m and "harmless" in m.group(1).lower():
                out.add(_norm(block.splitlines()[0]))
    return out


def parse_save(save: str):
    """(save_type, save_effect, effect_raw) fra FØRSTE klausul af save-strengen."""
    s = (save or "").lower()
    first = re.split(r";|,|\bor\b|\band\b", s)[0]
    stype = next((k for k in ("reflex", "fortitude", "will") if k in first), None)
    seff = next((k for k in SAVE_EFFECTS if k in first), None)
    raw = None
    if seff is None:
        m = re.search(r"(reflex|fortitude|will)\s+([a-z]+)", first)
        raw = m.group(2) if m else first.strip()
    return stype, seff, raw


def collect():
    """Returnér (genuine, suspects) blandt kontrol-E spells."""
    harmless = srd_harmless_names()
    genuine, suspects = [], []
    for sp in t.load(t.SPELLS):
        cat, conf, ev = t.classify(sp)
        if cat != "E" or sp["id"] in DONE:
            continue
        desc = t.clean(sp.get("description", "") or "")
        if t.DAMAGE_DICE.search(desc):
            continue                       # skade-E → Sonnet, ikke her
        stype, seff, raw = parse_save(sp.get("save"))
        save_l = (sp.get("save") or "").lower()

        # falske-E-signaler → hører til A/F, ikke en save-række
        buff = t.is_passive_buff(sp["name"], sp.get("school", ""), desc,
                                 sp.get("target", ""), sp.get("range", ""),
                                 sp.get("save", ""))
        # buff-signal: giver MÅLET en +N størrelses-/evne-bonus (Enlarge/Reduce/Animal
        # Growth). SRD giver dem en rigtig save, men mekanisk er de buffs (A), ikke kontrol.
        buff_bonus = re.search(
            r"\bsize bonus to (strength|dexterity|constitution)|"
            r"\benhancement bonus to (its |your )?(strength|dexterity|constitution)",
            desc, re.I)

        reason = None
        if sp["id"] in CURATED_UTILITY:
            reason = f"utility/buff (manuel vurdering): {CURATED_UTILITY[sp['id']]}"
        elif _norm(sp["name"]) in harmless:
            reason = "SRD-save er '(harmless)' → gavnlig buff (A/F), ikke fjende-kontrol"
        elif buff_bonus:
            reason = f"giver målet en gavnlig evne-/størrelses-bonus → buff (A): '{buff_bonus.group(0)}'"
        elif "object" in save_l:
            reason = "save gælder et OBJEKT (ikke en fjendtlig skabning) → utility (F)"
        elif buff and "self/ally" in buff:
            reason = f"buff på mig/allieret → A: {buff}"
        elif seff is None:
            reason = f"save-effekt '{raw}' er ikke half/negates/partial → nok illusion/utility (F)"
        elif stype is None:
            reason = f"kunne ikke udlede save-type af {sp.get('save')!r}"

        rec = {"id": sp["id"], "name": sp["name"], "save": sp.get("save"),
               "stype": stype, "seff": seff, "school": sp.get("school", ""),
               "reason": reason}
        (suspects if reason else genuine).append(rec)
    return genuine, suspects


def main():
    genuine, suspects = collect()
    genuine.sort(key=lambda r: r["name"].lower())
    suspects.sort(key=lambda r: r["name"].lower())

    L = []
    L.append("# Kontrol-E rækker (auto-genereret) — til spell_attacks.yaml\n")
    L.append("Genereret af `scripts/gen_control_e_rows.py`. Kontrol-E = kategori E "
             "uden skade (save-DC mod fjende, ingen terning). Muterer intet.\n")
    L.append(f"**{len(genuine)} ægte kontrol-E** (klar til indsæt) · "
             f"**{len(suspects)} suspekte falske-E** (hører til A/F — se nederst).\n")

    L.append("## 1) Klar til at indsætte i `data/spell_attacks.yaml`\n")
    L.append("```yaml")
    L.append("# ── Kontrol-E (område/save, ingen skade) — auto-genereret ──")
    for r in genuine:
        L.append(f"- spell_id: {r['id']}")
        L.append(f"  label: {r['name']}")
        L.append(f"  kind: save")
        L.append(f"  save_type: {r['stype']}")
        L.append(f"  save_effect: {r['seff']}")
    L.append("```\n")

    L.append("## 2) Suspekte falske-E — IKKE en save-række; flyt til override som A/F\n")
    L.append("Disse blev auto-klassificeret E men ligner buffs/utility (typisk fordi "
             "`save`-feltet mangler `(harmless)` i `spells.yaml`). Bekræft kategorien "
             "og læg dem i `data/spell_categories.yaml` under `corrected:`.\n")
    L.append("| spell_id | navn | save (i data) | hvorfor suspekt |")
    L.append("|----------|------|---------------|-----------------|")
    for r in suspects:
        save_s = str(r["save"]).replace("|", "/")
        L.append(f"| {r['id']} | {r['name']} | {save_s} | {r['reason']} |")

    out = HERE.parent / "briefs" / "control-e-rows.md"
    out.write_text("\n".join(L) + "\n")
    print(f"Skrev {out}")
    print(f"Ægte kontrol-E: {len(genuine)} · suspekte falske-E: {len(suspects)}")


if __name__ == "__main__":
    main()
