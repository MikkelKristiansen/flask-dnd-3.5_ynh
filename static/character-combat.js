// ── Manuelle angreb (redigerbare) ─────────────────────────────────────────
const attacksData = D.attacksData;


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
