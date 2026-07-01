"""Klasseevner → klikbar visnings-model.

Ét ansvar: oversæt en karakters rå ``class_features`` (navn → beskrivelse) til en
liste af rækker, hvor hver evne evt. peger på en forklaring man kan klikke frem
via præcis den samme ``/api/detail/ability``-infrastruktur som wild shape bruger.

Selve SRD-teksten bor i ``data/special_abilities.yaml`` (slås op via db); her bor
kun navn→slug-normaliseringen + fallback-reglen: kendes slug'en ikke i kataloget,
vises evnen uden klik (ingen 404), ligesom i dag.

Normaliseringen genbruger ``special_abilities._slug`` — samme regel som animal-
statblokke bruger ("Rage 3/day" → ``rage``) — så de to lag ikke driver fra
hinanden. Kun de rå navne der *over-splitter* eller optræder i to stavemåder
samles her til ét kanonisk id.
"""
from special_abilities import slug_from_label

# Rå klasseevne-navn (efter _slug) → kanonisk special_abilities-id.
# Grunde: level-suffikser der ikke fanges af tal-reglen ("any distance"),
# navne-inkonsistenser i kilden, og ranger'ens "Nth Favored Enemy"-rækker der
# alle er den samme evne.
_ALIAS = {
    "slow_fall_any_distance": "slow_fall",
    "turn_or_rebuke_undead":  "turn_undead",
    "thousand_faces":         "a_thousand_faces",
    "1st_favored_enemy":      "favored_enemy",
    "2nd_favored_enemy":      "favored_enemy",
    "3rd_favored_enemy":      "favored_enemy",
    "4th_favored_enemy":      "favored_enemy",
    "5th_favored_enemy":      "favored_enemy",
}


def feature_slug(name: str) -> str:
    """Rå klasseevne-navn → special_abilities-slug.

    'Rage 3/day' → 'rage' · 'Sneak Attack +7d6' → 'sneak_attack' ·
    'Slow Fall any distance' → 'slow_fall' (via alias).
    """
    slug = slug_from_label(name)
    return _ALIAS.get(slug, slug)


def feature_rows(class_features: dict, known_ids: set) -> list[dict]:
    """→ [{'name', 'val', 'slug'}] til template'en.

    ``slug`` sættes kun når forklaringen findes i kataloget (``known_ids``);
    ellers ``None`` ⇒ template'en viser evnen uden klik (graceful fallback).
    """
    rows = []
    for name, val in class_features.items():
        slug = feature_slug(name)
        rows.append({
            "name": name,
            "val":  val,
            "slug": slug if slug in known_ids else None,
        })
    return rows
