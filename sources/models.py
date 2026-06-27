"""Dataklasser + validering for D&D 3.5 karakterark.

Rene datastrukturer uden afhængigheder: ability scores, skills, angreb,
inventory-poster og selve Character — plus validering af en indlæst YAML-dict.
Beregninger, effekter og fil-I/O bor i andre moduler; her er kun formen på data.

character.py re-eksporterer disse navne (façade), så de mange char_module.Character
/ AbilityScores-kald rundt om i app/companion/persistence/tests virker uændret.
"""
from dataclasses import dataclass, field


@dataclass
class AbilityScores:
    str: int = 10
    dex: int = 10
    con: int = 10
    int: int = 10
    wis: int = 10
    cha: int = 10

    def modifier(self, ability: str) -> int:
        return (getattr(self, ability) - 10) // 2


@dataclass
class Skill:
    id: str
    ranks: float        # float: cross-class giver halve ranks
    misc: int = 0
    misc_note: str = ""  # valgfri kilde-label for misc, fx "Nature Sense" / "Gnome"


@dataclass
class Attack:
    name: str
    kind: str = "melee"            # melee | ranged | melee_touch | ranged_touch
    base_damage: str = "1d4"       # KUN terningen; Str lægges på i koden
    str_damage_mult: float = 1.0   # 1 normal · 1.5 tohånds · 0.5 off-hand · 0 ingen Str
    bonus: int = 0                 # situations-uafhængig til-hit (Weapon Focus, masterwork, magi)
    fixed_damage: str = ""         # skade sat af kilden (spell/touch); tilsidesætter base+Str
    crit: str = "x2"
    type: str = ""
    range: str = ""
    source: str = "weapon"         # weapon | spell — spell-angreb er betingede (kræver aktiv spell)
    requires: str = ""             # navn på buff der skal være aktiv før angrebet vises (tom = altid)
    not_proficient: bool = False   # våben man ikke er proficient med → −4 allerede lagt i bonus
    note: str = ""                 # kort UI-markør (fx TWF-straf "−2 TWF (off-hånd)") — info, ikke et tal


@dataclass
class InventoryItem:
    name: str = ""              # tom => navn slås op fra katalog via ref
    weight: float = 0.0         # kun for custom genstande; katalog-vægt slås op via ref
    qty: int = 1
    notes: str = ""
    ref: str = ""               # "tabel/id" i kataloget (weapons|armor|items); tom = custom
    state: str = "backpack"     # wielded | worn | backpack | stored | dropped
    bonus: int = 0              # til-hit-bonus på afledte angreb (masterwork/feat/TWF)
    str_mult: float | None = None  # override af Str-til-skade (None = default fra våbentype)
    two_handed: bool = False    # enhåndsvåben brugt tohånds → ×1,5 Str (hvis str_mult ikke sat)
    off_hand: bool = False      # våben holdt i off-hånd (two-weapon fighting) → ½ Str + TWF-straf
    double: bool = False        # dobbeltvåben (fx quarterstaff) brugt som to våben → primær + off-hånds-ende (light)
    masterwork: bool = False    # rustning/skjold: mesterværk → ACP forbedres med +1 (mod 0)
    enhancement: int = 0        # rustning/skjold: magisk +N til AC (≥1 medfører masterwork)
    house_rule: bool = False    # DM tillader trods manglende proficiency/druid-forbud → ingen straf/advarsel


@dataclass
class Character:
    name: str
    race: str
    cls: str            # 'class' er reserveret i Python
    level: int
    hp_current: int
    hp_max: int
    ability_scores: AbilityScores
    experience_points: int = 0
    saves: dict = field(default_factory=dict)
    combat: dict = field(default_factory=dict)
    skills: list = field(default_factory=list)
    feats: list = field(default_factory=list)
    attacks: list = field(default_factory=list)
    spells_prepared: dict = field(default_factory=dict)
    spells_used: dict = field(default_factory=dict)
    spells_active: dict = field(default_factory=dict)  # spells "I brug" (varighed kører) — {level: [index]}
    spell_charges: dict = field(default_factory=dict)  # ladninger tilbage pr. aktiv spell — {"level-index": antal}
    conditions: list = field(default_factory=list)
    buffs: list = field(default_factory=list)  # aktive positive effekter: {name, note, affects, spell_id?}
    languages: list = field(default_factory=list)  # kendte sprog (automatiske + valgte bonussprog)
    inventory: list = field(default_factory=list)
    gold: dict = field(default_factory=dict)
    notes: str = ""
    size: str = "medium"
    armor: str = ""             # equipped rustnings-id (slås op i armor-tabellen)
    shield: str = ""            # equipped skjold-id
    companion: dict = field(default_factory=dict)
    wild_shape: dict = field(default_factory=dict)  # {animal_used, elemental_used, current_form}
    summons: list = field(default_factory=list)  # aktive Summon Nature's Ally-væsner (tynde refs); ryddes når SNA-spellet sættes "Brugt"
    class_features: dict = field(default_factory=dict)
    deity: str = ""
    alignment: str = ""         # fx Lawful Good (blev tidligere skrevet men aldrig indlæst)
    gender: str = ""            # fri tekst (mand/kvinde) — bruges til højde/vægt-tabel
    age: str = ""               # alder i år (fri tekst, flavor)
    height: str = ""            # fx 5'10" (fri tekst, flavor)
    weight: str = ""            # fx 180 lb (fri tekst, flavor)
    racial_traits: dict = field(default_factory=dict)
    domains: list = field(default_factory=list)
    domain_spells_prepared: dict = field(default_factory=dict)  # {level: spell_id}
    domain_spells_used: dict = field(default_factory=dict)      # {level: bool}


def validate_character_data(data: object) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"Forventet YAML-dict, fik {type(data).__name__}")

    missing = [k for k in ("name", "hp", "ability_scores") if k not in data]
    if missing:
        raise ValueError(f"Manglende påkrævede felter: {', '.join(sorted(missing))}")

    hp = data.get("hp") or {}
    if not isinstance(hp, dict):
        raise ValueError(f"hp skal være et dict, fik {type(hp).__name__}")
    for sub in ("current", "max"):
        if sub not in hp:
            raise ValueError(f"hp.{sub} mangler i YAML-filen")

    ab = data.get("ability_scores") or {}
    if not isinstance(ab, dict):
        raise ValueError(f"ability_scores skal være et dict, fik {type(ab).__name__}")
    missing_ab = [a for a in ("str", "dex", "con", "int", "wis", "cha") if a not in ab]
    if missing_ab:
        raise ValueError(f"ability_scores mangler: {', '.join(missing_ab)}")
