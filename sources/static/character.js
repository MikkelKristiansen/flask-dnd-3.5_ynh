// character.js — opførsel for karakterarket.
// Server-data injiceres via data-broen window.DND i character.html;
// her udpakkes den med uændrede variabelnavne, så resten af logikken er urørt.
const D = window.DND;

const BASE = D.scriptRoot;
const CHAR = D.name;
const HP_MAX = D.hpMax;
let hpCurrent = D.hpCurrent;

// Spell-tilstande: {level: [spell_index, ...]}. used = "Brugt", active = "I brug".
let spellsUsed = D.spellsUsed;
let spellsActive = D.spellsActive;
// Normalize keys to integers in JS
spellsUsed = Object.fromEntries(Object.entries(spellsUsed).map(([k,v]) => [parseInt(k), v]));
spellsActive = Object.fromEntries(Object.entries(spellsActive).map(([k,v]) => [parseInt(k), v]));

// Slot totals from server
const slotTotals = D.slotTotals;

// Conditions
let conditions = D.conditions;

// Buffs (tracking) — data til badge-popups + hurtigvalg
const charBuffs   = D.charBuffs;
const compBuffs   = D.compBuffs;
// Summon-buffs pr. target-streng ("summon-<lvl>-<idx>") → showBuff slår op her.
const summonBuffs = D.summonBuffs;
const buffCatalog = D.buffCatalog.concat(D.damageCatalog);
const abilityData = D.abilityData;
const AFFECT_LABEL = {attack:"angreb", save:"saves", skill:"skills", ac:"AC", hp:"HP",
                      str:"Str", dex:"Dex", con:"Con", wis:"Wis", int:"Int", cha:"Cha", speed:"speed"};

// All conditions lookup for name display
const allConditions = {};
Object.assign(allConditions, D.allConditions);

// Navn → id, så condition-ord i beskrivelser kan gøres klikbare
const conditionByName = {};
Object.keys(allConditions).forEach(id => {
  conditionByName[allConditions[id].name.toLowerCase().replace(/-/g, " ")] = id;
});

function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

// Gør condition-navne i et renderet element klikbare. Kun første forekomst
// pr. condition, kun i tekstnoder (rører ikke HTML-tags/attributter).
// skipId udelades (en condition skal ikke linke til sig selv).
function linkConditions(rootEl, skipId) {
  const names = Object.keys(conditionByName)
    .filter(n => conditionByName[n] !== skipId)
    .sort((a, b) => b.length - a.length);
  if (!names.length) return;
  // navne er normaliseret med mellemrum; tillad bindestreg i teksten (flat-footed)
  const alt = names.map(n => escRe(n).replace(/ /g, "[\\s-]+")).join("|");
  const pattern = new RegExp("\\b(" + alt + ")\\b", "gi");
  const linked = new Set();
  const textNodes = [];
  const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT);
  let n;
  while (n = walker.nextNode()) {
    if (!n.parentElement || n.parentElement.closest(".cond-link")) continue;
    textNodes.push(n);
  }
  textNodes.forEach(textNode => {
    const text = textNode.textContent;
    const frag = document.createDocumentFragment();
    let lastIndex = 0, m, replaced = false;
    pattern.lastIndex = 0;
    while (m = pattern.exec(text)) {
      const id = conditionByName[m[0].toLowerCase().replace(/-/g, " ")];
      if (!id || linked.has(id)) continue;
      linked.add(id);
      replaced = true;
      frag.appendChild(document.createTextNode(text.slice(lastIndex, m.index)));
      const span = document.createElement("span");
      span.className = "cond-link";
      span.textContent = m[0];
      span.title = "Vis forklaring";
      span.onclick = (e) => { e.stopPropagation(); showDetail("condition", id); };
      frag.appendChild(span);
      lastIndex = m.index + m[0].length;
    }
    if (replaced) {
      frag.appendChild(document.createTextNode(text.slice(lastIndex)));
      textNode.parentNode.replaceChild(frag, textNode);
    }
  });
}

// ── Companion HP ──────────────────────────────────────────────────────────
// — companion-blok: funktioner defineres altid; data er companion-sikker via broen —
let compHpCurrent = D.compHpCurrent;
const compHpMax   = D.compHpMax;

function adjCompHp(delta) {
  fetch(BASE + "/api/companion_hp", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, delta})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    compHpCurrent = data.hp_current;
    const el = document.getElementById("comp-hp-val");
    if (el) el.textContent = compHpCurrent + "/" + data.hp_max;
  });
}

// ── Summon-effekter & HP ───────────────────────────────────────────────────
// En summon-target er strengen "summon-<spell_level>-<spell_index>". De generiske
// effekt-funktioner (addCondition/addBuff/...) genkender den og router til summon.
function parseSummonTarget(target) {
  const m = /^summon-(\d+)-(\d+)$/.exec(target || "");
  return m ? {spell_level: parseInt(m[1]), spell_index: parseInt(m[2])} : null;
}

function adjSummonHp(target, creatureIdx, delta) {
  const s = parseSummonTarget(target);
  if (!s) return;
  fetch(BASE + "/api/summon_hp", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, spell_level: s.spell_level,
                          spell_index: s.spell_index, creature_index: creatureIdx, delta})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    const hp = data.hp_current[creatureIdx];
    const el = document.getElementById(`${target}-hp-${creatureIdx}`);
    if (el) el.textContent = hp + "/" + data.hp_max;
    // Individ-kortets status-farve (kun ved count>1; count==1 har intet kort).
    const card = document.getElementById(`${target}-card-${creatureIdx}`);
    if (card) {
      const ratio = data.hp_max ? hp / data.hp_max : 1;
      card.className = "summon-indiv " + (hp <= 0 ? "down" : ratio <= 0.5 ? "hurt" : "ok");
    }
  });
}

// Justér et summons resterende runder (varighed). reset=true → fuld varighed.
function adjSummonRounds(target, delta, reset) {
  const s = parseSummonTarget(target);
  if (!s) return;
  fetch(BASE + "/api/summon_rounds", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, spell_level: s.spell_level,
                          spell_index: s.spell_index, delta, reset: !!reset})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    const el = document.getElementById(`${target}-rounds`);
    if (!el) return;
    const done = data.rounds_left === 0;
    el.textContent = done ? "udløbet" : `${data.rounds_left}/${data.rounds_max} runder`;
    el.classList.toggle("expired", done);
  });
}

// ── Companion tricks (redigerbar liste) ───────────────────────────────────
let compTricks = D.compTricks;

function renderTricks() {
  const box = document.getElementById("comp-tricks");
  if (!box) return;
  if (!compTricks.length) {
    box.innerHTML = '<span style="color:var(--muted);font-size:.85rem">— ingen tricks —</span>';
    return;
  }
  box.innerHTML = compTricks.map((t, i) =>
    `<span style="display:inline-flex;align-items:center;gap:.3rem;padding:.15rem .5rem;`
    + `background:var(--card);border:1px solid var(--border);border-radius:12px;font-size:.82rem">`
    + `${t.replace(/</g,'&lt;')}`
    + `<span onclick="removeTrick(${i})" title="Fjern" `
    + `style="cursor:pointer;color:var(--muted);font-weight:bold">×</span></span>`
  ).join("");
}

function saveTricks() {
  fetch(BASE + "/api/companion_tricks", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, tricks: compTricks})
  })
  .then(r => r.json())
  .then(data => { if (!data.error) { compTricks = data.tricks; renderTricks(); } });
}

function addTrick() {
  const inp = document.getElementById("comp-trick-input");
  const name = inp.value.trim();
  if (!name) return;
  compTricks.push(name);
  inp.value = "";
  renderTricks();
  saveTricks();
}

function removeTrick(i) {
  compTricks.splice(i, 1);
  renderTricks();
  saveTricks();
}

renderTricks();
// — companion-blok slut —

// ── Animal Companion: tilkald / afsked ────────────────────────────────────
function openSummonCompanion() {
  document.getElementById("summon-companion-overlay").classList.add("open");
}

function confirmSummonCompanion() {
  const animal = document.getElementById("summon-companion-animal").value;
  const name   = document.getElementById("summon-companion-name").value.trim();
  if (!animal) return;
  fetch(BASE + "/api/companion", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "summon", animal, name})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

function dismissCompanion(name) {
  if (!confirm(`Er du helt sikker?\n\nDu siger farvel til ${name}. Ledsagerens data slettes og kan ikke fortrydes.`)) return;
  fetch(BASE + "/api/companion", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "dismiss"})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

