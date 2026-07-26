// ── Barbarian Rage: aktiverbar klasse-feature via buff-motoren (spell_id "rage") ─
// Til/fra-knap. Aktiv rage er bare en buff på karakteren; al mekanik (str/con-kaskade,
// temp-HP, Will, AC) kommer fra effekt-posten i data/effects.yaml.
function toggleRage() {
  const idx = charBuffs.findIndex(b => b.spell_id === "rage");
  if (idx >= 0) {
    removeBuff("character", idx);            // afslut rage
    return;
  }
  fetch(BASE + "/api/buffs", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "add", buff: {
      name: "Rage", spell_id: "rage", affects: ["str", "con", "save", "ac", "hp"],
      note: "+4 Str, +4 Con, +2 morale Will, −2 AC. Varighed 3 + ny Con-mod runder."
    }})
  }).then(() => location.reload());
}


// ── Paladin: Smite Evil + Lay on Hands (dag-tællere, nulstilles ved "Ny dag") ──
function useSmite() {
  fetch(BASE + "/api/paladin", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "smite"})
  }).then(r => r.json()).then(d => { if (d.error) alert(d.error); else location.reload(); });
}

function useLayOnHands() {
  const pi = D.paladinInfo;
  if (!pi || pi.lay_remaining < 1) return;
  const missing = Math.max(0, HP_MAX - hpCurrent);
  const suggested = missing > 0 ? Math.min(pi.lay_remaining, missing) : pi.lay_remaining;
  const raw = prompt(`Hvor mange HP vil du helbrede dig selv? (${pi.lay_remaining} tilbage i puljen)`, suggested);
  if (raw === null) return;
  const n = parseInt(raw, 10);
  if (isNaN(n) || n <= 0) return;
  fetch(BASE + "/api/paladin", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "lay_on_hands", amount: n})
  }).then(r => r.json()).then(d => { if (d.error) alert(d.error); else location.reload(); });
}


// ── Gold ──────────────────────────────────────────────────────────────────
function editGold(coin) {
  const valEl = document.getElementById("gold-val-" + coin);
  if (!valEl) return;
  const current = parseInt(valEl.textContent) || 0;
  const input = document.createElement("input");
  input.type  = "number";
  input.value = current;
  input.min   = "0";
  input.style.cssText =
    "background:var(--card);border:1px solid var(--accent);color:var(--text);" +
    "font-family:Georgia,serif;width:4.5rem;padding:.2rem .3rem;border-radius:3px;" +
    "font-size:.85rem;text-align:center;font-weight:bold;";
  valEl.replaceWith(input);
  input.focus(); input.select();

  function save() {
    const newVal = Math.max(0, parseInt(input.value) || 0);
    fetch(BASE + "/api/gold", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({char: CHAR, coin, value: newVal})
    })
    .then(r => r.json())
    .then(data => {
      if (data.error) return;
      // Rebuild the gold val span
      const span = document.createElement("span");
      span.className = "gold-val";
      span.id = "gold-val-" + coin;
      span.title = "Klik for at redigere";
      span.textContent = data.gold[coin] ?? newVal;
      span.onclick = () => editGold(coin);
      input.replaceWith(span);
    });
  }
  input.addEventListener("blur", save);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter")  input.blur();
    if (e.key === "Escape") {
      const span = document.createElement("span");
      span.className = "gold-val";
      span.id = "gold-val-" + coin;
      span.title = "Klik for at redigere";
      span.textContent = current;
      span.onclick = () => editGold(coin);
      input.replaceWith(span);
    }
  });
}


// ── XP ────────────────────────────────────────────────────────────────────
function addXp() {
  const input = document.getElementById("xp-input");
  const delta = parseInt(input.value) || 0;
  if (delta === 0) return;
  fetch(BASE + "/api/xp", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, delta})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    const info = data.xp_info;
    const textEl = document.getElementById("xp-text");
    if (textEl) textEl.textContent = `${info.xp} / ${info.next ?? "MAX"}`;
    const bar = document.getElementById("xp-bar");
    if (bar) {
      bar.style.width = info.pct + "%";
      bar.className = "bar-fill " + (info.ready ? "xp-ready" : "xp-fill");
    }
    const btn = document.getElementById("xp-levelup-btn");
    if (btn) btn.style.display = info.ready ? "inline" : "none";
    input.value = "";
    input.focus();
  });
}


