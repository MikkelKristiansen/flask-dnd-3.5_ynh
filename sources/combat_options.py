"""Kampindstillinger — situationelle kamp-toggles ("Lag A" + "Lag B").

Dedikeret feature-modul (som summon.py/wild_shape.py): oversætter karakterens
aktive kamp-toggles (char.combat_options) til modifier-dicts (samme form som
buffs/tilstande i effects.yaml) og til en view-model til panelet i skabelonen.

Data (label/feat/scope/modifiers/note pr. option) bor i data/combat_options.yaml
og indlæses af refdata.combat_options() — dette modul indeholder ingen data,
kun opslag/oversættelse. Motoren (resolve_modifiers) rører vi ikke: options
emitterer bare almindelige modifiers ind i active_modifiers før net beregnes.

Lag B tilføjer "editable" options (Power Attack, Combat Expertise): i stedet
for en bool gemmer char.combat_options[option_id] et HELTAL N (valgt værdi).
Tilknyttede under-toggles (fx Power Attacks "tohånds") gemmes under en
namespacet nøgle "<option_id>.<toggle_navn>" som en almindelig bool.

Lag C tilføjer options der injicerer en HEL ekstra angrebs-RÆKKE i stedet for
bare et tal (Rapid Shot, Manyshot) — se extra_attacks() nedenfor. Samme
feat-gating som active_modifiers/panel; klonen bygges med dataclasses.replace,
samme mønster som TWF-klonen i rules.derive_attacks.
"""
import dataclasses

import refdata
from models import Attack


def _editable_modifiers(char, option_id: str, opt: dict, bab: int) -> list[dict]:
    """Modifiers fra én editable option (Power Attack/Combat Expertise-stil).

    N læses fra char.combat_options[option_id] (heltal ≥ 1 = til). Klampes til
    [min, cap] hvor cap enten er et fast heltal eller sentinel "bab" (karakterens
    faktiske base attack bonus). Ugyldige/ikke-heltals-værdier springes stille
    over — en korrupt/gammel karakterfil må ikke crashe arket.
    """
    raw = (char.combat_options or {}).get(option_id)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return []
    if n < 1:
        return []

    editable = opt.get("editable") or {}
    cap = editable.get("cap", n)
    cap = bab if cap == "bab" else int(cap)
    min_n = int(editable.get("min", 1))
    n = max(min_n, min(n, cap))

    mods: list[dict] = []
    for pair in opt.get("paired") or []:
        mods.append({
            "target": pair["target"], "type": pair["type"],
            "value": pair["per"] * n,
        })
    for tname, tspec in (opt.get("toggles") or {}).items():
        if not (char.combat_options or {}).get(f"{option_id}.{tname}"):
            continue
        for extra in tspec.get("extra") or []:
            mods.append({
                "target": extra["target"], "type": extra["type"],
                "value": extra["per"] * n,
            })
    return mods


def active_modifiers(char, char_feat_ids: list, bab: int = 0) -> list[dict]:
    """Modifiers fra karakterens AKTIVE kamp-toggles (char.combat_options).

    En option medtages kun hvis den er slået til OG (hvis feat-gated) karakteren
    faktisk ejer feat'en — fjerner spilleren feat'en igen uden at slukke
    toggle'en, forsvinder bonussen alligevel. Ren funktion, ingen I/O udover
    refdata-opslaget (som er indlæst i hukommelsen ved import).

    `bab` bruges kun til at opløse editable-options' "bab"-cap-sentinel.
    """
    options = refdata.combat_options()
    mods: list[dict] = []
    for option_id, opt in options.items():
        # Namespacede under-toggle-nøgler ("power_attack.two_handed") er ikke
        # selv en option i kataloget — de behandles inde i _editable_modifiers.
        value = (char.combat_options or {}).get(option_id)
        feat = opt.get("feat")
        if feat and feat not in char_feat_ids:
            continue
        if opt.get("editable"):
            mods.extend(_editable_modifiers(char, option_id, opt, bab))
        else:
            if value:
                mods.extend(opt.get("modifiers") or [])
    return mods


def extra_attacks(char, char_feat_ids: list, ranged_templates: list) -> list[Attack]:
    """Klonede Attack-objekter fra aktive options med en extra_attack-spec.

    ranged_templates = de wielded ranged-Attack-objekter (fra derive_attacks,
    fanget af character_view før attack_rows bygges). 'Primær' = den med
    højeste .bonus (stabilt: første ved lige, jf. max()'s dokumenterede
    adfærd). Feat-gated ligesom active_modifiers. Ingen ranged-våben i spil
    → returnér [] (option'en injicerer bare intet — noten på selve
    checkbox'en fortæller at der kræves en bue).
    """
    if not ranged_templates:
        return []
    primary = max(ranged_templates, key=lambda a: a.bonus)

    clones: list[Attack] = []
    for option_id, opt in refdata.combat_options().items():
        spec = opt.get("extra_attack")
        if not spec:
            continue
        feat = opt.get("feat")
        if feat and feat not in char_feat_ids:
            continue
        if not (char.combat_options or {}).get(option_id):
            continue
        to_hit = spec.get("to_hit", 0)
        bonus_parts = primary.bonus_parts
        if to_hit:
            bonus_parts = bonus_parts + [{"label": spec["label"], "value": to_hit}]
        clones.append(dataclasses.replace(
            primary,
            name=spec["label"],
            bonus=primary.bonus + to_hit,
            bonus_parts=bonus_parts,
            note=spec.get("note", ""),
        ))
    return clones


def panel(char, char_feat_ids: list, bab: int = 0) -> list[dict]:
    """View-model til "Kampindstillinger"-panelet.

    Viser hver option der er SYNLIG (generisk, eller feat-gated og feat'en
    ejes) — feat-gated options uden feat'en udelades helt (ingen grund til at
    vise en afkrydsning man ikke kan bruge). Editable options får ekstra felter
    (value/cap/min/prompt/toggles) så skabelonen kan rendere et talfelt i
    stedet for en afkrydsning.
    """
    rows = []
    for option_id, opt in refdata.combat_options().items():
        feat = opt.get("feat")
        if feat and feat not in char_feat_ids:
            continue
        editable = opt.get("editable")
        row = {
            "id": option_id,
            "label": opt.get("label", option_id),
            "note": opt.get("note", ""),
            "scope": opt.get("scope", "all"),
        }
        if editable:
            cap = editable.get("cap", 1)
            cap = bab if cap == "bab" else int(cap)
            try:
                value = int((char.combat_options or {}).get(option_id) or 0)
            except (TypeError, ValueError):
                value = 0
            row.update({
                "editable": True,
                "value": value,
                "cap": cap,
                "min": int(editable.get("min", 1)),
                "prompt": editable.get("prompt", opt.get("label", option_id)),
                "toggles": [
                    {
                        "name": tname,
                        "label": tspec.get("label", tname),
                        "on": bool((char.combat_options or {}).get(f"{option_id}.{tname}")),
                    }
                    for tname, tspec in (opt.get("toggles") or {}).items()
                ],
            })
        else:
            row.update({
                "editable": False,
                "on": bool((char.combat_options or {}).get(option_id, False)),
            })
        rows.append(row)
    return rows