// Familiaren døde: fjern den + start ventetid og midlertidig straf på mesteren.
function familiarDied(name) {
  if (!confirm(`${name} døde.\n\nDen fjernes, en ventetid begynder, og du bærer en midlertidig straf (−1 angreb/saves) indtil en ny familiar er tilkaldt.`)) return;
  fetch(BASE + "/api/familiar", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "died"})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

// Tæl ventetiden (dage til gen-tilkald) op/ned; ved 0 kan en ny familiar tilkaldes.
function adjFamiliarCooldown(delta) {
  fetch(BASE + "/api/familiar", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "cooldown", delta})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

// ── Wild Shape: skift form / skift tilbage ────────────────────────────────
function shapeWildShape() {
  const form = document.getElementById("ws-form-pick").value;
  if (!form) return;
  fetch(BASE + "/api/wild_shape", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "shape", form})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

function revertWildShape() {
  fetch(BASE + "/api/wild_shape", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "revert"})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

function toggleWildAbility(slug) {
  fetch(BASE + "/api/wild_shape", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "toggle_ability", ability: slug})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) window.location.reload(); else alert(d.error || "Fejl"); });
}

// ── Manuelle angreb (redigerbare) ─────────────────────────────────────────
const attacksData = D.attacksData;

// ── Inventory state ───────────────────────────────────────────────────────
let inventoryData = D.inventoryData;
const catalogData = D.catalogData;
let currentWeight = D.currentWeight;
let currentEnc    = D.currentEnc;
let encLimits     = D.encLimits;
const baseSpeed   = D.baseSpeed;

// ── Tab switching ──────────────────────────────────────────────────────────
function showTab(name, btn) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  btn.classList.add("active");
  history.replaceState(null, "", "#" + name);   // bevar fane ved genindlæsning
}

// Aktivér fane fra URL-hash ved load (så reload efter udrustning lander på Udstyr)
(function restoreTab() {
  const h = location.hash.replace("#", "");
  if (!h) return;
  const btn = document.querySelector(`.tab-btn[onclick*="showTab('${h}'"]`);
  if (btn) showTab(h, btn);
})();

function showSpellView(name, btn) {
  document.querySelectorAll(".spell-view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".spell-subtab").forEach(b => b.classList.remove("active"));
  document.getElementById("spellview-" + name).classList.add("active");
  btn.classList.add("active");
}

function toggleUnusableSkills() {
  const sec = document.getElementById("skills-section");
  const btn = document.getElementById("skill-toggle-btn");
  const shown = sec.classList.toggle("show-unusable");
  const n = sec.querySelectorAll(".skill-row.unusable").length;
  btn.textContent = (shown ? "− " : "+ ") + n + " trænet-kun";
}

// ── HP ────────────────────────────────────────────────────────────────────
function hpBarColor(pct) {
  // 80-100% → grøn, ned til 0% → rød via HSL
  if (pct >= 80) return "hsl(120,55%,38%)";
  const hue = Math.round(pct * 1.5); // 80→120 (grøn), 0→0 (rød)
  return `hsl(${hue},70%,38%)`;
}

function updateHpDisplay(hp) {
  const numEl    = document.getElementById("hp-num");
  const barEl    = document.getElementById("hp-bar");
  const statusEl = document.getElementById("hp-status");

  numEl.textContent = hp;

  const pct = HP_MAX > 0 ? Math.max(0, Math.min(100, Math.round(hp * 100 / HP_MAX))) : 0;
  barEl.style.width      = pct + "%";
  barEl.style.background = hpBarColor(pct);

  if (hp <= -10) {
    numEl.className = "hp-num-dead";
    statusEl.textContent  = " ☠ Død";
    statusEl.style.color  = "var(--red)";
    barEl.classList.remove("hp-bar-dying");
  } else if (hp < 0) {
    numEl.className = "hp-num-dead";
    statusEl.textContent  = " 🩸 Døende";
    statusEl.style.color  = "var(--red)";
    barEl.classList.add("hp-bar-dying");
  } else if (hp === 0) {
    numEl.className = "hp-num-dead";
    statusEl.textContent  = " 💫 Besvimede";
    statusEl.style.color  = "var(--yellow)";
    barEl.classList.remove("hp-bar-dying");
  } else {
    numEl.className       = "";
    statusEl.textContent  = "";
    barEl.classList.remove("hp-bar-dying");
  }
}

function hpChange(delta) {
  fetch(BASE + "/api/hp", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, delta})
  })
  .then(r => r.json())
  .then(data => {
    hpCurrent = data.hp_current;
    updateHpDisplay(hpCurrent);
  });
}

// Sæt korrekt startfarve og status ved sideload
updateHpDisplay(hpCurrent);

// ── Conditions ────────────────────────────────────────────────────────────
// Effekter (tilstande + buffs) — server-renderet, så vi reloader efter ændring.
function toggleEffectPicker(target) {
  const p = document.getElementById("effect-picker-" + target);
  p.style.display = (p.style.display === "block") ? "none" : "block";
}

function onBuffPick(target) {
  const custom = document.getElementById("buff-select-" + target).value === "custom";
  document.getElementById("buff-name-" + target).style.display = custom ? "block" : "none";
  document.getElementById("buff-note-" + target).style.display = custom ? "block" : "none";
}

// Oversæt en target-streng til request-felterne: summon-targets sender target:
// "summon" + SNA-slot; character/companion sender bare target-strengen videre.
function effectTargetBody(target) {
  const s = parseSummonTarget(target);
  return s ? {target: "summon", spell_level: s.spell_level, spell_index: s.spell_index}
           : {target: target || "character"};
}

function addCondition(target) {
  target = target || "character";
  const id = document.getElementById("cond-select-" + target).value;
  if (!id) return;
  fetch(BASE + "/api/conditions", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, condition_id: id, action: "add", ...effectTargetBody(target)})
  }).then(() => location.reload());
}

function removeCondition(id, target) {
  fetch(BASE + "/api/conditions", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, condition_id: id, action: "remove", ...effectTargetBody(target)})
  }).then(() => location.reload());
}

function addBuff(target) {
  target = target || "character";
  const sel = document.getElementById("buff-select-" + target);
  let buff = null;
  if (sel.value === "custom") {
    const name = document.getElementById("buff-name-" + target).value.trim();
    if (!name) return;
    buff = {name, note: document.getElementById("buff-note-" + target).value.trim(), affects: []};
  } else if (sel.value !== "") {
    buff = buffCatalog[parseInt(sel.value)];
  }
  if (!buff) return;
  // Ability-skade m.fl.: katalog-effekten har en redigerbar værdi → spørg om
  // mængden og send den med som instans-override (negativ for skade).
  if (buff.editable) {
    const raw = prompt(buff.prompt || "Værdi?", Math.abs(buff.value || 1));
    if (raw === null) return;
    const n = parseInt(raw, 10);
    if (isNaN(n) || n === 0) return;
    buff = {...buff, value: buff.negative ? -Math.abs(n) : n};
  }
  fetch(BASE + "/api/buffs", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "add", buff, ...effectTargetBody(target)})
  }).then(() => location.reload());
}

function removeBuff(target, idx) {
  fetch(BASE + "/api/buffs", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "remove", index: idx, ...effectTargetBody(target)})
  }).then(() => location.reload());
}

// ── Kampindstillinger: toggles der lægger bonusser oveni FØR man slår ──────
// (Point Blank Shot, Dodge, Charge, Fighting Defensively). Samme simple
// reload-mønster som addBuff/removeBuff.
function toggleCombatOption(id, el) {
  fetch(BASE + "/api/combat_options", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, option_id: id, on: el.checked})
  }).then(() => location.reload());
}

// Editable kampindstillinger (Lag B: Power Attack/Combat Expertise) — talfelt
// i stedet for afkrydsning. 0/tomt slukker optionen (og rydder dens evt.
// under-toggles server-side, se api_combat_options).
function setCombatOption(id, el) {
  fetch(BASE + "/api/combat_options", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, option_id: id, value: parseInt(el.value) || 0})
  }).then(() => location.reload());
}

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