// ── Ny dag ────────────────────────────────────────────────────────────────
function newDay() {
  if (!confirm("Nulstil alle brugte spells? (Forberedelse bevares)")) return;
  fetch(BASE + "/api/newday", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR})
  })
  .then(r => r.json())
  .then(() => {
    // Clear all spell usage visually
    spellsUsed = {};
    document.querySelectorAll(".spell-row").forEach(row => {
      row.classList.remove("used");
      const status = row.querySelector(".spell-status");
      if (status) { status.textContent = "Ledig"; status.className = "spell-status free"; }
    });
    Object.keys(slotTotals).forEach(lvl => updatePips(parseInt(lvl)));
    // Update slot counters
    Object.entries(slotTotals).forEach(([lvl, total]) => {
      const el = document.getElementById("slots-" + lvl);
      if (el) el.textContent = total + " / " + total;
      // Spontane castere: nulstil slot-puljen pr. niveau (alt ledigt igen).
      const ks = document.getElementById("known-slots-" + lvl);
      if (ks) ks.textContent = total + "/" + total;
    });
    // Paladin: nulstil dagens Smite-/Lay-on-Hands-tællere visuelt (serveren har
    // allerede nulstillet dem). Knapperne re-aktiveres ved næste reload.
    if (D.paladinInfo) {
      const sm = document.getElementById("smite-remaining");
      if (sm) sm.textContent = D.paladinInfo.smite_per_day;
      const lay = document.getElementById("lay-remaining");
      if (lay) lay.textContent = D.paladinInfo.lay_pool;
    }
    // Wild Shape: serveren har nulstillet dagens brug (wild_shape: {}); sæt
    // "brug tilbage"-tælleren til fuld igen (= dagens maks) uden reload.
    ["animal", "elemental"].forEach(kind => {
      const left = document.getElementById("ws-" + kind + "-left");
      const uses = document.getElementById("ws-" + kind + "-uses");
      if (left && uses) left.textContent = uses.textContent;
    });
  });
}


// ── Level-up ───────────────────────────────────────────────────────────────
const luBase       = D.luBase;
const allFeats     = D.allFeats;
const allSkillsDB  = D.allSkillsDB;
const clsSkillSet  = new Set(D.clsSkills);
const charFeatIds  = new Set(D.charFeatIds);
const abScores     = D.abScores;

// Current skill ranks map — mutable for the modal session
const baseRanks = {};
Object.assign(baseRanks, D.baseRanks);

let luHpRoll      = 0;
let luSkillDeltas = {};   // {id: delta float}
let luFeat        = null;
let luFeatWeapon  = "";   // valgt våben for våben-feats (Weapon Focus m.fl.)
let luFeatSchool  = "";   // valgt troldskole for skole-feats (Spell Focus m.fl.)
// Bonus-kampfeat (fx fighter) — separat valg, kun fra fighter_bonus-puljen.
let luBonusFeat       = null;
let luBonusFeatWeapon = "";
let luBonusFeatSchool = "";
let luAbBoost     = null;
const LU_WEAPON_CHOICE_FEATS = ['weapon_focus','weapon_specialization','improved_critical'];
const LU_SCHOOL_CHOICE_FEATS = ['spell_focus','greater_spell_focus'];
let luShownSkills = [];   // ordered list of skill IDs shown in modal

function rpc(sid)  { return clsSkillSet.has(sid) ? 1.0 : 0.5; }
function maxR(sid) { const n = luBase.new_level; return clsSkillSet.has(sid) ? n+3 : Math.floor((n+3)/2); }

function luSPUsed() {
  return Object.entries(luSkillDeltas).reduce((acc,[sid,d]) =>
    acc + (d > 0 ? Math.round(d / rpc(sid)) : 0), 0);
}

