// ── Inventory state ───────────────────────────────────────────────────────
let inventoryData = D.inventoryData;
const catalogData = D.catalogData;
let currentWeight = D.currentWeight;
let currentEnc    = D.currentEnc;
let encLimits     = D.encLimits;
const baseSpeed   = D.baseSpeed;


// ── Inventory ─────────────────────────────────────────────────────────────
function calcEncSpeed(base) {
  const sq = Math.floor(base / 5);
  return Math.max(5, (sq - Math.floor(sq / 3)) * 5);
}

function renderInventory() {
  const list = document.getElementById("inv-list");
  if (inventoryData.length === 0) {
    list.innerHTML = '<p style="color:var(--muted);font-size:.85rem;font-style:italic;padding:.3rem 0">Tom rygsæk</p>';
    return;
  }
  list.innerHTML = "";
  const STATE_LABEL = {wielded:"i hånden", worn:"båret", stored:"opbevaret", dropped:"droppet"};
  inventoryData.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className = "inv-row";
    const tw = (item.weight * item.qty).toFixed(1);
    const ref = item.is_ref;
    const lbl = STATE_LABEL[item.state] || "";
    const badge = lbl ? `<span class="inv-state st-${item.state}">${lbl}</span>` : "";
    // Alle genstande er klikbare → popup med info + handlinger (også katalog).
    const nameCell = `<span class="inv-editable" onclick="openItemDetail(${idx})" title="Klik for info / handlinger">${escHtml(item.name)}</span>`;
    const wtCell = ref
      ? `<span class="inv-weight" title="Vægt fra katalog (størrelses-justeret)">${tw} lbs</span>`
      : `<span class="inv-weight inv-editable" onclick="editInvField(this,${idx},'weight')" title="Klik for at redigere vægt">${tw} lbs</span>`;
    // Forbrugsvare (potion/wand): 🧪 Brug-knap + ladningstæller i stedet for antal-stepper.
    const midCell = item.consumable
      ? `<span class="inv-qty-stepper">
           <button class="inv-use" onclick="useConsumable(${idx})" title="Brug (kast dens spell + tæl ladning ned)">🧪 Brug</button>
           <span class="inv-charges" title="Ladninger tilbage">${item.charges != null ? item.charges : "?"}${item.charges != null ? " lad." : ""}</span>
         </span>`
      : `<span class="inv-qty-stepper">
           <button class="inv-step" onclick="adjQty(${idx},-1)" title="−1 (fx brug ammo)">−</button>
           <span class="inv-qty inv-editable" onclick="editInvField(this,${idx},'qty')" title="Klik for at indtaste antal">×${item.qty}</span>
           <button class="inv-step" onclick="adjQty(${idx},1)" title="+1">+</button>
         </span>`;
    let html =
      `<div class="inv-c1">${nameCell}${badge}</div>
       ${midCell}
       ${wtCell}
       <button class="inv-remove" onclick="removeItem(${idx})" title="Fjern">×</button>`;
    if (item.notes) html += `<span class="inv-notes" style="cursor:pointer" onclick="openItemDetail(${idx})">${escHtml(item.notes)}</span>`;
    row.innerHTML = html;
    list.appendChild(row);
  });
}

function itemInfoHtml(d, dtype) {
  const rows = [];
  const r = (k, v) => {
    if (v !== null && v !== undefined && v !== "")
      rows.push(`<div class="ii-row"><span class="ii-k">${k}</span><span class="ii-v">${escHtml(String(v))}</span></div>`);
  };
  if (dtype === "weapon") {
    r("Skade (M)", d.dmg_m); r("Skade (S)", d.dmg_s); r("Kritisk", d.critical);
    r("Rækkevidde", d.range_ft ? d.range_ft + " ft" : null);
    r("Type", d.damage_type);
    r("Kategori", [d.category, d.weapon_class].filter(Boolean).join(" · "));
    r("Vægt", d.weight + " lb"); r("Pris", formatCost(d.cost_cp));
  } else if (dtype === "armor") {
    r("AC-bonus", "+" + d.armor_bonus);
    r("Max Dex", (d.max_dex === null || d.max_dex === undefined) ? "—" : "+" + d.max_dex);
    r("Rustnings-tjekstraf", d.armor_check);
    r("Type", d.type);
    r("Vægt", d.weight + " lb"); r("Pris", formatCost(d.cost_cp));
  } else {
    r("Kategori", d.category);
    const bundle = d.bundle || 1;
    if (bundle > 1) {  // ammo: vægt/pris per skud
      r("Vægt", +(d.weight / bundle).toFixed(3) + " lb/skud");
      r("Pris", (d.cost_cp === null ? "—" : formatCost(Math.round(d.cost_cp / bundle))) + " /skud");
    } else {
      r("Vægt", d.weight + " lb"); r("Pris", formatCost(d.cost_cp));
    }
  }
  return `<div class="item-info">${rows.join("")}</div>`;
}