function showBuff(target, idx) {
  const list = parseSummonTarget(target) ? (summonBuffs[target] || [])
             : (target === "companion" ? compBuffs : charBuffs);
  const b = list[idx];
  if (!b) return;
  document.getElementById("modal-title").textContent = b.name;
  document.getElementById("modal-subtitle").textContent = "Buff — tracking (læg selv tallet til)";
  const affects = (b.affects || []).map(a => AFFECT_LABEL[a] || a).join(", ");
  const body = document.getElementById("modal-body");
  body.innerHTML =
    (b.note ? `<p style="line-height:1.5">${escHtml(b.note)}</p>` : "") +
    (affects ? `<div class="modal-row"><span class="modal-key">Påvirker</span><span class="modal-val">${affects}</span></div>` : "");
  document.getElementById("modal-overlay").classList.add("open");
  if (b.spell_id) {
    fetch(BASE + `/api/detail/spell/${b.spell_id}`).then(r => r.json()).then(d => {
      if (!d.error && d.description)
        body.innerHTML += `<div style="margin-top:.7rem;padding-top:.6rem;border-top:1px solid var(--border);line-height:1.5;white-space:pre-line">${mdText(d.description)}</div>`;
    });
  }
}

// Breakdown for en evnescore en aktiv effekt har ændret: basis → effektiv + kilder.
function showAbilityBreakdown(key) {
  const a = abilityData.find(x => x.key === key);
  if (!a) return;
  document.getElementById("modal-title").textContent = a.abbr;
  document.getElementById("modal-subtitle").textContent = "Evnescore — basis → effektiv";
  const arrow = a.up ? "▲" : "▼";
  const sources = (a.sources || []).map(s =>
    `<div class="modal-row"><span class="modal-key">${escHtml(s.name)}</span>`
    + `<span class="modal-val">${s.value > 0 ? "+" : ""}${s.value}</span></div>`).join("");
  document.getElementById("modal-body").innerHTML =
    `<div class="modal-row"><span class="modal-key">Basis</span>`
    + `<span class="modal-val">${a.base} (${a.base_mod >= 0 ? "+" : ""}${a.base_mod})</span></div>`
    + `<div class="modal-row"><span class="modal-key">Effektiv ${arrow}</span>`
    + `<span class="modal-val">${a.score} (${a.mod >= 0 ? "+" : ""}${a.mod})</span></div>`
    + (sources ? `<div style="margin-top:.5rem">${sources}</div>` : "");
  document.getElementById("modal-overlay").classList.add("open");
}

// Påmindelse ved sektionerne (del 2): hvilke aktive buffs rammer denne sektion.
function buffReminderHtml(buffs, tags, target) {
  const rel = buffs.map((b, i) => ({b, i}))
                   .filter(x => (x.b.affects || []).some(a => tags.includes(a)));
  if (!rel.length) return "";
  const items = rel.map(({b, i}) =>
    `<span class="buff-rem-item">`
    + `<span class="buff-rem-name" onclick="showBuff('${target}',${i})">${escHtml(b.name)}</span>`
    + (b.note ? ` <span class="buff-rem-note">${escHtml(b.note)}</span>` : "")
    + `</span>`).join("");
  return `<span class="buff-rem-lead">⚡ Aktive buffs:</span>${items}`;
}

function renderBuffReminders() {
  const ATTACK = ["attack", "str", "dex"];
  const SAVE   = ["save", "con", "dex", "wis"];
  const COMBAT = ["ac", "dex", "str", "speed"];
  [
    ["buff-rem-saves-character",   charBuffs, SAVE,   "character"],
    ["buff-rem-combat-character",  charBuffs, COMBAT, "character"],
    ["buff-rem-attacks-character", charBuffs, ATTACK, "character"],
    ["buff-rem-combat-companion",  compBuffs, SAVE.concat(COMBAT), "companion"],
    ["buff-rem-attacks-companion", compBuffs, ATTACK, "companion"],
  ].forEach(([id, buffs, tags, target]) => {
    const el = document.getElementById(id);
    if (!el) return;
    const html = buffReminderHtml(buffs, tags, target);
    el.innerHTML = html;
    el.style.display = html ? "block" : "none";
  });
}
renderBuffReminders();

// ── Spells ────────────────────────────────────────────────────────────────
// To-tilstands-spells cykler Ledig→Brugt→Ledig. Tre-tilstands-spells (data-three-
// state: self_duration-buffs OG kategori-F utility m/ varighed) har en ekstra "I
// brug"-tilstand: Ledig→I brug→Brugt→Ledig. Når en tre-tilstands-spell skifter,
// reloader vi — så Oversigtens angreb/varighed (server-renderet) opdateres.
const STATE_LABEL = {free: "Ledig", active: "I brug", used: "Brugt"};

function slotUsedCount(level) {
  // Både "Brugt" og "I brug" har forbrugt en slot.
  return (spellsUsed[level] || []).length + (spellsActive[level] || []).length;
}

function spellState(level, idx) {
  if ((spellsActive[level] || []).includes(idx)) return "active";
  if ((spellsUsed[level] || []).includes(idx)) return "used";
  return "free";
}

function cycleSpell(level, idx) {
  const row = document.getElementById(`spell-${level}-${idx}`);
  // Tre-tilstand (self_duration ELLER kategori-F utility m/ varighed): Ledig→I brug→
  // Brugt. To-tilstand (øjeblikkelige angreb, healing …): Ledig↔Brugt.
  const threeState = row && row.dataset.threeState === "1";
  const cur = spellState(level, idx);
  let next;
  if (threeState) {
    next = cur === "free" ? "active" : (cur === "active" ? "used" : "free");
  } else {
    next = cur === "used" ? "free" : "used";
  }
  // Forbruger vi en frisk slot (fra Ledig til I brug/Brugt)? Tjek kapacitet.
  if (cur === "free" && next !== "free") {
    const total = slotTotals[level] || 0;
    if (slotUsedCount(level) >= total) {
      alert("Ingen slots tilbage på level " + level + "!");
      return;
    }
  }
  fetch(BASE + "/api/spells", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, spell_index: idx, state: next})
  })
  .then(r => r.json())
  .then(data => {
    spellsUsed = Object.fromEntries(Object.entries(data.spells_used).map(([k,v]) => [parseInt(k), v]));
    spellsActive = Object.fromEntries(Object.entries(data.spells_active).map(([k,v]) => [parseInt(k), v]));
    // Et SNA-spell skifter summon-fane + Kast-knap (server-renderet) → reload.
    // Tre-tilstands-spells kan tænde/slukke et spell-angreb ELLER en utility-varighed
    // i Oversigten (server-renderet) → reload.
    if (data.is_summon || threeState) { location.reload(); return; }
    updateSpellDisplay(level);
  });
}

// ── Summon Nature's Ally: kast → vælg væsen ────────────────────────────────
// summonCatalog: {SNA-niveau: [{id, name}, ...]} — væsner pr. forberedt SNA-niveau.
const summonCatalog = D.summonCatalog;

const SNA_NUM = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"];

// mode = "cast" (kast et summon-spell, SNA/SM) | "sacrifice" (ofre et andet spell
// til SNA N — kun druide). label = spell-navnet, bruges i overskriften ved cast.
function openSummonPicker(level, idx, mode, label) {
  mode = mode || "cast";
  const list = summonCatalog[level] || [];
  if (!list.length) { alert("Ingen summonbare væsner på niveau " + level + "."); return; }
  document.getElementById("summon-modal-level").value = level;
  document.getElementById("summon-modal-index").value = idx;
  document.getElementById("summon-modal-mode").value = mode;
  document.getElementById("summon-modal-subtitle").textContent =
    (mode === "sacrifice" ? "Ofre plads → Summon Nature's Ally " + SNA_NUM[level]
                          : (label || "Summon " + SNA_NUM[level]));
  const sel = document.getElementById("summon-modal-creature");
  // Grupér efter spor (offset): niveau-N-listen (1 væsen), niveau N-1 (1d3), N-2
  // (1d4+1). value = indeks i listen, så vi kan hente id/skabelon/antal ved kast.
  const byOffset = {};
  list.forEach((c, i) => { (byOffset[c.offset] = byOffset[c.offset] || []).push({c, i}); });
  sel.innerHTML = Object.keys(byOffset).map(Number).sort((a, b) => a - b).map(off => {
    const grp = byOffset[off], c0 = grp[0].c;
    const glabel = off === 0 ? `1 væsen (niveau ${SNA_NUM[c0.tier_level]})`
                             : `${c0.count} af samme slags (niveau ${SNA_NUM[c0.tier_level]})`;
    const opts = grp.map(({c, i}) => `<option value="${i}">${escHtml(c.name)}</option>`).join("");
    return `<optgroup label="${glabel}">${opts}</optgroup>`;
  }).join("");
  updateSummonCount();
  document.getElementById("summon-modal-augment").style.display =
    charFeatIds.has("augment_summoning") ? "" : "none";
  document.getElementById("summon-modal-overlay").classList.add("open");
}