function openLevelUpModal() {
  luHpRoll = 0; luSkillDeltas = {}; luFeat = null; luFeatWeapon = ""; luFeatSchool = ""; luAbBoost = null;
  luBonusFeat = null; luBonusFeatWeapon = ""; luBonusFeatSchool = "";
  document.getElementById("lu-feat-weapon").style.display = "none";
  document.getElementById("lu-feat-school").style.display = "none";
  document.getElementById("lu-bonus-feat-weapon").style.display = "none";
  document.getElementById("lu-bonus-feat-school").style.display = "none";
  // Vis kun skills man allerede har ranks i — resten tilføjes via dropdownen.
  luShownSkills = Object.keys(baseRanks).filter(sid => baseRanks[sid] > 0);
  document.getElementById("lu-hp-manual").value = "";
  renderLuModal();
  document.getElementById("lu-overlay").classList.add("open");
}

function renderLuModal() {
  const nl = luBase.new_level;
  document.getElementById("lu-title").textContent =
    `${D.cls} ${luBase.current_level} → ${nl}`;
  document.getElementById("lu-hd").textContent  = luBase.hit_die;
  document.getElementById("lu-con").textContent = (luBase.con_modifier >= 0 ? "+" : "") + luBase.con_modifier;

  updateLuHpDisplay();
  updateLuSpHeader();
  renderLuSkills();
  renderNewSkillSel();

  const featSec = document.getElementById("lu-feat-sec");
  featSec.style.display = luBase.feat_level ? "block" : "none";
  if (luBase.feat_level) {
    document.getElementById("lu-feat-lvl").textContent = nl;
    filterLuFeats();
  }

  const bonusFeatSec = document.getElementById("lu-bonus-feat-sec");
  bonusFeatSec.style.display = luBase.bonus_feat_level ? "block" : "none";
  if (luBase.bonus_feat_level) {
    document.getElementById("lu-bonus-feat-lvl").textContent = nl;
    filterLuBonusFeats();
  }

  const abSec = document.getElementById("lu-ab-sec");
  abSec.style.display = luBase.ability_level ? "block" : "none";
  if (luBase.ability_level) renderLuAbBtns();

  const ftSec = document.getElementById("lu-features-sec");
  if (luBase.new_features && luBase.new_features.length) {
    ftSec.style.display = "block";
    document.getElementById("lu-features-list").innerHTML =
      luBase.new_features.map(f => `• ${escHtml(f)}`).join("<br>");
  } else {
    ftSec.style.display = "none";
  }
  document.getElementById("lu-warning").textContent = "";
}

function updateLuHpDisplay() {
  const el = document.getElementById("lu-hp-total");
  if (luHpRoll > 0) {
    const gained = Math.max(1, luHpRoll + luBase.con_modifier);
    el.textContent = `= +${gained} HP`;
  } else {
    el.textContent = "";
  }
}

function updateLuSpHeader() {
  const left = luBase.skill_points - luSPUsed();
  document.getElementById("lu-sp-header").textContent =
    `Skill Points — ${left} / ${luBase.skill_points} tilbage`;
}

function rollLuHp() {
  fetch(BASE + `/api/roll/1d${luBase.hit_die}`)
  .then(r => r.json())
  .then(d => {
    luHpRoll = d.rolls[0];
    document.getElementById("lu-hp-manual").value = luHpRoll;
    document.getElementById("lu-roll-result").textContent = `Rullede: ${luHpRoll}`;
    updateLuHpDisplay();
  });
}

function setLuHpManual(val) {
  const n = parseInt(val);
  if (n >= 1) { luHpRoll = n; updateLuHpDisplay(); }
}

