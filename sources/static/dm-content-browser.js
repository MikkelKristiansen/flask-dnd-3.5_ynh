// dm-content-browser.js — opslagsværk: browse katalog (monstre/fælder/døre).
//
// Virker to steder: (1) et toggle-panel i eventyr-editoren (indsætter @ref ved
// markøren), og (2) den selvstændige /dm/opslag-side (ren browsing, ingen editor).
// Konfig læses fra #browse-panel (data-entity-api). Editor-afhængigt (toggle, ＋
// indsæt) er valgfrit: er der ingen toggle, står panelet åbent; er der ingen editor
// (window.DmEditor), vises ingen ＋-knap.
//
// Genbruger /dm/api/entity-ids (id+navn+cr) + /dm/api/catalog-statblock (adventure-fri
// statblok) + window.DmEditor.editor.insert.
(function () {
  "use strict";
  var panel = document.getElementById("browse-panel");
  if (!panel) return;
  var toggle = document.getElementById("browse-toggle");
  var HAS_EDITOR = !!(window.DmEditor && window.DmEditor.editor);

  var API = panel.dataset.entityApi || "";
  var STATBLOCK = API.replace(/\/entity-ids$/, "/catalog-statblock");
  // Åbnet fra en session? → giv ?from=<slug> med til statblok-fetch, så magiske
  // genstande får en give-loot-knap (kamp-kontekst). Tom = party-løst opslag.
  var FROM = panel.dataset.from || "";

  var TABS = [
    { key: "monster",  label: "Monstre", ins: "@monster[" },
    { key: "faelde",   label: "Fælder",  ins: "@faelde[" },
    { key: "door",     label: "Døre",    ins: "@dør[" },
    { key: "genstand", label: "Magiske genstande", ins: "@genstand[" }
  ];
  var CACHE = {};
  var active = "monster";

  var tabBar = panel.querySelector(".br-tabs");
  var search = panel.querySelector(".br-search");
  var listEl = panel.querySelector(".br-list");

  if (toggle) {
    toggle.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) load(active);
    });
  }

  TABS.forEach(function (t) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "br-tab" + (t.key === active ? " active" : "");
    b.textContent = t.label;
    b.dataset.key = t.key;
    b.addEventListener("click", function () {
      active = t.key;
      tabBar.querySelectorAll(".br-tab").forEach(function (x) {
        x.classList.toggle("active", x.dataset.key === active);
      });
      load(active);
    });
    tabBar.appendChild(b);
  });

  search.addEventListener("input", render);

  function tabOf(key) { return TABS.filter(function (t) { return t.key === key; })[0]; }

  function load(key) {
    if (CACHE[key]) { render(); return; }
    listEl.innerHTML = '<div class="br-empty">Henter …</div>';
    fetch(API + "?type=" + key)
      .then(function (r) { return r.json(); })
      .then(function (d) { CACHE[key] = d; render(); })
      .catch(function () { listEl.innerHTML = '<div class="br-empty">Kunne ikke hente.</div>'; });
  }

  function render() {
    var items = CACHE[active] || [];
    var q = search.value.trim().toLowerCase();
    if (q) items = items.filter(function (it) {
      return it.name.toLowerCase().indexOf(q) !== -1 ||
             String(it.cr == null ? "" : it.cr).indexOf(q) !== -1;
    });
    listEl.innerHTML = "";
    if (!items.length) { listEl.innerHTML = '<div class="br-empty">Ingen match.</div>'; return; }
    var tab = tabOf(active);
    items.slice(0, 300).forEach(function (it) {
      var row = document.createElement("div");
      row.className = "br-row";
      var name = document.createElement("button");
      name.type = "button"; name.className = "br-name"; name.title = "Vis statblok";
      name.textContent = it.name;
      name.addEventListener("click", function () { preview(row, active, it.id); });
      row.appendChild(name);
      if (it.cr != null && it.cr !== "") {
        var cr = document.createElement("span");
        cr.className = "br-cr"; cr.textContent = "CR " + it.cr;
        row.appendChild(cr);
      }
      if (HAS_EDITOR) {
        var ins = document.createElement("button");
        ins.type = "button"; ins.className = "br-ins"; ins.title = "Indsæt reference"; ins.textContent = "＋";
        ins.addEventListener("click", function () {
          window.DmEditor.editor.insert(tab.ins + it.id + "]");
        });
        row.appendChild(ins);
      }
      listEl.appendChild(row);
    });
  }

  function preview(row, type, id) {
    var next = row.nextSibling;
    if (next && next.className === "br-preview") { next.parentNode.removeChild(next); return; }  // toggle
    var box = document.createElement("div");
    box.className = "br-preview";
    box.innerHTML = "Henter …";
    row.parentNode.insertBefore(box, row.nextSibling);
    fetch(STATBLOCK + "/" + type + "/" + encodeURIComponent(id)
          + (FROM ? "?from=" + encodeURIComponent(FROM) : ""))
      .then(function (r) { return r.text(); })
      .then(function (html) { box.innerHTML = html; })
      .catch(function () { box.innerHTML = "Kunne ikke hente statblok."; });
  }

  if (!toggle) { panel.hidden = false; load(active); }   // standalone: altid åben
})();