// Vis antal-udtrykket for det valgte væsen (rulles server-side ved kast). Skjules
// for 1-væsen-sporet, hvor der aldrig er andet end præcis ét.
function updateSummonCount() {
  const level  = parseInt(document.getElementById("summon-modal-level").value);
  const chosen = (summonCatalog[level] || [])[parseInt(document.getElementById("summon-modal-creature").value)] || {};
  const row = document.getElementById("summon-modal-count-row");
  if (chosen.count && chosen.count !== "1") {
    document.getElementById("summon-modal-count-note").textContent =
      `Antal: ${chosen.count} af samme slags — rulles automatisk ved kast.`;
    row.style.display = "";
  } else {
    row.style.display = "none";
  }
}

function castSummon() {
  const level = parseInt(document.getElementById("summon-modal-level").value);
  const idx   = parseInt(document.getElementById("summon-modal-index").value);
  const mode  = document.getElementById("summon-modal-mode").value;
  const chosen = (summonCatalog[level] || [])[parseInt(document.getElementById("summon-modal-creature").value)] || {};
  const creature = chosen.id;
  const template = chosen.template || null;
  // Antal bestemmes/rulles server-side ud fra sporet — klienten sender det ikke.
  fetch(BASE + "/api/summon", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, mode, level, spell_index: idx, creature, template})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert("Kunne ikke kaste: " + data.error); return; }
    // Fanen er server-renderet → reload viser den nye summon-fane + spell "I brug".
    location.reload();
  });
}

// ── Spontan cure/inflict (cleric) ──────────────────────────────────────────
// cureCatalog: {slot-niveau: [{id, name, level}]} — cure/inflict-spells man kan
// konvertere til pr. forberedt slot-niveau. Ofre = markér pladsen "Brugt" (genbrug
// /api/spells) og åbn den kastede spell, så spilleren kan slå helbredelsen.
const cureCatalog = D.cureCatalog || {};
const cureDirection = D.cureDirection || "cure";

function openCurePicker(level, idx) {
  const list = cureCatalog[level] || [];
  if (!list.length) { alert("Ingen " + cureDirection + "-spells for niveau " + level + "."); return; }
  document.getElementById("cure-modal-level").value = level;
  document.getElementById("cure-modal-index").value = idx;
  document.getElementById("cure-modal-title").textContent =
    (cureDirection === "inflict" ? "✚ Spontan inflict" : "✚ Spontan cure");
  document.getElementById("cure-modal-subtitle").textContent =
    "Ofre plads (level " + level + ") → " + (cureDirection === "inflict" ? "inflict" : "cure") + "-spell";
  const sel = document.getElementById("cure-modal-spell");
  sel.innerHTML = list.map(s => `<option value="${s.id}">${s.name} (L${s.level})</option>`).join("");
  document.getElementById("cure-modal-overlay").classList.add("open");
}

function castSpontaneousCure() {
  const level = parseInt(document.getElementById("cure-modal-level").value);
  const idx   = parseInt(document.getElementById("cure-modal-index").value);
  const spellId = document.getElementById("cure-modal-spell").value;
  // Kapacitets-tjek (samme som cycleSpell): en frisk plads forbruges.
  if (slotUsedCount(level) >= (slotTotals[level] || 0)) {
    alert("Ingen slots tilbage på level " + level + "!");
    return;
  }
  // Ofre pladsen = sæt den "Brugt" via det eksisterende spell-state-endpoint.
  fetch(BASE + "/api/spells", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, spell_index: idx, state: "used"})
  })
  .then(r => r.json())
  .then(data => {
    spellsUsed = Object.fromEntries(Object.entries(data.spells_used).map(([k, v]) => [parseInt(k), v]));
    spellsActive = Object.fromEntries(Object.entries(data.spells_active).map(([k, v]) => [parseInt(k), v]));
    updateSpellDisplay(level);
    document.getElementById("cure-modal-overlay").classList.remove("open");
    // Åbn den kastede spell, så spilleren ser og kan slå helbredelsen.
    showDetail("spell", spellId);
  });
}

// ── Kast et øjeblikkeligt spell (Magic Missile, Fireball, Sleep …) ─────────
// Instantaneous angrebs- og område/save-spells har ingen "I brug"-tilstand
// (self_duration) — de kastes her-og-nu: læg skade-udtrykket i terningefeltet
// (spilleren trykker Rul) og markér slotten Brugt. label bærer også save-DC'en for
// kategori-E-spells. Save-spells uden skade (Sleep) har tomt rollExpr → vi viser
// blot DC-linjen i terning-området. Vi reloader IKKE (det ville nulstille feltet);
// updateSpellDisplay skjuler Kast-knappen når rækken ikke længere er ledig.
function castSpell(level, idx, rollExpr, label) {
  if (slotUsedCount(level) >= (slotTotals[level] || 0)) {
    alert("Ingen slots tilbage på level " + level + "!");
    return;
  }
  if (rollExpr) {
    quickRoll(rollExpr, label, 1);
  } else {
    // Ingen skade at rulle — vis save-DC-linjen i terning-området.
    document.getElementById("dice-expr").value = "";
    document.getElementById("dice-result").innerHTML =
      `<span style="color:var(--muted);font-size:.72rem">${escHtml(label)}</span>`;
  }
  fetch(BASE + "/api/spells", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, spell_index: idx, state: "used"})
  })
  .then(r => r.json())
  .then(data => {
    spellsUsed = Object.fromEntries(Object.entries(data.spells_used).map(([k, v]) => [parseInt(k), v]));
    spellsActive = Object.fromEntries(Object.entries(data.spells_active).map(([k, v]) => [parseInt(k), v]));
    updateSpellDisplay(level);
  });
}

// Brug en ladning (fx en Magic Stone-sten). Rammer den 0 → spell bliver "Brugt".
// Angreb er server-renderet, så vi reloader bagefter.
function spendCharge(level, spellIndex) {
  fetch(BASE + "/api/spell_charge", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, spell_index: spellIndex, delta: -1})
  }).then(() => location.reload());
}

// Skift en spells angrebs-tilstand (Produce Flame: nærkamp ⇄ kastet). Serveren
// rykker til næste tilstand i gruppen og gemmer valget; siden genindlæses.
function cycleSpellMode(level, spellIndex) {
  fetch(BASE + "/api/spell_mode", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, spell_index: spellIndex})
  }).then(() => location.reload());
}

// Skift et kastbart våbens tilstand (nærkamp ⇄ kastet) via dets inventar-indeks.
function cycleWeaponThrow(invIndex) {
  fetch(BASE + "/api/weapon_throw", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, inv_index: invIndex})
  }).then(() => location.reload());
}

function updateSpellDisplay(level) {
  document.querySelectorAll(`[id^="spell-${level}-"]`).forEach(row => {
    const idx = parseInt(row.id.replace(`spell-${level}-`, ""));
    const sid = row.dataset.spellId;
    const st = spellState(level, idx);
    row.className = "spell-row" + (st !== "free" ? " " + st : "");
    row.onclick = () => showDetail("spell", sid);
    const statusEl = row.querySelector(".spell-status");
    if (statusEl) {
      statusEl.textContent = STATE_LABEL[st];
      statusEl.className = "spell-status " + st;
      statusEl.onclick = (e) => { e.stopPropagation(); cycleSpell(level, idx); };
    }
    // ⚡ Kast-knappen giver kun mening på en ledig slot (kan ikke kaste en brugt spell).
    const castBtn = row.querySelector(".spell-cast-btn");
    if (castBtn) castBtn.style.display = (st === "free") ? "" : "none";
  });
  updatePips(level);
  const total = slotTotals[level] || 0;
  const slotEl = document.getElementById("slots-" + level);
  if (slotEl) slotEl.textContent = (total - slotUsedCount(level)) + " / " + total;
}

function updatePips(level) {
  const pipsEl = document.getElementById("pips-" + level);
  if (!pipsEl) return;
  const usedCount = slotUsedCount(level);
  const total = slotTotals[level] || 0;
  let html = "";
  for (let i = 0; i < total; i++) {
    html += `<span class="pip ${i < usedCount ? "used" : "free"}"></span>`;
  }
  pipsEl.innerHTML = html;
}

// ── Dice roller ───────────────────────────────────────────────────────────
// Value-knapperne (til-hit, skade, skills, saves …) RULLER ikke — de sætter blot
// udtrykket i feltet via setDice(). Man ruller først når man trykker ⚄ Rul (eller
// Enter). Det skal føles som at slå med rigtige terninger.
let pendingMin = null;       // damage-gulv (min 1) husket fra value-knappen til næste Rul
let pendingLabel = "";       // hvad rulles der for — vises over resultatet ved Rul
let pendingGuidance = false; // et armeret Guidance-rul afventer at man trykker Rul