function renderLuSkills() {
  const cont = document.getElementById("lu-skill-rows");
  cont.innerHTML = "";
  luShownSkills.forEach(sid => {
    const base  = baseRanks[sid] || 0;
    const delta = luSkillDeltas[sid] || 0;
    const total = base + delta;
    const mx    = maxR(sid);
    const isCC  = !clsSkillSet.has(sid);
    const info  = allSkillsDB.find(s => s.id === sid);
    const name  = info ? info.name : sid;
    const spLeft = luBase.skill_points - luSPUsed();
    const canAdd = total < mx && spLeft >= 1;
    const canSub = delta > 0;

    const row = document.createElement("div");
    row.className = "lu-skill-row";
    row.innerHTML =
      `<span style="cursor:help" onmouseenter="showSkillTooltip('${sid}',this)" onmouseleave="hideSpellTooltip()">${escHtml(name)}${isCC ? '<span style="color:var(--muted);font-size:.72rem"> CC</span>' : ""}</span>
       <span style="display:flex;align-items:center;gap:.35rem">
         <button class="lu-pm" onclick="adjLuSkill('${sid}',-${rpc(sid)})" ${canSub?"":"disabled"}>−</button>
         <span style="min-width:3.2rem;text-align:center;font-size:.83rem">
           ${base}${delta?`<span style="color:var(--green)"> +${delta}</span>`:""}
         </span>
         <button class="lu-pm" onclick="adjLuSkill('${sid}',${rpc(sid)})" ${canAdd?"":"disabled"}>+</button>
         <span style="color:var(--muted);font-size:.72rem;min-width:2rem">/${mx}</span>
       </span>`;
    cont.appendChild(row);
  });
}

function adjLuSkill(sid, d) {
  const base  = baseRanks[sid] || 0;
  const cur   = luSkillDeltas[sid] || 0;
  const next  = Math.round((cur + d) * 10) / 10;
  if (next < 0) return;
  if (base + next > maxR(sid)) return;
  // SP check
  const costCur  = cur  > 0 ? Math.round(cur  / rpc(sid)) : 0;
  const costNext = next > 0 ? Math.round(next / rpc(sid)) : 0;
  if (luSPUsed() - costCur + costNext > luBase.skill_points) return;
  if (next === 0) delete luSkillDeltas[sid]; else luSkillDeltas[sid] = next;
  updateLuSpHeader();
  renderLuSkills();
}

function renderNewSkillSel() {
  const sel = document.getElementById("lu-new-skill-sel");
  const shown = new Set(luShownSkills);
  sel.innerHTML = '<option value="">— tilføj ny skill —</option>';
  const cls  = allSkillsDB.filter(s => clsSkillSet.has(s.id) && !shown.has(s.id));
  const xcls = allSkillsDB.filter(s => !clsSkillSet.has(s.id) && !shown.has(s.id));
  [[cls,"Klasseskills"],[xcls,"Krydsklasse"]].forEach(([arr,label]) => {
    if (!arr.length) return;
    const og = document.createElement("optgroup");
    og.label = label;
    arr.forEach(s => { og.innerHTML += `<option value="${s.id}">${escHtml(s.name)}</option>`; });
    sel.appendChild(og);
  });
}

function addNewLuSkill() {
  const sel = document.getElementById("lu-new-skill-sel");
  const sid = sel.value;
  if (!sid || luShownSkills.includes(sid)) return;
  baseRanks[sid] = 0;
  luShownSkills.push(sid);
  sel.value = "";
  renderLuSkills();
  renderNewSkillSel();
}

function filterLuFeats() {
  const q          = (document.getElementById("lu-feat-search").value || "").toLowerCase();
  const onlyOk     = document.getElementById("lu-feat-eligible-only").checked;
  const sel        = document.getElementById("lu-feat-sel");
  sel.innerHTML = "";
  allFeats.filter(f => !charFeatIds.has(f.id) && f.id !== luBonusFeat &&
    (onlyOk ? f.eligible : true) &&
    (f.name.toLowerCase().includes(q) || (f.prerequisites||"").toLowerCase().includes(q)))
  .forEach(f => {
    const opt = document.createElement("option");
    opt.value = f.id;
    // Ulovlige feats (kun synlige når "vis alle") markeres og kan ikke vælges.
    opt.textContent = (f.eligible ? "" : "⚠ ") + f.name +
      (f.prerequisites ? ` · kræver: ${f.prerequisites}` : "");
    if (!f.eligible) { opt.disabled = true; opt.style.color = "var(--muted)"; }
    if (f.id === luFeat) opt.selected = true;
    sel.appendChild(opt);
  });
  if (luFeat) showLuFeatInfo(luFeat);
}

