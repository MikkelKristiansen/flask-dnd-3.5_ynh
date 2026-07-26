// character-prep-modal.js — forberedelses-modalen (prepared castere: wizard/cleric/…).
//
// Udspaltet fra character-spells.js. Bygger et udkast (newPrepared/prepCollapsed/
// newDomainPrepared) og gemmer det. Loades EFTER character-spells.js + character-tooltips.js:
// refererer globale data/state derfra ved KALD-tid (currentPrepared, currentDomainPrepared,
// newDomainPrepared, availableSpells, domainSlots/Available, slotTotals, D, CHAR, BASE,
// escHtml, hideSpellTooltip). Funktionerne er globale (inline onclick i templates).

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