function rollDice(min) {
  const expr = document.getElementById("dice-expr").value.trim() || "1d20";
  const useMin = (min != null) ? min : pendingMin;   // value-knappens min huskes til Rul
  let url = BASE + "/api/roll/" + encodeURIComponent(expr);
  if (useMin != null) url += "?min=" + useMin;
  fetch(url)
  .then(r => r.json())
  .then(data => {
    const el = document.getElementById("dice-result");
    if (data.error) {
      el.innerHTML = `<span style="color:var(--red)">${data.error}</span>`;
      return;
    }
    const rollStr = data.rolls.join("+");
    const modStr = data.modifier !== 0 ? (data.modifier > 0 ? "+" + data.modifier : data.modifier) : "";
    const flooredStr = data.floored ? ` <span style="color:var(--muted)">(min ${useMin})</span>` : "";
    const labelStr = pendingLabel ? `<span style="color:var(--muted);font-size:.72rem">${escHtml(pendingLabel)}</span><br>` : "";
    el.innerHTML = labelStr + `<span class="total">${data.total}</span><br><span class="detail">[${rollStr}]${modStr}${flooredStr}</span>`;
    // Guidance forbruges FØRST når det guidede rul faktisk sker (ikke ved populate).
    if (pendingGuidance && guidanceArmed && guidanceIdx >= 0) {
      guidanceArmed = false;
      pendingGuidance = false;
      renderGuidanceChip();
      fetch(BASE + "/api/buffs", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({char: CHAR, action: "remove", target: "character", index: guidanceIdx})
      }).then(() => setTimeout(() => location.reload(), 1500));
    }
  });
}

// Sæt et udtryk i terningefeltet UDEN at rulle. min (damage-gulv) og label huskes,
// så Rul kan bruge dem. Result-feltet viser en "tryk Rul"-hint.
function setDice(expr, label, min) {
  document.getElementById("dice-expr").value = expr;
  pendingMin = (min != null) ? min : null;
  pendingLabel = label || "";
  const el = document.getElementById("dice-result");
  el.innerHTML = `<span style="color:var(--muted);font-size:.72rem">${label ? escHtml(label) + " — " : ""}tryk ⚄ Rul</span>`;
}

// Value-knap: sæt udtryk i feltet (ruller ikke). Navnet bevares for de mange
// eksisterende onclick-kald i skabelonen.
function quickRoll(expr, label, min) {
  pendingGuidance = false;
  setDice(expr, label, min);
}

// Manuel redigering af feltet løsriver det fra en value-knap → almindeligt rul
// uden husket min/label/guidance.
function onDiceInput() {
  pendingMin = null;
  pendingLabel = "";
  pendingGuidance = false;
}

// ── Guidance: +1 competence på ÉT angreb/save/skill (engangs) ───────────────
let guidanceIdx = charBuffs.findIndex(b => b && b.spell_id === "guidance");
let guidanceArmed = false;

function renderGuidanceChip() {
  const el = document.getElementById("guidance-chip");
  if (!el) return;
  if (guidanceIdx < 0) { el.style.display = "none"; return; }
  el.style.display = "inline-flex";
  el.classList.toggle("armed", guidanceArmed);
  el.textContent = guidanceArmed
    ? "⚡ Guidance armet — næste angreb/save/skill får +1 (tap = fortryd)"
    : "⚡ Guidance klar — tap for at lægge +1 på næste angreb/save/skill";
}

function toggleGuidance() {
  if (guidanceIdx < 0) return;
  guidanceArmed = !guidanceArmed;
  renderGuidanceChip();
}

// Læg delta til den efterstillede modifier i et terninge-udtryk ("1d20+5" → +6).
function addToMod(expr, delta) {
  const mm = expr.match(/([+-]\d+)\s*$/);
  if (mm) {
    const n = parseInt(mm[1], 10) + delta;
    return expr.slice(0, mm.index) + (n >= 0 ? "+" : "") + n;
  }
  return expr + (delta >= 0 ? "+" : "") + delta;
}

// Value-knap der kan modtage Guidance. Er buffen armet, sættes udtrykket i feltet
// med +1 allerede lagt til (så man kan se det), og markeres som ventende guidance.
// Selve buffen forbruges først når man trykker Rul (se rollDice) — ellers ville et
// utaget slag brænde buffen. Ruller ikke selv.
function guidedRoll(expr, label, min) {
  if (guidanceArmed && guidanceIdx >= 0) {
    setDice(addToMod(expr, 1), (label || "") + " (+1 Guidance)", min);
    pendingGuidance = true;
    return;
  }
  pendingGuidance = false;
  setDice(expr, label, min);
}
renderGuidanceChip();

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

// ── Detail popup ──────────────────────────────────────────────────────────
function showDetail(dtype, did) {
  fetch(BASE + `/api/detail/${dtype}/${did}`)
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    const title = document.getElementById("modal-title");
    const subtitle = document.getElementById("modal-subtitle");
    const body = document.getElementById("modal-body");

    if (dtype === "spell") {
      title.textContent = data.name;
      subtitle.textContent = data.school || "";
      body.innerHTML = `
        ${row("Components", data.components)}
        ${row("Cast time", data.cast_time)}
        ${row("Range", data.range)}
        ${row(data.target_label || "Target", data.target)}
        ${row("Duration", data.duration)}
        ${row("Save", data.save)}
        ${row("SR", data.spell_resistance)}
        <div style="margin-top:.7rem;line-height:1.5;white-space:pre-line">${mdText(data.description)}</div>`;
    } else if (dtype === "skill") {
      title.textContent = data.name;
      subtitle.textContent = `Ability: ${(data.ability||"").toUpperCase()} · ${data.trained_only ? "Trained only" : "Untrained"}`;
      body.innerHTML = data.description
        ? `<p style="line-height:1.6">${escHtml(data.description)}</p>`
        : "";
    } else if (dtype === "feat") {
      title.textContent = data.name;
      subtitle.textContent = `${data.type || ""}${data.prerequisites ? " · Kræver: " + data.prerequisites : ""}`;
      body.innerHTML = `<p>${data.benefit || ""}</p>
        ${data.normal ? `<p style="margin-top:.5rem;color:var(--muted)"><em>Normal: ${data.normal}</em></p>` : ""}
        ${data.special ? `<p style="margin-top:.5rem;color:var(--muted)"><em>Special: ${data.special}</em></p>` : ""}`;
    } else if (dtype === "condition") {
      title.textContent = data.name;
      subtitle.textContent = data.summary || "";
      body.innerHTML = `<p style="line-height:1.5">${data.description || ""}</p>`;
    } else if (dtype === "ability") {
      const KIND = {ex: "Extraordinary (Ex)", su: "Supernatural (Su)", sp: "Spell-like (Sp)"};
      title.textContent = data.name;
      subtitle.textContent = KIND[data.kind] || "";
      body.innerHTML = `<p style="line-height:1.6">${escHtml(data.description || "")}</p>`;
    }

    // Gør condition-ord i beskrivelsen klikbare (ikke for skills — kort tekst)
    if (dtype === "spell" || dtype === "feat" || dtype === "condition") {
      linkConditions(body, dtype === "condition" ? did : null);
    }

    document.getElementById("modal-overlay").classList.add("open");
  });
}

function row(label, val) {
  if (!val) return "";
  return `<div class="modal-row"><span class="modal-key">${label}</span><span class="modal-val">${val}</span></div>`;
}

function closeModal(event) {
  if (event.target === document.getElementById("modal-overlay"))
    document.getElementById("modal-overlay").classList.remove("open");
}

document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    document.getElementById("modal-overlay").classList.remove("open");
    document.getElementById("item-modal-overlay").classList.remove("open");
    document.getElementById("prep-overlay").classList.remove("open");
    closeLu();
    hideSpellTooltip();
  }
});

// ── Spell preparation data (from server) ──────────────────────────────────
// availableSpells: {level: [{id, name, school, ...}, ...]}
const availableSpells = D.availableSpells;
// currentPrepared: mutable copy of spells_prepared
let currentPrepared = D.currentPrepared;
currentPrepared = Object.fromEntries(
  Object.entries(currentPrepared).map(([k, v]) => [parseInt(k), v])
);

// ── Domain spell data ──────────────────────────────────────────────────────
// domainSlots: {level: 1}  ·  domainAvailable: {level: [{id, name, school, ...}]}
const domainSlots = D.domainSlots;
const domainAvailable = D.domainAvailable;
let currentDomainPrepared = D.currentDomainPrepared;
currentDomainPrepared = Object.fromEntries(
  Object.entries(currentDomainPrepared).map(([k, v]) => [parseInt(k), v])
);
let newDomainPrepared = {};

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

