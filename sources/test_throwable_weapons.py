"""Unit-tests for kastbare våben (thrown=1): ét angreb m/ ⇄-skift nærkamp/kastet.

Kør: python -m pytest test_throwable_weapons.py   (fra sources/)

Et kastbart våben (dagger, spear, javelin …) giver ÉN angrebsrække med en ⇄-knap
i stedet for to samtidige. item.thrown styrer tilstanden (None = våbnets natur:
nærkampsvåben→nærkamp, kastevåben→kastet). Kastet = Dex til-hit (kind=ranged) +
fuld Str til skade; et rent kastevåben (javelin) i nærkamp får SRD's improviserede
−4. Se derive_attacks/make_throwable i rules.py.
"""
import db
from character import InventoryItem, derive_attacks, AbilityScores, attack_total

_STR13_DEX15 = AbilityScores(str=13, dex=15)   # Str +1, Dex +2


def _one(ref, **item_kw):
    inv = [InventoryItem(ref=ref, state="wielded", **item_kw)]
    atks = derive_attacks(inv, db, size="medium")
    assert len(atks) == 1
    return atks[0]


def test_melee_weapon_defaults_to_melee():
    a = _one("weapons/dagger")
    assert a.kind == "melee"
    assert a.name == "Dagger (nærkamp)"
    assert a.throw_mode["current"] == 0
    assert a.range == ""   # rækkevidde skjules i nærkamp


def test_melee_weapon_thrown_uses_dex_and_full_str():
    a = _one("weapons/dagger", thrown=True)
    assert a.kind == "ranged"          # → Dex til-hit
    assert a.range == "10 ft."
    r = attack_total(a, _STR13_DEX15, bab=2, size="medium")
    assert r["to_hit"] == 4            # BAB2 + Dex2
    assert r["damage"] == "1d4+1"      # fuld Str (+1) til skade


def test_thrown_weapon_defaults_to_thrown():
    a = _one("weapons/javelin")        # weapon_class=ranged → naturlig kaste
    assert a.kind == "ranged"
    assert a.name == "Javelin (kastet)"
    assert a.throw_mode["current"] == 1


def test_thrown_weapon_in_melee_gets_improvised_penalty():
    a = _one("weapons/javelin", thrown=False)
    assert a.kind == "melee"
    assert a.not_proficient is False   # −4'en er improviserings-straffen, ikke prof
    labels = [(p["label"], p["value"]) for p in a.bonus_parts]
    assert ("ikke egnet til nærkamp", -4) in labels
    r = attack_total(a, _STR13_DEX15, bab=2, size="medium")
    assert r["to_hit"] == -1           # BAB2 + Str1 + 0 − 4


def test_two_handed_thrown_uses_single_str_not_one_and_half():
    # Spear: nærkamp tohånds ×1.5, men kastet kun ×1 (SRD kastevåben).
    strong = AbilityScores(str=16, dex=12)   # Str +3
    melee = _one("weapons/spear")
    thrown = _one("weapons/spear", thrown=True)
    assert attack_total(melee, strong, bab=2, size="medium")["damage"] == "1d8+4"   # +3 ×1.5 = +4
    assert attack_total(thrown, strong, bab=2, size="medium")["damage"] == "1d8+3"  # +3 ×1


def test_non_throwable_weapon_has_no_mode():
    a = _one("weapons/longsword")
    assert a.throw_mode is None


def test_throw_mode_carries_inventory_index():
    inv = [InventoryItem(ref="weapons/club", state="backpack"),      # idx 0 (ikke wielded)
           InventoryItem(ref="weapons/dagger", state="wielded")]     # idx 1
    a = derive_attacks(inv, db, size="medium")[0]
    assert a.throw_mode["weapon_index"] == 1
    assert a.throw_mode["count"] == 2
