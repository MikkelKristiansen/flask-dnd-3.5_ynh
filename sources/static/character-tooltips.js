// character-tooltips.js — hover-tooltips til karakterarket (spell/skill/angreb).
//
// Udspaltet fra character-spells.js. Rene visnings-funktioner der genbruger
// #spell-tooltip-elementet. Loades EFTER character-spells.js (og character-core.js),
// så de globale hjælpere/data de refererer ved KALD-tid findes: escHtml (core),
// slaSpells/skillBreakdowns (data-consts i character-spells.js), allSkillsDB (core/
// progression). Funktionerne er globale (kaldes fra inline onmouseenter i templates).

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