// Bonus-kampfeat: samme mønster som filterLuFeats, men begrænset til
// fighter_bonus-puljen (db.get_fighter_bonus_feats() → fighter_bonus-flag i all_feats_json).
function filterLuBonusFeats() {
  const q          = (document.getElementById("lu-bonus-feat-search").value || "").toLowerCase();
  const onlyOk     = document.getElementById("lu-bonus-feat-eligible-only").checked;
  const sel        = document.getElementById("lu-bonus-feat-sel");
  sel.innerHTML = "";
  allFeats.filter(f => f.fighter_bonus && !charFeatIds.has(f.id) && f.id !== luFeat &&
    (onlyOk ? f.eligible : true) &&
    (f.name.toLowerCase().includes(q) || (f.prerequisites||"").toLowerCase().includes(q)))
  .forEach(f => {
    const opt = document.createElement("option");
    opt.value = f.id;
    opt.textContent = (f.eligible ? "" : "⚠ ") + f.name +
      (f.prerequisites ? ` · kræver: ${f.prerequisites}` : "");
    if (!f.eligible) { opt.disabled = true; opt.style.color = "var(--muted)"; }
    if (f.id === luBonusFeat) opt.selected = true;
    sel.appendChild(opt);
  });
  if (luBonusFeat) showLuBonusFeatInfo(luBonusFeat);
}

function pickLuFeat(fid) {
  luFeat = fid || null;
  showLuFeatInfo(fid);
  // Våben-feats: vis en våben-dropdown og kræv et valg.
  const wsel = document.getElementById("lu-feat-weapon");
  if (luFeat && LU_WEAPON_CHOICE_FEATS.includes(luFeat)) {
    if (!wsel.options.length) {
      wsel.innerHTML = '<option value="">— vælg våben —</option>' +
        (catalogData.weapons || []).map(w => `<option value="${escHtml(w.name)}">${escHtml(w.name)}</option>`).join("");
    }
    wsel.value = luFeatWeapon || "";
    wsel.style.display = "block";
  } else {
    wsel.style.display = "none";
    luFeatWeapon = "";
  }
  // Skole-feats (Spell Focus m.fl.): vis en troldskole-dropdown og kræv et valg.
  const ssel = document.getElementById("lu-feat-school");
  if (luFeat && LU_SCHOOL_CHOICE_FEATS.includes(luFeat)) {
    if (!ssel.options.length) {
      ssel.innerHTML = '<option value="">— vælg troldskole —</option>' +
        (D.spellSchools || []).map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join("");
    }
    ssel.value = luFeatSchool || "";
    ssel.style.display = "block";
  } else {
    ssel.style.display = "none";
    luFeatSchool = "";
  }
}

function showLuFeatInfo(fid) {
  const f = allFeats.find(f => f.id === fid);
  const el = document.getElementById("lu-feat-info");
  if (f) {
    let head = "";
    if (f.prerequisites) head += `<em>Kræver: ${escHtml(f.prerequisites)}</em><br>`;
    if (!f.eligible && f.unmet && f.unmet.length)
      head += `<span style="color:var(--red,#c66)">⚠ Mangler: ${escHtml(f.unmet.join(", "))}</span><br>`;
    el.innerHTML = head + escHtml(f.benefit || "");
  } else {
    el.innerHTML = "";
  }
}

function pickLuBonusFeat(fid) {
  luBonusFeat = fid || null;
  showLuBonusFeatInfo(fid);
  // Våben-feats: vis en våben-dropdown og kræv et valg.
  const wsel = document.getElementById("lu-bonus-feat-weapon");
  if (luBonusFeat && LU_WEAPON_CHOICE_FEATS.includes(luBonusFeat)) {
    if (!wsel.options.length) {
      wsel.innerHTML = '<option value="">— vælg våben —</option>' +
        (catalogData.weapons || []).map(w => `<option value="${escHtml(w.name)}">${escHtml(w.name)}</option>`).join("");
    }
    wsel.value = luBonusFeatWeapon || "";
    wsel.style.display = "block";
  } else {
    wsel.style.display = "none";
    luBonusFeatWeapon = "";
  }
  // Skole-feats (Spell Focus m.fl.): vis en troldskole-dropdown og kræv et valg.
  const ssel = document.getElementById("lu-bonus-feat-school");
  if (luBonusFeat && LU_SCHOOL_CHOICE_FEATS.includes(luBonusFeat)) {
    if (!ssel.options.length) {
      ssel.innerHTML = '<option value="">— vælg troldskole —</option>' +
        (D.spellSchools || []).map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join("");
    }
    ssel.value = luBonusFeatSchool || "";
    ssel.style.display = "block";
  } else {
    ssel.style.display = "none";
    luBonusFeatSchool = "";
  }
}

