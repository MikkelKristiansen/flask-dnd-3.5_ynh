// Justér en aktiv spells (kategori F-utility ELLER vedvarende kategori-E som
// Flaming Sphere) resterende varighed. reset=true → fuld varighed. Native enhed
// (min/timer/runder/dage) — serveren returnerer labelen. prefix vælger hvilket
// DOM-element der opdateres ("util" = Aktive effekter, "effect" = Spell-effekter).
function adjUtilDuration(level, idx, delta, reset, prefix) {
  prefix = prefix || "util";
  fetch(BASE + "/api/spell_duration", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, level, spell_index: idx, delta, reset: !!reset})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) return;
    const el = document.getElementById(`${prefix}-${level}-${idx}-dur`);
    if (!el) return;
    const done = data.left === 0;
    el.textContent = done ? "udløbet" : `${data.left}/${data.max} ${data.unit_label}`;
    el.classList.toggle("expired", done);
  });
}

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

