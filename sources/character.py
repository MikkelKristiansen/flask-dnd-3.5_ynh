"""Façade for D&D 3.5 karakter-modulet.

Karakter-logikken er delt op i fokuserede moduler efter ansvar:

* ``models``      — dataklasser (AbilityScores/Skill/Attack/InventoryItem/Character)
                    + validering
* ``effects``     — mekanisk effekt-motor + effekt-view-lag
* ``rules``       — beregninger (afledte tal, udledt ved render)
* ``refdata``     — statisk referencedata (racer/sprog/klasser/feats)
* ``persistence`` — fil-I/O (indlæs/gem/snapshots)

Dette modul re-eksporterer deres offentlige navne, så de mange
``import character as char_module`` / ``char_module.X(...)``-kald i app, companion
og tests virker uændret. Migrering til direkte imports kan ske senere, i ro — eller
aldrig.

Importrækkefølgen er bevidst: models og effects FØRST, fordi effects.py
re-importerer AbilityScores herfra (façade-cyklus brydes ved at AbilityScores er
bundet inden effects loades); persistence SIDST, fordi den slår dataklasser +
felt-/feat-hjælpere op via denne façade.
"""
from models import (AbilityScores, Skill, Attack, InventoryItem, Character,  # noqa: F401
                    validate_character_data)
from effects import (ABILITIES, SAVE_TARGETS, resolve_modifiers,  # noqa: F401
                     resolve_ac_bonuses, resolve_target, save_effect_bonus,
                     skill_effect_bonus, conditional_modifiers, con_temp_hp,
                     effective_ability_scores)
from refdata import (  # noqa: F401
    hit_die, skill_points_per_level, is_feat_level, is_ability_level, class_skills,
    race_data, race_ids, race_bio, class_age_group, class_speed_bonus,
    STANDARD_LANGUAGES, class_languages, race_bonus_languages,
    automatic_languages, bonus_language_pool, bonus_language_count,
    apply_racial_adjustments, level1_feat_count, class_bonus_feats,
    class_bonus_feat_choices, class_bonus_feat_pool, class_bonus_feat_ignore_prereqs,
    class_ac_ability, class_starting_gold,
    class_weapon_proficiency, class_armor_proficiency,
    WEAPON_CHOICE_FEATS, SCHOOL_CHOICE_FEATS, SPELL_SCHOOLS,
    feat_id, feat_weapon, feat_school, feat_label, owned_feat_tokens,
    spell_focus_bonus, class_cast_type, class_needs_domains,
    base_skill_points, class_can_turn_undead, class_has_wild_shape, class_wild_shape,
    feat_prereq_unmet)
from rules import (  # noqa: F401
    POINT_BUY_COST, POINT_BUY_BUDGET, point_buy_cost, point_buy_total,
    XP_THRESHOLDS, SKILL_SYNERGIES, SYNERGY_THRESHOLD, INVENTORY_STATES,
    compute_synergy_bonuses, synergy_sources, armor_check_penalty, druid_armor_violations,
    skill_total, save_total, armor_class, xp_to_next_level, xp_progress,
    active_buff_keys, attack_visible)
from attacks import (  # noqa: F401
    SIZE_MOD_ATTACK, SIZE_MOD_GRAPPLE, size_mod_attack, size_mod_grapple,
    weapon_proficient, armor_proficient, proficiency_violations, armor_attack_penalty,
    attack_total, attack_to_hit_breakdown, attack_damage_breakdown,
    grapple_total, initiative_total, derive_attacks,
    hand_usage, twf_context, two_weapon_penalty, monk_unarmed_attacks)
from items import (  # noqa: F401
    CARRIED_STATES,
    carry_limits, encumbrance_level, total_weight, weight_for_size, resolve_item,
    carried_weight, equipped_armor, encumbrance_consequences)
from spells import (  # noqa: F401
    spell_charge_key, spell_attack_damage, spell_area_damage,
    derive_spell_attacks, derive_spell_effects, spell_max_charges, active_spell_keys,
    spell_cast_info, wis_bonus_spells, spell_slots_total, spell_save_dc, spell_like_dc)
from persistence import (  # noqa: E402,F401
    SNAPSHOT_KEEP, load_character, save_character, write_character_file,
    restore_snapshot, snapshot_dir, list_snapshots, delete_character)