// ── Spell tooltip ─────────────────────────────────────────────────────────
const spellLookup = {};
Object.values(availableSpells).forEach(arr => arr.forEach(s => { spellLookup[s.id] = s; }));
Object.values(domainAvailable).forEach(arr => arr.forEach(s => { spellLookup[s.id] = s; }));

// Spell-like abilities — preloaded from server
const slaSpells = D.slaSpells;
slaSpells.forEach(e => { if (e.spell) spellLookup[e.id] = e.spell; });

function showSlaTooltip(event, spellId) {
  const entry = slaSpells.find(e => e.id === spellId);
  if (entry && entry.spell) showSpellTooltip(entry.spell, event.currentTarget);
}

function truncDesc(desc, max) {
  if (!desc || desc.length <= max) return desc || "";
  const cut = desc.slice(0, max);
  const dot = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
  return (dot > max * 0.5 ? desc.slice(0, dot + 1) : cut.replace(/\s\S+$/, "")) + " …";
}

function showSpellTooltip(spell, chipEl) {
  const tt = document.getElementById("spell-tooltip");
  const meta = [spell.school, spell.cast_time].filter(Boolean).join(" · ");
  tt.innerHTML =
    `<div class="tt-name">${escHtml(spell.name)}</div>` +
    (meta ? `<div class="tt-meta">${escHtml(meta)}</div>` : "") +
    `<div class="tt-desc">${escHtml(truncDesc(spell.description, 200))}</div>`;

  const r = chipEl.getBoundingClientRect();
  const tw = 280, gap = 8;
  let left = Math.min(r.left, window.innerWidth - tw - 10);
  let top  = r.bottom + gap;
  // flip above chip if too close to bottom
  if (top + 130 > window.innerHeight) top = r.top - 130 - gap;
  tt.style.left = left + "px";
  tt.style.top  = top  + "px";
  tt.style.display = "block";
}

function hideSpellTooltip() {
  document.getElementById("spell-tooltip").style.display = "none";
}

// Skill-opdeling på hover: viser hvordan totalen er sammensat (ranks + ability +
// misc m/ kilde + synergi + ACP + effekter). Genbruger spell-tooltip-elementet.
const skillBreakdowns = D.skillBreakdowns;

// Fælles renderer for en "total = sum af navngivne dele"-tooltip (skills + angreb).
// b = {name, total, parts:[{label,value}]}. Genbruger spell-tooltip-elementet.
function renderBreakdownTooltip(b, el) {
  if (!b || !b.parts || !b.parts.length) return;
  const tt = document.getElementById("spell-tooltip");
  const sgn = n => (n >= 0 ? "+" : "") + n;
  // Værdier er enten tal (til-hit/skill: vises med fortegn) eller strenge
  // (skade-terning som "1d8": vises råt). p.die er en terning-del.
  const fmt = v => (typeof v === "number" ? sgn(v) : escHtml(String(v)));
  const rows = b.parts.map(p =>
    `<div style="display:flex;justify-content:space-between;gap:1.2rem">
       <span>${escHtml(p.label)}</span><span>${fmt(p.die !== undefined ? p.die : p.value)}</span></div>`).join("");
  tt.innerHTML =
    `<div class="tt-name">${escHtml(b.name)} = ${fmt(b.total)}</div>` +
    `<div class="tt-desc" style="margin-top:.3rem">${rows}</div>`;
  const r = el.getBoundingClientRect();
  const tw = 220, gap = 8;
  const left = Math.min(r.left, window.innerWidth - tw - 10);
  let top = r.bottom + gap;
  if (top + 170 > window.innerHeight) top = r.top - 170 - gap;
  tt.style.left = left + "px";
  tt.style.top  = top + "px";
  tt.style.display = "block";
}

function showSkillBreakdown(sid, el) {
  renderBreakdownTooltip(skillBreakdowns[sid], el);
}

// Angrebs-til-hit-opdeling: BAB + ability + størrelse + våben + effekter. Data
// ligger på selve elementet (data-bd), så vi ikke behøver et server-keyet katalog.
function showAttackBreakdown(el) {
  try { renderBreakdownTooltip(JSON.parse(el.dataset.bd), el); } catch (e) {}
}

// Skill-tooltip i level-up — genbruger spell-tooltip-elementet (z-index over modalen).
function showSkillTooltip(sid, el) {
  const s = allSkillsDB.find(x => x.id === sid);
  if (!s) return;
  const tt = document.getElementById("spell-tooltip");
  const meta = [(s.ability || "").toUpperCase(), s.trained_only ? "Trænet kun" : "Utrænet"]
    .filter(Boolean).join(" · ");
  tt.innerHTML =
    `<div class="tt-name">${escHtml(s.name)}</div>` +
    (meta ? `<div class="tt-meta">${escHtml(meta)}</div>` : "") +
    `<div class="tt-desc">${escHtml(truncDesc(s.description, 200))}</div>`;
  const r = el.getBoundingClientRect();
  const tw = 280, gap = 8;
  let left = Math.min(r.left, window.innerWidth - tw - 10);
  let top  = r.bottom + gap;
  if (top + 130 > window.innerHeight) top = r.top - 130 - gap;
  tt.style.left = left + "px";
  tt.style.top  = top  + "px";
  tt.style.display = "block";
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

// ── Spontan casting (sorcerer/bard): kendt liste + slot-pulje ──────────────
// Spontane castere forbereder ikke; de caster fra en fast kendt liste indtil
// dagens slots pr. niveau er brugt. "Kast" tæller en slot op/ned; loftet
// håndhæves server-side. Lær/glem reloader for at gentegne listen.

function castKnown(level, delta) {
  fetch(BASE + "/api/cast_known", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, delta})
  })
  .then(r => r.json())
  .then(d => {
    if (!d.ok) return;
    // Serveren clamper til [0, total]; vis det resulterende ledige antal.
    const el = document.getElementById("known-slots-" + level);
    if (el) el.textContent = (d.total - d.used) + "/" + d.total;
    if (delta > 0 && d.total === 0) alert("Ingen slots på level " + level + ".");
  });
}

function learnKnown(level, spellId) {
  fetch(BASE + "/api/spells_known", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "add", level, spell_id: spellId})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) location.reload(); });
}

function forgetKnown(level, spellId) {
  if (!confirm("Glem dette spell fra den kendte liste?")) return;
  fetch(BASE + "/api/spells_known", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "remove", level, spell_id: spellId})
  })
  .then(r => r.json())
  .then(d => { if (d.ok) location.reload(); });
}

// ── Preparation modal ─────────────────────────────────────────────────────
// newPrepared tracks the in-progress selection: {level: [spell_id, ...]}
let newPrepared = {};
const prepCollapsed = new Set();

function togglePrepLevel(lvl) {
  if (prepCollapsed.has(lvl)) prepCollapsed.delete(lvl);
  else prepCollapsed.add(lvl);
  const collapsed = prepCollapsed.has(lvl);
  ["left", "right"].forEach(side => {
    const body    = document.getElementById(`prep-lbody-${side}-${lvl}`);
    const chevron = document.getElementById(`prep-chevron-${side}-${lvl}`);
    if (body)    body.style.display         = collapsed ? "none" : "";
    if (chevron) chevron.style.transform    = collapsed ? "rotate(-90deg)" : "";
  });
}

function openPrepModal() {
  // Deep copy currentPrepared as starting point
  newPrepared = {};
  Object.entries(currentPrepared).forEach(([lvl, ids]) => {
    newPrepared[parseInt(lvl)] = [...ids];
  });
  newDomainPrepared = {};
  Object.entries(currentDomainPrepared).forEach(([lvl, id]) => {
    if (id) newDomainPrepared[parseInt(lvl)] = id;
  });

  renderPrepModal();
  document.getElementById("prep-overlay").classList.add("open");
}

