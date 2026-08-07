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



// ── Ledsagerens udstyr ────────────────────────────────────────────────────
// Barding tæller i dyrets AC, og vægten måles mod dyrets EGEN bæreevne (firbenede
// bærer ×1,5). Serveren regner alt; her sendes handlingen og siden genindlæses,
// fordi AC'en i statblokken ovenfor kan have ændret sig.
function compInvPost(body) {
  return fetch(BASE + "/api/companion_inventory", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({char: CHAR, ...body})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert("Kunne ikke: " + data.error); return; }
    location.reload();     // barding ændrer AC → hele statblokken skal gentegnes
  });
}

function compInvRemove(index) { compInvPost({action: "remove", index}); }

// Giv tilbage til ejeren. `antal` > 1 betyder at rækken er en stak der KAN deles
// (serveren afgør det — forbrugsvarer med ladninger sendes altid hele). Så
// spørges der hvor mange; ellers flytter ét klik bare genstanden.
function compInvGiveBack(index, antal) {
  const body = {action: "transfer", index, to_companion: false};
  if (antal > 1) {
    const svar = prompt(`Hvor mange af de ${antal} skal tilbage?`, antal);
    if (svar === null) return;                  // Annuller
    const n = parseInt(svar, 10);
    if (isNaN(n) || n < 1) return;
    body.qty = Math.min(n, antal);
  }
  compInvPost(body);
}
function compInvState(index, state) { compInvPost({action: "update", index, state}); }

function compInvBuy() {
  const sel = document.getElementById("comp-shop-select");
  if (!sel || !sel.value) return;
  // Barding sendes som "worn" — det er hele pointen med at købe den. Alt andet
  // i rygsækken. Serveren skubber selv en tidligere barding af.
  const state = sel.value.startsWith("armor/") ? "worn" : "backpack";
  compInvPost({action: "add", ref: sel.value, state});
}

// Butikslisten hentes fra /api/catalog med companion-parametrene, så priser og
// vægte er dyrets (barding-kolonnen), ikke Tjørns.
(function loadCompShop() {
  const sel = document.getElementById("comp-shop-select");
  if (!sel || !D.compSize) return;
  const q = new URLSearchParams({
    str: D.compStr || 10, size: D.compSize, magic: "0",
    companion_size: D.compSize, companion_animal: D.compAnimal || "",
  });
  fetch(BASE + "/api/catalog?" + q.toString())
    .then(r => r.json())
    .then(data => {
      const grupper = {};
      for (const it of data.items || []) (grupper[it.group] ||= []).push(it);
      sel.innerHTML = '<option value="">— vælg —</option>';
      for (const navn of Object.keys(grupper).sort()) {
        const og = document.createElement("optgroup");
        og.label = navn;
        for (const it of grupper[navn]) {
          const o = document.createElement("option");
          o.value = it.ref;
          o.textContent = `${it.name} — ${it.cost_str}, ${it.weight} lb`;
          og.appendChild(o);
        }
        sel.appendChild(og);
      }
    });
})();
