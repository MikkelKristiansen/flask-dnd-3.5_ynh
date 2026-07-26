"""Blueprint: inventar (tilføj/fjern/opdatér) + noter.

_char_path importeres lazy (se routes_spells.py for hvorfor).
"""
from flask import Blueprint, jsonify, request

import catalog
import character as char_module
import db
from character_view import _inv_row

inventory_bp = Blueprint("inventory", __name__)


def _armor_slot(item, db) -> str | None:
    """'body' for en krops-rustning, 'shield' for et skjold, ellers None."""
    if not item.ref.startswith("armor/"):
        return None
    rec = db.get_armor(item.ref.split("/", 1)[1])
    if not rec:
        return None
    return "shield" if rec.get("type") == "shield" else "body"

def _enforce_armor_slots(inventory, idx, db) -> None:
    """Hård slot-håndhævelse: kun én worn krops-rustning + ét worn skjold ad gangen.

    Når post idx sættes til 'worn', flyttes enhver anden worn rustning i SAMME slot
    (body/shield) tilbage til 'backpack'. Så opstår der aldrig en ulovlig tilstand
    med to bårne rustninger — i tråd med "kun lovlige kombinationer giver lovlige tal".
    """
    item = inventory[idx]
    if item.state != "worn":
        return
    slot = _armor_slot(item, db)
    if slot is None:
        return
    for j, other in enumerate(inventory):
        if j != idx and other.state == "worn" and _armor_slot(other, db) == slot:
            other.state = "backpack"