// Ammo-strip på Oversigt: ammunition fra inventaret med −/+ (styrer samme qty
// som Udstyr, så de to faner deler tæller).
function renderAmmo() {
  const sec = document.getElementById("ammo-section");
  const strip = document.getElementById("ammo-strip");
  if (!strip) return;
  const ammo = inventoryData
    .map((it, idx) => ({it, idx}))
    .filter(x => x.it.is_ammo);
  if (!ammo.length) { sec.style.display = "none"; return; }
  sec.style.display = "";
  strip.innerHTML = ammo.map(({it, idx}) =>
    `<div class="ammo-row">
       <span class="ammo-name${it.qty === 0 ? ' ammo-empty' : ''}">🎯 ${escHtml(it.name)}</span>
       <span class="inv-qty-stepper">
         <button class="inv-step" onclick="adjQty(${idx},-1)" title="−1 skud">−</button>
         <span class="inv-qty" title="Klik i Udstyr for at indtaste">${it.qty}</span>
         <button class="inv-step" onclick="adjQty(${idx},1)" title="+1 skud">+</button>
       </span>
     </div>`).join("");
}

function openItemDetail(idx) {
  const item = inventoryData[idx];
  document.getElementById("item-modal-idx").value    = idx;
  document.getElementById("item-modal-title").textContent = item.name || "Genstand";
  // Katalog-info øverst (kun ref-genstande): hent stats og vis.
  const infoBox = document.getElementById("item-modal-info");
  infoBox.innerHTML = "";
  if (item.is_ref && item.ref) {
    const [tbl, cid] = item.ref.split("/");
    const dtype = {weapons: "weapon", armor: "armor", items: "item"}[tbl];
    if (dtype)
      fetch(BASE + `/api/detail/${dtype}/${cid}`)
        .then(r => r.json())
        .then(d => { if (!d.error) infoBox.innerHTML = itemInfoHtml(d, dtype); });
  }
  document.getElementById("item-modal-name").value   = item.name;
  document.getElementById("item-modal-weight").value = item.weight;
  document.getElementById("item-modal-qty").value    = item.qty;
  document.getElementById("item-modal-notes").value  = item.notes || "";
  // Katalog-genstande: navn + vægt er låst (slås op i kataloget); kun antal/noter redigeres.
  const nameEl = document.getElementById("item-modal-name");
  const wtEl   = document.getElementById("item-modal-weight");
  nameEl.disabled = wtEl.disabled = !!item.is_ref;
  // "Worn" (rustning → AC) kun for rustning — våben/grej kan ikke bæres som rustning.
  const isArmorItem = (item.ref || "").startsWith("armor/");
  const wornOpt = document.getElementById("item-state-worn");
  wornOpt.hidden = wornOpt.disabled = !isArmorItem;
  let startState = item.state || "backpack";
  if (startState === "worn" && !isArmorItem) startState = "backpack";  // ryd gammel ulovlig tilstand
  document.getElementById("item-modal-state").value = startState;
  // Våben-felter (bonus/Str-mult) kun for våben i kataloget
  const isWeapon = (item.ref || "").startsWith("weapons/");
  document.getElementById("item-modal-weapon").style.display = isWeapon ? "flex" : "none";
  if (isWeapon) {
    document.getElementById("item-modal-bonus").value   = item.bonus || 0;
    document.getElementById("item-modal-strmult").value =
      (item.str_mult === null || item.str_mult === undefined) ? "" : item.str_mult;
    document.getElementById("item-modal-mighty").value =
      (item.mighty === null || item.mighty === undefined) ? "" : item.mighty;
  }
  // Two-weapon-felter (off-hånd/dobbeltvåben) kun for våben i kataloget
  document.getElementById("item-modal-twf").style.display = isWeapon ? "flex" : "none";
  if (isWeapon) {
    document.getElementById("item-modal-offhand").checked = !!item.off_hand;
    document.getElementById("item-modal-double").checked  = !!item.double;
  }
  // Rustnings-felter (mesterværk/magi) kun for rustning/skjold i kataloget
  const isArmor = (item.ref || "").startsWith("armor/");
  document.getElementById("item-modal-armor").style.display = isArmor ? "flex" : "none";
  if (isArmor) {
    document.getElementById("item-modal-enh").value = item.enhancement || 0;
    document.getElementById("item-modal-mwk").checked = !!item.masterwork;
  }
  // House-rule-flag: kun relevant for grej der kan rammes af proficiency (våben/rustning)
  document.getElementById("item-modal-houserule-row").style.display =
    (isWeapon || isArmor) ? "block" : "none";
  document.getElementById("item-modal-houserule").checked = !!item.house_rule;
  document.getElementById("item-modal-overlay").classList.add("open");
  (item.is_ref ? document.getElementById("item-modal-qty") : nameEl).focus();
}

