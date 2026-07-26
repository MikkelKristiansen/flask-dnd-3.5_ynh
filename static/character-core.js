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


// ── Delte HTML/markdown-hjælpere (bruges bredt: showDetail, buff-tooltips, cast-labels m.fl.) ──
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
