/* equipment_picker.js — genbrugelig udrustningsbutik (UI-komponent).
 *
 * Ansvar: hent /api/catalog, tegn varerne i faner, hold styr på afkrydsninger
 * og vis live budget + vægt/encumbrance. Ren VISNING — den lægger kun sammen og
 * sammenligner; alle 3.5-regel-tal (pris, vægt, proficient, enc-grænser) kommer
 * færdige fra serveren. Holdt adskilt fra character.js med vilje.
 *
 * Brug fra værts-siden:
 *   EquipmentPicker.init({ cls, str, size, budgetCp, selected, onChange });
 *   EquipmentPicker.setBudget(cp);              // når startguld ændres
 *   EquipmentPicker.setContext({ cls, str, size, race });  // genhenter kataloget
 *   EquipmentPicker.getSelected();              // → [{ref, category, qty}]
 */
window.EquipmentPicker = (function () {
  "use strict";

  // Faner: top-niveau kategori (matcher katalogets `category`) → fane-label.
  const TABS = [
    { key: "alle",    label: "Alt udstyr" },
    { key: "weapons", label: "⚔ Våben" },
    { key: "armor",   label: "🛡 Rustning" },
    { key: "items",   label: "🎒 Udstyr" },
  ];

  const ENC_LABEL = { Light: "Let", Medium: "Middel", Heavy: "Tung", Overloaded: "Overbelastet" };

  const state = {
    items: [],            // beriget katalog fra /api/catalog
    encLimits: {},        // {light, medium, heavy}
    selected: new Map(),  // ref → {item, qty}
    base: "",             // WSGI script_root (YunoHost-subpath) — sættes af værten
    cls: "", str: 10, size: "medium", race: "",
    budgetCp: 0,
    category: "alle", search: "", onlyProf: false, onlyAfford: false,
    onChange: null,
  };

  // ── DOM-hjælpere (alt scopes under #eqp-root, så komponenten kan genbruges) ──
  const $ = (id) => document.getElementById(id);
  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function formatCost(cp) {
    if (cp === null || cp === undefined) return "—";
    if (cp === 0) return "—";
    const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
    return [gp && `${gp} gp`, sp && `${sp} sp`, c && `${c} cp`].filter(Boolean).join(" ");
  }

  // ── Datahentning ────────────────────────────────────────────────────────
  async function fetchCatalog() {
    const q = new URLSearchParams({ str: state.str, size: state.size });
    if (state.cls)  q.set("cls", state.cls);
    if (state.race) q.set("race", state.race);
    const res = await fetch(`${state.base}/api/catalog?${q.toString()}`);
    if (!res.ok) throw new Error(`/api/catalog: ${res.status}`);
    const data = await res.json();
    state.items = data.items || [];
    state.encLimits = data.enc_limits || {};
    // Behold valgte items, men opdater deres reference til de nye (vægt/pris kan
    // have ændret sig med str/size) — match på ref.
    const byRef = new Map(state.items.map((it) => [it.ref, it]));
    for (const [ref, sel] of state.selected) {
      if (byRef.has(ref)) sel.item = byRef.get(ref);
      else state.selected.delete(ref);
    }
  }

  // Pris-delta for én valgt materiale-mod (kom færdig fra serveren).
  function modDelta(item, key) {
    const m = (item.modifiers || []).find((x) => x.key === key);
    return m ? m.delta_cp : 0;
  }
  // Linjepris pr. styk = basispris + valgte mod-deltaer (ren summering).
  function lineCost(sel) {
    let cp = sel.item.cost_cp || 0;
    sel.mods.forEach((k) => (cp += modDelta(sel.item, k)));
    return cp;
  }

  // ── Totaler (ren summering — OK i JS) ────────────────────────────────────
  function totals() {
    let costCp = 0, weight = 0;
    for (const sel of state.selected.values()) {
      costCp += lineCost(sel) * sel.qty;
      weight += (sel.item.weight || 0) * sel.qty;
    }
    return { costCp, weight: Math.round(weight * 1000) / 1000 };
  }

  function encLevel(weight) {
    const l = state.encLimits;
    if (weight <= (l.light ?? Infinity))  return "Light";
    if (weight <= (l.medium ?? Infinity)) return "Medium";
    if (weight <= (l.heavy ?? Infinity))  return "Heavy";
    return "Overloaded";
  }

  // ── Rendering ─────────────────────────────────────────────────────────────
  function renderTabs() {
    const box = $("eqp-tabs");
    box.innerHTML = "";
    for (const t of TABS) {
      const b = el("button", "eqp-tab" + (state.category === t.key ? " active" : ""), t.label);
      b.type = "button";
      b.onclick = () => { state.category = t.key; renderTabs(); renderList(); };
      box.appendChild(b);
    }
  }

  function itemVisible(it) {
    if (state.category !== "alle" && it.category !== state.category) return false;
    if (state.onlyProf && !it.proficient) return false;
    if (state.onlyAfford) {
      const remaining = state.budgetCp - totals().costCp;
      const alreadyPicked = state.selected.has(it.ref);
      if (!alreadyPicked && (it.cost_cp || 0) > remaining) return false;
    }
    if (state.search) {
      const q = state.search.toLowerCase();
      if (!it.name.toLowerCase().includes(q) && !(it.group || "").toLowerCase().includes(q))
        return false;
    }
    return true;
  }

  function detailText(it) {
    const d = it.detail || {};
    if (it.category === "weapons") {
      return [d.dmg, d.crit, d.type].filter(Boolean).join(" · ");
    }
    if (it.category === "armor") {
      const parts = [];
      if (d.ac != null) parts.push(`+${d.ac} AC`);
      if (d.max_dex != null) parts.push(`maks Dex ${d.max_dex}`);
      if (d.check) parts.push(`ACP ${d.check}`);
      return parts.join(" · ");
    }
    return it.group || "";
  }

  function renderRow(it) {
    const sel = state.selected.get(it.ref);
    const checked = !!sel;
    // Rækken er en <div> (ikke <label>), så mod-checkboxe ikke også toggler varen.
    const row = el("div", "eqp-row" + (checked ? " picked" : "") +
                          (it.proficient ? "" : " not-prof"));
    const cb = el("input");
    cb.type = "checkbox";
    cb.className = "eqp-check";
    cb.checked = checked;
    cb.onchange = () => toggle(it, cb.checked);

    const main = el("div", "eqp-row-main");
    const name = el("div", "eqp-row-name", it.name +
      (it.recommended ? ' <span class="eqp-tag-rec" title="Anbefalet for klassen">★</span>' : "") +
      (it.proficient ? "" : ' <span class="eqp-tag-warn" title="Ikke proficient (straf)">⚠</span>'));
    name.onclick = () => { cb.checked = !cb.checked; toggle(it, cb.checked); };
    main.appendChild(name);
    main.appendChild(el("div", "eqp-row-sub", detailText(it)));
    // SRD-beskrivelse (særlige egenskaber) vist direkte under navnet — ingen hover.
    if (it.description) {
      const desc = el("div", "eqp-row-desc");
      desc.textContent = it.description;   // ren tekst — ingen HTML-fortolkning
      main.appendChild(desc);
    }

    // Materiale-/kvalitets-modifikatorer (masterwork/cold iron/sølv) som toggles.
    if ((it.modifiers || []).length) {
      const mods = el("div", "eqp-mods");
      for (const m of it.modifiers) {
        const on = checked && sel.mods.has(m.key);
        const lab = el("label", "eqp-mod" + (on ? " on" : ""));
        const mcb = el("input");
        mcb.type = "checkbox";
        mcb.checked = on;
        mcb.onchange = () => toggleMod(it, m.key, mcb.checked);
        lab.appendChild(mcb);
        lab.appendChild(el("span", null, `${m.label} +${formatCost(m.delta_cp)}`));
        mods.appendChild(lab);
      }
      main.appendChild(mods);
    }

    const right = el("div", "eqp-row-right");
    // Vis effektiv linjepris når mods er valgt, ellers basisprisen.
    const costStr = (sel && sel.mods.size) ? formatCost(lineCost(sel)) : it.cost_str;
    right.appendChild(el("div", "eqp-row-cost", costStr));
    right.appendChild(el("div", "eqp-row-weight", (it.weight || 0) + " lb"));

    row.appendChild(cb);
    row.appendChild(main);
    row.appendChild(right);
    return row;
  }

  function renderList() {
    const list = $("eqp-list");
    list.innerHTML = "";
    const visible = state.items.filter(itemVisible);
    if (!visible.length) {
      list.appendChild(el("div", "eqp-empty", "Ingen genstande matcher."));
      return;
    }
    // Gruppér under group-overskrifter (optgroup-erstatning).
    let lastGroup = null;
    for (const it of visible) {
      if (it.group !== lastGroup) {
        list.appendChild(el("div", "eqp-group", it.group || "Øvrigt"));
        lastGroup = it.group;
      }
      list.appendChild(renderRow(it));
    }
  }

  function renderWidget() {
    const { costCp, weight } = totals();
    const remaining = state.budgetCp - costCp;
    $("eqp-budget").textContent = formatCost(state.budgetCp);
    $("eqp-spent").textContent  = formatCost(costCp);
    const left = $("eqp-left");
    left.textContent = formatCost(remaining);
    left.classList.toggle("over", remaining < 0);

    const heavy = state.encLimits.heavy || 0;
    $("eqp-weight").textContent = `${weight} lb / ${heavy} lb`;
    const fill = $("eqp-encbar-fill");
    fill.style.width = heavy ? Math.min(100, (weight / heavy) * 100) + "%" : "0%";

    const lvl = encLevel(weight);
    const badge = $("eqp-enc-badge");
    badge.textContent = ENC_LABEL[lvl] || lvl;
    badge.className = "eqp-badge enc-" + lvl.toLowerCase();
    fill.className = "eqp-encbar-fill enc-" + lvl.toLowerCase();

    const count = $("eqp-count");
    if (count) count.textContent = state.selected.size;
  }

  function syncHidden() {
    const hidden = $("eqp-selected");
    if (hidden) hidden.value = JSON.stringify(getSelected());
  }

  function refresh() {
    renderList();      // 'kun råd til' afhænger af resterende budget
    renderWidget();
    syncHidden();
    if (typeof state.onChange === "function") state.onChange(getSelected());
  }

  // ── Handlinger ────────────────────────────────────────────────────────────
  function toggle(it, on) {
    if (on) {
      if (!state.selected.has(it.ref))
        state.selected.set(it.ref, { item: it, qty: 1, mods: new Set() });
    } else {
      state.selected.delete(it.ref);
    }
    refresh();
  }

  // Slå en materiale-mod til/fra; vælger automatisk varen hvis den ikke var valgt.
  function toggleMod(it, key, on) {
    let sel = state.selected.get(it.ref);
    if (!sel) { sel = { item: it, qty: 1, mods: new Set() }; state.selected.set(it.ref, sel); }
    if (on) sel.mods.add(key); else sel.mods.delete(key);
    refresh();
  }

  function getSelected() {
    return [...state.selected.values()].map(({ item, qty, mods }) => ({
      ref: item.ref, category: item.category, qty, mods: [...mods],
    }));
  }

  // ── Offentligt API ──────────────────────────────────────────────────────
  async function init(opts = {}) {
    Object.assign(state, {
      base: opts.base || "", cls: opts.cls || "", str: opts.str || 10,
      size: opts.size || "medium", race: opts.race || "",
      budgetCp: opts.budgetCp || 0, onChange: opts.onChange || null,
    });
    // Bind filter-kontroller.
    $("eqp-search").oninput = (e) => { state.search = e.target.value; renderList(); };
    $("eqp-only-prof").onchange = (e) => { state.onlyProf = e.target.checked; renderList(); };
    $("eqp-only-afford").onchange = (e) => { state.onlyAfford = e.target.checked; renderList(); };
    await reload();
    // Forudvalgte items (fx ved redigering) — liste af refs.
    if (Array.isArray(opts.selected)) {
      const byRef = new Map(state.items.map((it) => [it.ref, it]));
      for (const ref of opts.selected)
        if (byRef.has(ref)) state.selected.set(ref, { item: byRef.get(ref), qty: 1, mods: new Set() });
    }
    renderTabs();
    refresh();
  }

  async function reload() {
    try {
      await fetchCatalog();
    } catch (err) {
      $("eqp-list").innerHTML =
        `<div class="eqp-empty">Kunne ikke hente kataloget (${err.message}).</div>`;
    }
  }

  function setBudget(cp) { state.budgetCp = cp || 0; refresh(); }

  async function setContext(ctx = {}) {
    if (ctx.cls != null)  state.cls = ctx.cls;
    if (ctx.str != null)  state.str = ctx.str;
    if (ctx.size != null) state.size = ctx.size;
    if (ctx.race != null) state.race = ctx.race;
    await reload();
    renderList();
    renderWidget();
    syncHidden();
  }

  return { init, setBudget, setContext, getSelected };
})();