@inventory_bp.route("/api/inventory", methods=["POST"])
def api_inventory():
    from app import _char_path
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")   # "add" | "remove"
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char      = char_module.load_character(str(path))
    inventory = list(char.inventory)
    used  = None            # "use": info om den brugte forbrugsvare (rul/buff/ladninger)
    extra = {}              # ekstra save-nøgler ud over inventory (fx buffs ved brug)

    if action == "add":
        ref   = str(data.get("ref", "")).strip()
        state = str(data.get("state", "backpack")).lower()
        if state not in char_module.INVENTORY_STATES:
            state = "backpack"
        # "worn" (rustning → AC) giver kun mening for rustning; våben/grej kan ikke
        # bæres som rustning. Coerce til "backpack" (på person).
        if state == "worn" and not ref.startswith("armor/"):
            state = "backpack"
        if ref:
            # Katalog-genstand: navn/vægt slås op via ref ved visning
            sm = data.get("str_mult")
            kwargs = dict(
                ref=ref, state=state,
                qty=max(1, int(data.get("qty", 1))),
                bonus=int(data.get("bonus", 0)),
                str_mult=(None if sm in (None, "") else float(sm)),
                notes=str(data.get("notes", "")),
            )
            # Materiale-/kvalitets-mods fra butikken (masterwork/cold iron/sølv) →
            # ekstra felter (masterwork-flag, +1 til-hit, materiale-mærkat i navn).
            table, _, oid = ref.partition("/")
            getter = {"weapons": db.get_weapon, "armor": db.get_armor}.get(table)
            record = getter(oid) if getter else None
            if record:
                kwargs.update(catalog.apply_material_overlay(record, table, data.get("mods")))
            inventory.append(char_module.InventoryItem(**kwargs))
            _enforce_armor_slots(inventory, len(inventory) - 1, db)
        else:
            name = str(data.get("name", "")).strip()
            if not name:
                return jsonify({"error": "name required"}), 400
            inventory.append(char_module.InventoryItem(
                name=name,
                weight=float(data.get("weight", 0)),
                qty=max(1, int(data.get("qty", 1))),
                notes=str(data.get("notes", "")),
                state=state,
            ))
    elif action == "remove":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(inventory):
            inventory.pop(idx)
    elif action == "update":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(inventory):
            old = inventory[idx]
            # Bevar katalog-ref; navn/vægt redigeres kun for custom.
            # qty kan gå til 0 (fx ammo brugt op); ingen negative.
            old.qty   = max(0, int(data.get("qty", old.qty)))
            old.notes = str(data.get("notes", old.notes))
            if "state" in data:
                st = str(data["state"]).lower()
                if st in char_module.INVENTORY_STATES:
                    # "worn" (rustning → AC) kun for rustning; ellers på person.
                    if st == "worn" and _armor_slot(old, db) is None:
                        st = "backpack"
                    old.state = st
                    _enforce_armor_slots(inventory, idx, db)
            if "off_hand" in data:
                old.off_hand = bool(data.get("off_hand"))
            if "double" in data:
                old.double = bool(data.get("double"))
            if "bonus" in data:
                old.bonus = int(data.get("bonus") or 0)
            if "str_mult" in data:
                sm = data.get("str_mult")
                old.str_mult = None if sm in (None, "") else float(sm)
            if "mighty" in data:
                mg = data.get("mighty")
                old.mighty = None if mg in (None, "") else int(mg)
            if "masterwork" in data:
                old.masterwork = bool(data.get("masterwork"))
            if "enhancement" in data:
                old.enhancement = int(data.get("enhancement") or 0)
            if "house_rule" in data:
                old.house_rule = bool(data.get("house_rule"))
            if not old.ref:
                old.name   = str(data.get("name", old.name))
                old.weight = float(data.get("weight", old.weight))
    elif action == "use":
        # Brug en forbrugsvare (potion/scroll/wand): kast dens spell én gang + tæl
        # ladninger ned. Buff-spells → tilføj buffen (effekt+varigheds-motoren);
        # øjeblikkelige → returnér et rulle-udtryk klienten slår i terningefeltet.
        # Ladnings-skalering (Cure 1d8+CL) bruger GENSTANDENS caster level, ikke
        # drikkerens. Engangs (charges_max ≤ 1) fjernes ved 0; wands bliver stående.
        idx = int(data.get("index", -1))
        if not (0 <= idx < len(inventory)):
            return jsonify({"error": "bad index"}), 400
        item = inventory[idx]
        table, _, oid = (item.ref or "").partition("/")
        mi = db.get_magic_item(oid) if table == "magic_items" else None
        if not mi or not mi.get("spell_id"):
            return jsonify({"error": "ikke en forbrugsvare"}), 400
        sid = str(mi["spell_id"])
        cl = int(mi.get("caster_level") or 1)
        cur = item.charges if item.charges is not None else int(mi.get("charges_max") or 1)
        if cur <= 0:
            return jsonify({"error": "tom"}), 400

        used = {"name": mi["name"]}
        eff = db.get_effect(sid)
        if eff and eff.get("kind") == "buff":
            buffs = list(char.buffs)
            buffs.append({"name": eff["name"], "spell_id": sid,
                          "affects": list(eff.get("affects") or []),
                          "note": f"fra {mi['name']}"})
            extra["buffs"] = buffs
            used["buff_added"] = eff["name"]
        else:
            info = (char_module.spell_cast_info(sid, cl, db)
                    or char_module.spell_heal_cast_info(sid, cl, db))
            if info:
                used["roll_expr"] = info["roll_expr"]
                used["roll_label"] = mi["name"]
                used["kind"] = info.get("kind")

        cur -= 1
        if cur <= 0 and int(mi.get("charges_max") or 1) <= 1:
            inventory.pop(idx)
            used["removed"] = True
        else:
            item.charges = cur
            used["charges_left"] = cur

    char_module.save_character(str(path), {"inventory": inventory, **extra})
    ab     = char.ability_scores
    weight = char_module.carried_weight(inventory, db, char.size)
    enc    = char_module.encumbrance_level(ab.str, weight, char.size)
    inv_rows = [_inv_row(i, char_module.resolve_item(i, db, char.size))
               for i in inventory]
    return jsonify({
        "inventory":  inv_rows,
        "weight":     weight,
        "enc":        enc,
        "enc_limits": char_module.carry_limits(ab.str, char.size),
        "used":       used,
    })

@inventory_bp.route("/api/notes", methods=["POST"])
def api_notes():
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    notes = str(data.get("notes", ""))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char_module.save_character(str(path), {"notes": notes})
    return jsonify({"ok": True})