function showLuBonusFeatInfo(fid) {
  const f = allFeats.find(f => f.id === fid);
  const el = document.getElementById("lu-bonus-feat-info");
  if (f) {
    let head = "";
    if (f.prerequisites) head += `<em>Kræver: ${escHtml(f.prerequisites)}</em><br>`;
    if (!f.eligible && f.unmet && f.unmet.length)
      head += `<span style="color:var(--red,#c66)">⚠ Mangler: ${escHtml(f.unmet.join(", "))}</span><br>`;
    el.innerHTML = head + escHtml(f.benefit || "");
  } else {
    el.innerHTML = "";
  }
}

function renderLuAbBtns() {
  const cont = document.getElementById("lu-ab-btns");
  cont.innerHTML = "";
  [["str","STR"],["dex","DEX"],["con","CON"],["int","INT"],["wis","WIS"],["cha","CHA"]]
  .forEach(([key,label]) => {
    const btn = document.createElement("button");
    btn.className = "lu-ab-btn" + (luAbBoost === key ? " selected" : "");
    btn.textContent = `${label} ${abScores[key]} → ${abScores[key]+1}`;
    btn.onclick = () => { luAbBoost = luAbBoost === key ? null : key; renderLuAbBtns(); };
    cont.appendChild(btn);
  });
}

function confirmLevelUp() {
  const warn = document.getElementById("lu-warning");
  warn.textContent = "";
  if (luHpRoll <= 0) { warn.textContent = "⚠ Rul eller angiv HP-stigning først."; return; }
  if (luBase.feat_level && !luFeat) { warn.textContent = "⚠ Vælg en feat."; return; }
  if (luBase.bonus_feat_level && !luBonusFeat) { warn.textContent = "⚠ Vælg en bonus-kampfeat."; return; }
  // Våben-/skole-feat valgt uden valg → bloker.
  const newFeats = [];
  if (luFeat) {
    let featPayload = luFeat;
    if (LU_WEAPON_CHOICE_FEATS.includes(luFeat)) {
      if (!luFeatWeapon) { warn.textContent = "⚠ Vælg et våben til feat'en."; return; }
      featPayload = {id: luFeat, weapon: luFeatWeapon};
    } else if (LU_SCHOOL_CHOICE_FEATS.includes(luFeat)) {
      if (!luFeatSchool) { warn.textContent = "⚠ Vælg en troldskole til feat'en."; return; }
      featPayload = {id: luFeat, school: luFeatSchool};
    }
    newFeats.push(featPayload);
  }
  if (luBonusFeat) {
    let bonusPayload = luBonusFeat;
    if (LU_WEAPON_CHOICE_FEATS.includes(luBonusFeat)) {
      if (!luBonusFeatWeapon) { warn.textContent = "⚠ Vælg et våben til bonus-feat'en."; return; }
      bonusPayload = {id: luBonusFeat, weapon: luBonusFeatWeapon};
    } else if (LU_SCHOOL_CHOICE_FEATS.includes(luBonusFeat)) {
      if (!luBonusFeatSchool) { warn.textContent = "⚠ Vælg en troldskole til bonus-feat'en."; return; }
      bonusPayload = {id: luBonusFeat, school: luBonusFeatSchool};
    }
    newFeats.push(bonusPayload);
  }
  fetch(BASE + "/api/levelup", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, hp_roll: luHpRoll,
      skill_deltas: luSkillDeltas, new_feats: newFeats, ability_boost: luAbBoost})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else warn.textContent = d.error || "Fejl"; });
}

function closeLu() { document.getElementById("lu-overlay").classList.remove("open"); }
function closeLuIfOutside(e) { if (e.target===document.getElementById("lu-overlay")) closeLu(); }