function saveItemDetail() {
  const idx    = parseInt(document.getElementById("item-modal-idx").value);
  const name   = document.getElementById("item-modal-name").value.trim();
  if (!name) { document.getElementById("item-modal-name").focus(); return; }
  const weight = parseFloat(document.getElementById("item-modal-weight").value) || 0;
  const qty    = Math.max(0, parseInt(document.getElementById("item-modal-qty").value) || 0);
  const notes  = document.getElementById("item-modal-notes").value;
  const state  = document.getElementById("item-modal-state").value;
  const payload = {char: CHAR, action: "update", index: idx, name, weight, qty, notes, state};
  if ((inventoryData[idx].ref || "").startsWith("weapons/")) {
    payload.bonus = parseInt(document.getElementById("item-modal-bonus").value) || 0;
    const sm = document.getElementById("item-modal-strmult").value.trim();
    payload.str_mult = sm === "" ? "" : parseFloat(sm);
    const mg = document.getElementById("item-modal-mighty").value.trim();
    payload.mighty = mg === "" ? "" : parseInt(mg);
    payload.off_hand = document.getElementById("item-modal-offhand").checked;
    payload.double   = document.getElementById("item-modal-double").checked;
  }
  if ((inventoryData[idx].ref || "").startsWith("armor/")) {
    payload.enhancement = Math.max(0, parseInt(document.getElementById("item-modal-enh").value) || 0);
    payload.masterwork  = document.getElementById("item-modal-mwk").checked;
  }
  const ref = inventoryData[idx].ref || "";
  if (ref.startsWith("weapons/") || ref.startsWith("armor/")) {
    payload.house_rule = document.getElementById("item-modal-houserule").checked;
  }
  fetch(BASE + "/api/inventory", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(data => {
    if (!data.error) {
      // Tilstand/bonus/Str-mult kan ændre afledte angreb + AC → genindlæs (bevarer fane)
      location.reload();
    }
  });
}

function closeItemModalIfOutside(event) {
  if (event.target === document.getElementById("item-modal-overlay"))
    document.getElementById("item-modal-overlay").classList.remove("open");
}


function uploadPortrait(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("char", CHAR);
  fd.append("portrait", file);
  fetch(BASE + "/api/portrait", {method: "POST", body: fd})
    .then(r => r.json().then(d => ({ok: r.ok, d})))
    .then(({ok, d}) => {
      if (!ok || d.error) { alert((d && d.error) || "Upload mislykkedes."); input.value = ""; }
      else { location.reload(); }
    })
    .catch(() => { alert("Kunne ikke uploade portræt (netværksfejl)."); input.value = ""; });
}

// Hurtig +/− på antal (fx tæl ammo ned). Lever live, ingen reload.
function adjQty(idx, delta) {
  const item = inventoryData[idx];
  const val = Math.max(0, (parseInt(item.qty) || 0) + delta);
  if (val === item.qty) return;
  fetch(BASE + "/api/inventory", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "update", index: idx, qty: val})
  })
  .then(r => r.json())
  .then(data => { if (!data.error) updateInventoryDisplay(data); });
}