function renderPrepModal() {
  const left  = document.getElementById("prep-left");
  const right = document.getElementById("prep-right");
  const levelNums = Object.keys(slotTotals).map(Number).sort((a, b) => a - b);

  left.innerHTML  = '<div class="prep-col-title">Tilgængelige spells</div>';
  right.innerHTML = '<div class="prep-col-title">Forberedte spells</div>';

  // Wizard forbereder kun FRA spellbogen (spells_known), ikke hele klasse-listen.
  const isSpellbook = (D.castType === "spellbook");

  levelNums.forEach(lvl => {
    let spellsAtLevel = (availableSpells[lvl] || []).slice();
    if (isSpellbook) {
      const book = new Set(D.spellsKnown[lvl] || D.spellsKnown[String(lvl)] || []);
      spellsAtLevel = spellsAtLevel.filter(sp => book.has(sp.id));
    }
    spellsAtLevel.sort((a, b) => a.name.localeCompare(b.name));
    const total    = slotTotals[lvl] || 0;
    const prepared = newPrepared[lvl] || [];
    const full     = prepared.length >= total;

    const collapsed = prepCollapsed.has(lvl);

    function makeHdr(side) {
      const hdr = document.createElement("div");
      hdr.className = "prep-level-header";
      hdr.style.cursor = "pointer";
      hdr.onclick = () => togglePrepLevel(lvl);
      const chevron = document.createElement("span");
      chevron.id = `prep-chevron-${side}-${lvl}`;
      chevron.className = "prep-level-chevron";
      chevron.textContent = "▾";
      if (collapsed) chevron.style.transform = "rotate(-90deg)";
      hdr.appendChild(chevron);
      hdr.appendChild(document.createTextNode(`Level ${lvl} — ${prepared.length}/${total} slots`));
      return hdr;
    }

    // ── Venstre kolonne: tilgængelige spells ──
    const lBlock = document.createElement("div");
    lBlock.className = "prep-level-block";
    lBlock.appendChild(makeHdr("left"));

    const lBody = document.createElement("div");
    lBody.id = `prep-lbody-left-${lvl}`;
    if (collapsed) lBody.style.display = "none";

    if (spellsAtLevel.length === 0) {
      const empty = document.createElement("div");
      empty.style.cssText = "color:var(--muted);font-size:.8rem;font-style:italic;padding:.3rem 0";
      empty.textContent = "Ingen spells tilgængelige";
      lBody.appendChild(empty);
    } else {
      spellsAtLevel.forEach(spell => {
        const row = document.createElement("div");
        row.className = "prep-avail-row" + (full ? " prep-avail-full" : "");
        row.innerHTML =
          `<span class="prep-avail-name">${escHtml(spell.name)}</span>` +
          `<span class="prep-avail-school">${escHtml(spell.school || "")}</span>`;
        if (!full) row.onclick = () => addPrepSpell(lvl, spell.id);
        if (spell.description) {
          row.addEventListener("mouseenter", () => showSpellTooltip(spell, row));
          row.addEventListener("mouseleave", hideSpellTooltip);
        }
        lBody.appendChild(row);
      });
    }
    lBlock.appendChild(lBody);
    left.appendChild(lBlock);

    // ── Højre kolonne: forberedte slots ──
    const rBlock = document.createElement("div");
    rBlock.className = "prep-level-block";
    rBlock.appendChild(makeHdr("right"));

    const rBody = document.createElement("div");
    rBody.id = `prep-lbody-right-${lvl}`;
    if (collapsed) rBody.style.display = "none";

    for (let i = 0; i < total; i++) {
      const slotRow = document.createElement("div");
      const spellId = prepared[i];
      if (spellId) {
        const sp = (availableSpells[lvl] || []).find(s => s.id === spellId);
        slotRow.className = "prep-slot-row prep-slot-filled";
        const nameSpan = document.createElement("span");
        nameSpan.className = "prep-slot-name";
        nameSpan.textContent = sp ? sp.name : spellId;
        if (sp && sp.description) {
          nameSpan.style.cursor = "help";
          nameSpan.addEventListener("mouseenter", () => showSpellTooltip(sp, nameSpan));
          nameSpan.addEventListener("mouseleave", hideSpellTooltip);
        }
        const removeBtn = document.createElement("button");
        removeBtn.className = "prep-slot-remove";
        removeBtn.textContent = "×";
        removeBtn.title = "Fjern";
        const capturedIdx = i;
        removeBtn.onclick = () => removePrepSpell(lvl, capturedIdx);
        slotRow.appendChild(nameSpan);
        slotRow.appendChild(removeBtn);
      } else {
        slotRow.className = "prep-slot-row prep-slot-empty";
        const ph = document.createElement("span");
        ph.className = "prep-slot-placeholder";
        ph.textContent = "── ledig slot ──";
        slotRow.appendChild(ph);
      }
      rBody.appendChild(slotRow);
    }
    rBlock.appendChild(rBody);
    right.appendChild(rBlock);

    // ── Domæne-slot for dette niveau (hvis nogen) ──
    if (domainSlots[lvl]) {
      const chosen = newDomainPrepared[lvl];
      const dAvail = (domainAvailable[lvl] || []).slice().sort((a, b) => a.name.localeCompare(b.name));

      // Venstre: tilgængelige domæne-formler
      const dlBlock = document.createElement("div");
      dlBlock.className = "prep-level-block";
      const dlHdr = document.createElement("div");
      dlHdr.className = "prep-level-header";
      dlHdr.textContent = `Level ${lvl} — ⛨ domæne`;
      dlBlock.appendChild(dlHdr);
      if (dAvail.length === 0) {
        const empty = document.createElement("div");
        empty.style.cssText = "color:var(--muted);font-size:.8rem;font-style:italic;padding:.3rem 0";
        empty.textContent = "Ingen domæne-formler tilgængelige";
        dlBlock.appendChild(empty);
      } else {
        dAvail.forEach(spell => {
          const row = document.createElement("div");
          row.className = "prep-avail-row" + (chosen ? " prep-avail-full" : "");
          row.innerHTML =
            `<span class="prep-avail-name">${escHtml(spell.name)}</span>` +
            `<span class="prep-avail-school">${escHtml(spell.school || "")}</span>`;
          if (!chosen) row.onclick = () => addDomainSpell(lvl, spell.id);
          if (spell.description) {
            row.addEventListener("mouseenter", () => showSpellTooltip(spell, row));
            row.addEventListener("mouseleave", hideSpellTooltip);
          }
          dlBlock.appendChild(row);
        });
      }
      left.appendChild(dlBlock);

      // Højre: den enkelte domæne-slot
      const drBlock = document.createElement("div");
      drBlock.className = "prep-level-block";
      const drHdr = document.createElement("div");
      drHdr.className = "prep-level-header";
      drHdr.textContent = `Level ${lvl} — ⛨ domæne (${chosen ? 1 : 0}/1)`;
      drBlock.appendChild(drHdr);
      const dSlotRow = document.createElement("div");
      if (chosen) {
        const sp = dAvail.find(s => s.id === chosen);
        dSlotRow.className = "prep-slot-row prep-slot-filled";
        const nameSpan = document.createElement("span");
        nameSpan.className = "prep-slot-name";
        nameSpan.textContent = sp ? sp.name : chosen;
        if (sp && sp.description) {
          nameSpan.style.cursor = "help";
          nameSpan.addEventListener("mouseenter", () => showSpellTooltip(sp, nameSpan));
          nameSpan.addEventListener("mouseleave", hideSpellTooltip);
        }
        const removeBtn = document.createElement("button");
        removeBtn.className = "prep-slot-remove";
        removeBtn.textContent = "×";
        removeBtn.title = "Fjern";
        removeBtn.onclick = () => removeDomainSpell(lvl);
        dSlotRow.appendChild(nameSpan);
        dSlotRow.appendChild(removeBtn);
      } else {
        dSlotRow.className = "prep-slot-row prep-slot-empty";
        const ph = document.createElement("span");
        ph.className = "prep-slot-placeholder";
        ph.textContent = "── ledig domæne-slot ──";
        dSlotRow.appendChild(ph);
      }
      drBlock.appendChild(dSlotRow);
      right.appendChild(drBlock);
    }
  });
}

function addDomainSpell(lvl, spellId) {
  newDomainPrepared[lvl] = spellId;
  renderPrepModal();
}

function removeDomainSpell(lvl) {
  delete newDomainPrepared[lvl];
  renderPrepModal();
}

function toggleDomainSpell(lvl, used) {
  fetch(BASE + "/api/domain_used", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level: lvl, used: !used})
  })
  .then(r => r.json())
  .then(data => { if (data.ok) window.location.reload(); });
}

function addPrepSpell(lvl, spellId) {
  if (!newPrepared[lvl]) newPrepared[lvl] = [];
  if (newPrepared[lvl].length >= (slotTotals[lvl] || 0)) return;
  newPrepared[lvl].push(spellId);
  renderPrepModal();
}

function removePrepSpell(lvl, idx) {
  if (!newPrepared[lvl]) return;
  newPrepared[lvl].splice(idx, 1);
  renderPrepModal();
}

