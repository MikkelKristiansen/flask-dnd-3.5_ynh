"""Kampindstillinger — situationelle kamp-toggles ("Lag A").

Dedikeret feature-modul (som summon.py/wild_shape.py): oversætter karakterens
aktive kamp-toggles (char.combat_options) til modifier-dicts (samme form som
buffs/tilstande i effects.yaml) og til en view-model til panelet i skabelonen.

Data (label/feat/scope/modifiers/note pr. option) bor i data/combat_options.yaml
og indlæses af refdata.combat_options() — dette modul indeholder ingen data,
kun opslag/oversættelse. Motoren (resolve_modifiers) rører vi ikke: options
emitterer bare almindelige modifiers ind i active_modifiers før net beregnes.
"""
import refdata


def active_modifiers(char, char_feat_ids: list) -> list[dict]:
    """Modifiers fra karakterens AKTIVE kamp-toggles (char.combat_options).

    En option medtages kun hvis den er slået til OG (hvis feat-gated) karakteren
    faktisk ejer feat'en — fjerner spilleren feat'en igen uden at slukke
    toggle'en, forsvinder bonussen alligevel. Ren funktion, ingen I/O udover
    refdata-opslaget (som er indlæst i hukommelsen ved import).
    """
    options = refdata.combat_options()
    mods: list[dict] = []
    for option_id, on in (char.combat_options or {}).items():
        if not on:
            continue
        opt = options.get(option_id)
        if not opt:
            continue
        feat = opt.get("feat")
        if feat and feat not in char_feat_ids:
            continue
        mods.extend(opt.get("modifiers") or [])
    return mods


def panel(char, char_feat_ids: list) -> list[dict]:
    """View-model til "Kampindstillinger"-panelet.

    Viser hver option der er SYNLIG (generisk, eller feat-gated og feat'en
    ejes) — feat-gated options uden feat'en udelades helt (ingen grund til at
    vise en afkrydsning man ikke kan bruge).
    """
    rows = []
    for option_id, opt in refdata.combat_options().items():
        feat = opt.get("feat")
        if feat and feat not in char_feat_ids:
            continue
        rows.append({
            "id": option_id,
            "label": opt.get("label", option_id),
            "note": opt.get("note", ""),
            "scope": opt.get("scope", "all"),
            "on": bool((char.combat_options or {}).get(option_id, False)),
        })
    return rows