// Brug en forbrugsvare: kast dens spell én gang + tæl ladning ned. Buff-potions →
// serveren tilføjer buffen (reload viser den + opdaterede stats); øjeblikkelige →
// rul i terningefeltet og opdatér ladningstælleren live.
function useConsumable(idx) {
  const item = inventoryData[idx];
  if (item.charges != null && item.charges <= 0) { alert(item.name + " er tom."); return; }
  fetch(BASE + "/api/inventory", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "use", index: idx})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert("Kunne ikke bruge: " + data.error); return; }
    const u = data.used || {};
    if (u.buff_added) { location.reload(); return; }   // buff ændrer stats → genindlæs
    if (u.roll_expr && typeof quickRoll === "function")
      quickRoll(u.roll_expr, u.roll_label || item.name, 1);
    updateInventoryDisplay(data);                       // ladninger/fjernelse live
  });
}

// cost_cp (kobber) → læsbar gp/sp/cp; null = "—".
function formatCost(cp) {
  if (cp === null || cp === undefined) return "—";
  if (cp === 0) return "0 gp";
  const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
  return [gp && `${gp} gp`, sp && `${sp} sp`, c && `${c} cp`].filter(Boolean).join(" ");
}

function editInvField(span, idx, field) {
  const item = inventoryData[idx];
  const input = document.createElement("input");
  input.type  = "number";
  input.value = field === "qty" ? item.qty : item.weight;
  input.min   = "0";
  if (field === "weight") input.step = "0.1";
  input.style.cssText =
    "background:var(--card);border:1px solid var(--accent);color:var(--text);" +
    "font-family:Georgia,serif;width:4.5rem;padding:.2rem .3rem;border-radius:3px;" +
    "font-size:.82rem;text-align:center;";
  span.replaceWith(input);
  input.focus(); input.select();

  function save() {
    const val = field === "qty"
      ? Math.max(0, parseInt(input.value) || 0)
      : Math.max(0, parseFloat(input.value) || 0);
    fetch(BASE + "/api/inventory", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({char: CHAR, action: "update", index: idx, [field]: val})
    })
    .then(r => r.json())
    .then(data => { if (!data.error) updateInventoryDisplay(data); });
  }
  input.addEventListener("blur", save);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter")  input.blur();
    if (e.key === "Escape") renderInventory();
  });
}

function renderEncConsequences(enc) {
  const el = document.getElementById("enc-consequences");
  if (enc === "Light") { el.style.display = "none"; return; }
  el.style.display = "block";
  const maxDex  = enc === "Medium" ? "+3" : (enc === "Heavy" ? "+1" : "+0");
  const chkPen  = enc === "Medium" ? "−3" : "−6";
  const speed   = enc === "Overloaded" ? 5 : calcEncSpeed(baseSpeed);
  const run     = (enc === "Heavy" || enc === "Overloaded") ? "×3" : "×4";
  el.innerHTML = `
    <div style="font-size:.72rem;color:var(--red);font-weight:bold;margin-bottom:.3rem;
                text-transform:uppercase;letter-spacing:1px">Enc. konsekvenser (${enc})</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:.25rem;font-size:.8rem">
      <span style="color:var(--muted)">Max DEX</span><span>${maxDex}</span>
      <span style="color:var(--muted)">Check</span><span>${chkPen}</span>
      <span style="color:var(--muted)">Hastighed</span><span>${speed} ft</span>
      <span style="color:var(--muted)">Løb</span><span>${run}</span>
    </div>`;
}

function updateInventoryDisplay(data) {
  inventoryData = data.inventory;
  currentWeight = data.weight;
  currentEnc    = data.enc;
  encLimits     = data.enc_limits;

  renderInventory();
  renderAmmo();

  document.getElementById("total-weight").textContent = currentWeight.toFixed(1) + " lbs";
  const badge = document.getElementById("enc-badge");
  badge.className = "enc-badge enc-" + currentEnc;
  badge.textContent = currentEnc;

  document.getElementById("enc-limits-text").textContent =
    `Light ≤ ${Math.round(encLimits.light)} lbs · Medium ≤ ${Math.round(encLimits.medium)} lbs · Heavy ≤ ${Math.round(encLimits.heavy)} lbs`;

  renderEncConsequences(currentEnc);
}

function removeItem(idx) {
  fetch(BASE + "/api/inventory", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "remove", index: idx})
  })
  .then(r => r.json())
  // Fjernelse kan ramme et wielded-våben/worn-rustning → genindlæs (bevarer fane)
  .then(data => { if (!data.error) location.reload(); });
}