function prepNewDay() {
  newPrepared = {};
  newDomainPrepared = {};
  renderPrepModal();
}

function savePrepared() {
  fetch(BASE + "/api/prepare", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, prepared_spells: newPrepared, domain_prepared: newDomainPrepared})
  })
  .then(r => r.json())
  .then(data => {
    if (!data.ok) return;
    // Update state
    currentPrepared = Object.fromEntries(
      Object.entries(data.prepared_spells).map(([k, v]) => [parseInt(k), v])
    );
    currentDomainPrepared = Object.fromEntries(
      Object.entries(data.domain_prepared || {}).map(([k, v]) => [parseInt(k), v])
    );
    spellsUsed = {};
    document.getElementById("prep-overlay").classList.remove("open");
    // Reload page to show new preparation
    window.location.reload();
  });
}

function closePrepIfOutside(event) {
  if (event.target === document.getElementById("prep-overlay")) {
    document.getElementById("prep-overlay").classList.remove("open");
    hideSpellTooltip();
  }
}

// ── Inventory ─────────────────────────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement("div");
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

// Escape HTML, then render the limited markdown used in SRD spell text
// (**bold** and _italic_/*italic*). Safe: HTML is escaped before markers run.
function mdText(s) {
  if (!s) return "";
  let t = escHtml(s);
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  t = t.replace(/_([^_]+)_/g, "<em>$1</em>");
  return t;
}

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
    let html =
      `<div class="inv-c1">${nameCell}${badge}</div>
       <span class="inv-qty-stepper">
         <button class="inv-step" onclick="adjQty(${idx},-1)" title="−1 (fx brug ammo)">−</button>
         <span class="inv-qty inv-editable" onclick="editInvField(this,${idx},'qty')" title="Klik for at indtaste antal">×${item.qty}</span>
         <button class="inv-step" onclick="adjQty(${idx},1)" title="+1">+</button>
       </span>
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

// ── Skift våben ─────────────────────────────────────────────────────────────
// Hurtig-vælger: list inventarets våben og skift dem mellem hånd og rygsæk uden
// at gå gennem hver genstands-modal. Våben skiftes uafhængigt (to-våbenskæmpe).
function openWeaponSwitch() {
  const list = document.getElementById("weapon-switch-list");
  const NON_WIELDED = {backpack: "rygsæk", stored: "opbevaret", dropped: "droppet", worn: "båret"};
  const weapons = inventoryData
    .map((it, idx) => ({it, idx}))
    .filter(x => (x.it.ref || "").startsWith("weapons/"));
  if (!weapons.length) {
    list.innerHTML = `<p style="color:var(--muted);font-size:.85rem">Ingen våben i inventaret. Tilføj våben under Udrustning.</p>`;
  } else {
    list.innerHTML = weapons.map(({it, idx}) => {
      const wielded = it.state === "wielded";
      const badge = wielded
        ? `<span class="inv-state st-wielded">i hånden</span>`
        : `<span class="inv-state">${NON_WIELDED[it.state] || "rygsæk"}</span>`;
      const btn = wielded
        ? `<button class="notes-cancel-btn" onclick="quickWield(${idx},'backpack')">Læg i rygsæk</button>`
        : `<button class="notes-save-btn" onclick="quickWield(${idx},'wielded')">Tag i hånden</button>`;
      return `<div style="display:flex;justify-content:space-between;align-items:center;gap:.6rem;padding:.4rem 0;border-bottom:1px solid var(--border)">
                <span style="min-width:0;overflow:hidden;text-overflow:ellipsis">${escHtml(it.name)} ${badge}</span>
                ${btn}
              </div>`;
    }).join("");
  }
  document.getElementById("weapon-switch-overlay").classList.add("open");
}

// Skift ét våbens tilstand (hånd/rygsæk) og genindlæs — afledte angreb + hånd-
// forbrug + AC skal genberegnes. Genbruger inventar-update-endpointet.
function quickWield(idx, state) {
  fetch(BASE + "/api/inventory", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "update", index: idx, state})
  })
  .then(r => r.json())
  .then(data => { if (!data.error) location.reload(); });
}

function closeWeaponSwitchIfOutside(event) {
  if (event.target === document.getElementById("weapon-switch-overlay"))
    document.getElementById("weapon-switch-overlay").classList.remove("open");
}

// ── Angrebs-editor (manuelle angreb) ──────────────────────────────────────
// Kilde styrer skade-modellen: spell → fast skade (Str ikke med); våben →
// terning + Str×mult. Vi gemmer server-side og reloader (angreb påvirker
// gating/hint), præcis som buffs.
function onAttackSourceChange() {
  const spell = document.getElementById("attack-modal-source").value === "spell";
  document.getElementById("attack-modal-requires-row").style.display = spell ? "block" : "none";
  document.getElementById("attack-modal-strmult-row").style.display  = spell ? "none" : "block";
  document.getElementById("attack-modal-dmg-hint").textContent =
    spell ? "(fast — Str tælles ikke med)" : "(terning; Str lægges til)";
}

function openAttackModal(mode, idx) {
  const editing = mode === "edit";
  const a = editing ? attacksData.find(x => x.idx === idx) : null;
  document.getElementById("attack-modal-title").textContent = editing ? "Rediger angreb" : "Nyt angreb";
  document.getElementById("attack-modal-idx").value      = editing ? idx : "";
  document.getElementById("attack-modal-name").value     = a ? a.name : "";
  document.getElementById("attack-modal-kind").value     = a ? a.kind : "melee";
  document.getElementById("attack-modal-source").value   = a ? a.source : "weapon";
  document.getElementById("attack-modal-requires").value = a ? (a.requires || "") : "";
  document.getElementById("attack-modal-bonus").value    = a ? a.bonus : 0;
  // Skade: fast (spell) vises fixed_damage, ellers base_damage.
  document.getElementById("attack-modal-damage").value =
    a ? (a.source === "spell" ? a.fixed_damage : a.base_damage) : "";
  document.getElementById("attack-modal-strmult").value =
    (a && a.source !== "spell") ? a.str_damage_mult : "";
  document.getElementById("attack-modal-crit").value  = a ? a.crit : "x2";
  document.getElementById("attack-modal-type").value  = a ? a.type : "";
  document.getElementById("attack-modal-range").value = a ? a.range : "";
  document.getElementById("attack-modal-remove").style.display = editing ? "block" : "none";
  onAttackSourceChange();
  document.getElementById("attack-modal-overlay").classList.add("open");
  document.getElementById("attack-modal-name").focus();
}

function editAttack(idx) { openAttackModal("edit", idx); }

function saveAttack() {
  const name = document.getElementById("attack-modal-name").value.trim();
  if (!name) { document.getElementById("attack-modal-name").focus(); return; }
  const idxRaw = document.getElementById("attack-modal-idx").value;
  const editing = idxRaw !== "";
  const attack = {
    name,
    kind:     document.getElementById("attack-modal-kind").value,
    source:   document.getElementById("attack-modal-source").value,
    requires: document.getElementById("attack-modal-requires").value.trim(),
    bonus:    parseInt(document.getElementById("attack-modal-bonus").value) || 0,
    damage:   document.getElementById("attack-modal-damage").value.trim(),
    str_mult: document.getElementById("attack-modal-strmult").value.trim(),
    crit:     document.getElementById("attack-modal-crit").value.trim(),
    type:     document.getElementById("attack-modal-type").value.trim(),
    range:    document.getElementById("attack-modal-range").value.trim(),
  };
  const payload = {char: CHAR, action: editing ? "update" : "add", attack};
  if (editing) payload.index = parseInt(idxRaw);
  fetch(BASE + "/api/attacks", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  }).then(r => r.json()).then(d => { if (!d.error) location.reload(); });
}

function removeAttack() {
  const idxRaw = document.getElementById("attack-modal-idx").value;
  if (idxRaw === "") return;
  if (!confirm("Fjern dette angreb?")) return;
  fetch(BASE + "/api/attacks", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, action: "remove", index: parseInt(idxRaw)})
  }).then(r => r.json()).then(d => { if (!d.error) location.reload(); });
}

function closeAttackModalIfOutside(event) {
  if (event.target === document.getElementById("attack-modal-overlay"))
    document.getElementById("attack-modal-overlay").classList.remove("open");
}

// Skift/tilføj portræt: upload som multipart og genindlæs så billedet vises.
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

// Initial inventory render
updateInventoryDisplay({
  inventory:  inventoryData,
  weight:     currentWeight,
  enc:        currentEnc,
  enc_limits: encLimits,
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