function addItem() {
  const nameEl = document.getElementById("add-name");
  const name   = nameEl.value.trim();
  if (!name) { nameEl.focus(); return; }
  const weight = parseFloat(document.getElementById("add-weight").value) || 0;
  const qty    = parseInt(document.getElementById("add-qty").value)    || 1;
  const notes  = document.getElementById("add-notes").value.trim();

  fetch(BASE + "/api/inventory", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "add", name, weight, qty, notes})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    updateInventoryDisplay(data);
    nameEl.value = "";
    document.getElementById("add-weight").value = "0";
    document.getElementById("add-qty").value    = "1";
    document.getElementById("add-notes").value  = "";
    nameEl.focus();
  });
}


// ── Tilføj fra katalog (udrustningsbutikken) ─────────────────────────────────
// Komponenten (equipment_picker.js) ejer visningen; her er kun glue: init med
// karakterens kontekst + send de valgte items til den eksisterende /api/inventory.
// Tilstanden udledes af kategori (våben=wielded, rustning=worn, gear=backpack);
// finjuster bagefter i detalje-modalen.
const SHOP_STATE_BY_CATEGORY = {weapons: "wielded", armor: "worn", items: "backpack"};

function addSelectedFromShop() {
  const sel = EquipmentPicker.getSelected();
  if (!sel.length) return;
  Promise.all(sel.map(it =>
    fetch(BASE + "/api/inventory", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({char: CHAR, action: "add", ref: it.ref,
                            state: SHOP_STATE_BY_CATEGORY[it.category] || "backpack",
                            qty: it.qty, mods: it.mods || []})
    }).then(r => r.json())
  )).then(() => {
    // Genindlæs: wielded-våben/worn-rustning påvirker afledte angreb + AC (server-side).
    location.reload();
  });
}

EquipmentPicker.init({
  base: BASE, cls: D.cls, str: D.abScores.str, size: D.size, budgetCp: D.goldCp || 0,
  baseWeight: D.currentWeight || 0,   // allerede båret vægt → butikkens enc bliver reel
});


// ── Markdown renderer ──────────────────────────────────────────────────────
function renderMd(raw) {
  if (!raw || !raw.trim())
    return '<em style="color:var(--muted)">Ingen noter endnu — tryk ✎ Rediger</em>';
  const out = [];
  let inList = false;
  for (const line of raw.split('\n')) {
    let l = escHtml(line)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>');
    if (/^#{1,4} /.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      const depth = line.match(/^(#{1,4})/)[1].length;
      out.push(`<${depth <= 2 ? 'h3' : 'h4'}>${l.replace(/^#{1,4} /, '')}</${depth <= 2 ? 'h3' : 'h4'}>`);
    } else if (/^- /.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${l.slice(2)}</li>`);
    } else if (/^-{3,}$/.test(line.trim())) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr>');
    } else if (line.trim() === '') {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<br>');
    } else {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(l + '<br>');
    }
  }
  if (inList) out.push('</ul>');
  return out.join('');
}


// ── Notes ─────────────────────────────────────────────────────────────────
let _notesRaw = D.notesRaw;
document.getElementById('notes-view').innerHTML = renderMd(_notesRaw);

function toggleNotesEdit() {
  document.getElementById('notes-textarea').value = _notesRaw;
  document.getElementById('notes-view').style.display = 'none';
  document.getElementById('notes-edit-area').style.display = 'block';
  document.getElementById('notes-edit-btn').style.display = 'none';
}
function cancelNotesEdit() {
  document.getElementById('notes-view').style.display = 'block';
  document.getElementById('notes-edit-area').style.display = 'none';
  document.getElementById('notes-edit-btn').style.display = '';
}
async function saveNotes() {
  const text = document.getElementById('notes-textarea').value;
  const r = await fetch(BASE + '/api/notes', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({char: CHAR, notes: text}),
  });
  if (r.ok) {
    _notesRaw = text;
    document.getElementById('notes-view').innerHTML = renderMd(_notesRaw);
    cancelNotesEdit();
  }
}

function restoreSnapshot(file, label) {
  if (!confirm(`Gendan tilstanden fra ${label}?\n\nDen nuværende tilstand gemmes som et snapshot først, så du kan fortryde.`)) return;
  fetch(BASE + "/api/restore", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, snapshot: file})
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) window.location.reload();
    else alert("Kunne ikke gendanne: " + (data.error || "ukendt fejl"));
  })
  .catch(() => alert("Kunne ikke gendanne (netværksfejl)."));
}

// Initial inventory render
updateInventoryDisplay({
  inventory:  inventoryData,
  weight:     currentWeight,
  enc:        currentEnc,
  enc_limits: encLimits,
});
