/* dm-board-editor.js — visuel opstillings-editor til DM-brættet.
 *
 * Ansvar: lade DM'en trække PC'er / monstre / markører fra en palette ind på
 * kortet, flytte dem (snap til grid-celle), redigere den enkelte token (label,
 * skjult, note) og gemme hele opstillingen. REN UI — al 3.5-regel/navne-data
 * kommer færdig fra serveren (palette + resolvede tokens); farve/ikon-tabellerne
 * sendes med, så nye tokens ser præcis ud som server-renderet (én sandhedskilde).
 *
 * Token-modellen er den samme liste `dm_board.board_view` sender ud, beriget med
 * `ref`/`note`. Ved gem POST'es kun de rå felter til /board/<adv>/<map>/tokens;
 * serveren saniterer. Positioner regnes altid som celle-koordinater (col/row) —
 * pixels findes kun forbigående under træk.
 *
 * Brug: DmBoardEditor.init({ model, palette, style, saveUrl, portraitBase }).
 * Genbruger bræt-render-matematikken i _board.html via window.dmRelayout.
 */
window.DmBoardEditor = (function () {
  "use strict";

  var model, palette, style, saveUrl, portraitBase;
  var board, panel, statusEl, detailEl, editing = false, selected = -1;

  function init(cfg) {
    model = (cfg.model || []).map(function (t) { return normalise(t); });
    palette = cfg.palette || { pcs: [], creatures: [], markers: [] };
    style = cfg.style || { colors: [], icons: {} };
    saveUrl = cfg.saveUrl;
    portraitBase = cfg.portraitBase;

    board = document.querySelector(".board");
    panel = document.getElementById("ed-panel");
    statusEl = document.getElementById("ed-status");
    detailEl = document.getElementById("ed-detail");
    if (!board || !panel) return;

    buildPalette();
    document.getElementById("ed-toggle").addEventListener("click", toggleEdit);
    document.getElementById("ed-save").addEventListener("click", save);
  }

  // Behold kun de felter vi ejer (drop server-visnings-props; de genberegnes).
  function normalise(t) {
    return {
      kind: t.kind, ref: t.ref || "",
      col: +t.col || 0, row: +t.row || 0,
      label: t.label || "", note: t.note || "", hidden: !!t.hidden,
    };
  }

  // ── Navne- & farve-opslag (matcher dm_board.board_view) ──────────────────
  var nameMap = null;
  function nameFor(ref) {
    if (!nameMap) {
      nameMap = {};
      palette.pcs.concat(palette.creatures).forEach(function (c) { nameMap[c.ref] = c.name; });
    }
    return nameMap[ref] || ref;
  }

  // Stabil farve pr. monster/npc-ref i første-optrædens-rækkefølge (som serveren).
  function colorMap() {
    var map = {}, i = 0;
    model.forEach(function (t) {
      if ((t.kind === "monster" || t.kind === "npc") && !(t.ref in map)) {
        map[t.ref] = style.colors[i % style.colors.length];
        i += 1;
      }
    });
    return map;
  }

  // ── Palette ──────────────────────────────────────────────────────────────
  function buildPalette() {
    var host = document.getElementById("ed-palette");
    host.innerHTML = "";
    addGroup(host, "Spillere", palette.pcs);
    addGroup(host, "Monstre & NPC'er", palette.creatures);
    addGroup(host, "Markører", palette.markers);
  }

  function addGroup(host, title, items) {
    if (!items.length) return;
    var h = document.createElement("div");
    h.className = "ed-grouphead";
    h.textContent = title;
    host.appendChild(h);
    items.forEach(function (it) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ed-chip ed-chip-" + it.kind;
      chip.textContent = (style.icons[it.kind] ? style.icons[it.kind] + " " : "") + it.name;
      chip.addEventListener("click", function () { addToken(it.kind, it.ref || ""); });
      host.appendChild(chip);
    });
  }

  // ── Tilføj / omdøb / fjern ────────────────────────────────────────────────
  function addToken(kind, ref) {
    if (grid().cell <= 0) { flash("Kalibrér grid først"); return; }
    var c = centerCell();
    model.push(normalise({ kind: kind, ref: ref, col: c.col, row: c.row }));
    relabel(kind, ref);
    paint();
    select(model.length - 1);
  }

  // A/B/C-instans-labels: ≥2 tokens af samme væsen får bogstaver, ellers intet.
  function relabel(kind, ref) {
    if (kind !== "monster" && kind !== "npc") return;
    var idx = model.map(function (t, i) { return { t: t, i: i }; })
      .filter(function (o) { return o.t.kind === kind && o.t.ref === ref; });
    idx.forEach(function (o, n) {
      o.t.label = idx.length >= 2 ? String.fromCharCode(65 + n) : "";
    });
  }

  function removeToken(i) {
    var t = model[i];
    model.splice(i, 1);
    relabel(t.kind, t.ref);
    select(-1);
    paint();
  }

  // ── Render (spejler _board.html's token-markup) ───────────────────────────
  function paint() {
    var colors = colorMap();
    board.querySelectorAll(".tok").forEach(function (el) { el.remove(); });
    model.forEach(function (t, i) {
      board.appendChild(makeTok(t, i, colors));
    });
    if (window.dmRelayout) window.dmRelayout();
  }

  function makeTok(t, i, colors) {
    var el = document.createElement("div");
    el.className = "tok tok-" + t.kind + (t.hidden ? " tok-hidden" : "") +
      (i === selected ? " tok-sel" : "");
    el.dataset.col = t.col;
    el.dataset.row = t.row;
    el.title = titleFor(t);
    if (t.kind === "pc") {
      var lbl = document.createElement("span");
      lbl.className = "tok-lbl";
      lbl.textContent = (t.label || t.ref.slice(0, 2)).toUpperCase();
      var img = document.createElement("img");
      img.className = "tok-por";
      img.src = portraitBase + encodeURIComponent(t.ref);
      img.alt = "";
      img.onerror = function () { img.remove(); };
      el.appendChild(lbl);
      el.appendChild(img);
    } else if (t.kind === "monster" || t.kind === "npc") {
      var disc = document.createElement("span");
      disc.className = "tok-disc";
      disc.style.background = colors[t.ref] || style.colors[0];
      disc.textContent = (t.label || nameFor(t.ref).slice(0, 1)).toUpperCase();
      el.appendChild(disc);
    } else {
      var mark = document.createElement("span");
      mark.className = "tok-mark";
      mark.textContent = style.icons[t.kind] || "📌";
      el.appendChild(mark);
    }
    if (editing) attachDrag(el, i);
    return el;
  }

  function titleFor(t) {
    if (t.kind === "pc") return t.label || nameFor(t.ref);
    if (t.kind === "monster" || t.kind === "npc")
      return (nameFor(t.ref) + " " + t.label).trim();
    return t.note || t.label || t.kind;
  }

  // ── Træk-og-flyt med snap ─────────────────────────────────────────────────
  function attachDrag(el, i) {
    el.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      var rect = board.getBoundingClientRect();
      var moved = false;
      el.setPointerCapture(ev.pointerId);
      function move(e) {
        moved = moved || Math.abs(e.clientX - ev.clientX) > 4 || Math.abs(e.clientY - ev.clientY) > 4;
        var fx = clamp((e.clientX - rect.left) / rect.width);
        var fy = clamp((e.clientY - rect.top) / rect.height);
        el.style.left = fx * 100 + "%";
        el.style.top = fy * 100 + "%";
      }
      function up(e) {
        el.releasePointerCapture(ev.pointerId);
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        if (moved) { snap(i, e); } else { select(i); }
      }
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
    });
  }

  function snap(i, e) {
    // Delt snap (fra _board.html): snapper OG clamper til kortets gyldige celler,
    // så en token ikke kan trækkes uden for det synlige område.
    var cell = window.dmSnapCell(board, e.clientX, e.clientY);
    if (!cell) { paint(); return; }
    model[i].col = cell.col;
    model[i].row = cell.row;
    paint();
  }

  // ── Detalje-editor for den valgte token ──────────────────────────────────
  function select(i) {
    selected = i;
    board.querySelectorAll(".tok").forEach(function (el, n) {
      el.classList.toggle("tok-sel", n === i);
    });
    renderDetail();
  }

  function renderDetail() {
    detailEl.innerHTML = "";
    if (selected < 0 || selected >= model.length) {
      detailEl.textContent = "Klik en token for at redigere den.";
      return;
    }
    var t = model[selected];
    var head = document.createElement("div");
    head.className = "ed-detailhead";
    head.textContent = titleFor(t) || t.kind;
    detailEl.appendChild(head);

    if (t.kind === "monster" || t.kind === "npc" || t.kind === "pc") {
      detailEl.appendChild(field("Label", t.label, function (v) {
        t.label = v; paint(); renderDetail();
      }));
    }
    if (t.kind === "trap" || t.kind === "door" || t.kind === "treasure" || t.kind === "note") {
      detailEl.appendChild(field("Note", t.note, function (v) {
        t.note = v; select(selected);
      }));
    }
    detailEl.appendChild(checkbox("Skjult for spillere", t.hidden, function (v) {
      t.hidden = v; paint(); select(selected);
    }));
    var del = document.createElement("button");
    del.type = "button";
    del.className = "ed-del";
    del.textContent = "🗑 Fjern token";
    del.addEventListener("click", function () { removeToken(selected); });
    detailEl.appendChild(del);
  }

  function field(label, value, onChange) {
    var wrap = document.createElement("label");
    wrap.className = "ed-field";
    wrap.textContent = label + " ";
    var inp = document.createElement("input");
    inp.type = "text";
    inp.value = value || "";
    inp.addEventListener("input", function () { onChange(inp.value); });
    wrap.appendChild(inp);
    return wrap;
  }

  function checkbox(label, checked, onChange) {
    var wrap = document.createElement("label");
    wrap.className = "ed-field ed-check";
    var inp = document.createElement("input");
    inp.type = "checkbox";
    inp.checked = !!checked;
    inp.addEventListener("change", function () { onChange(inp.checked); });
    wrap.appendChild(inp);
    wrap.appendChild(document.createTextNode(" " + label));
    return wrap;
  }

  // ── Tilstand & gem ────────────────────────────────────────────────────────
  function toggleEdit() {
    editing = !editing;
    panel.hidden = !editing;
    board.classList.toggle("editing", editing);
    document.getElementById("ed-toggle").textContent =
      editing ? "✓ Færdig med at redigere" : "✏️ Rediger opstilling";
    select(-1);
    paint();               // gentegn med/uden træk-håndtag
  }

  function save() {
    var payload = model.map(function (t) {
      var o = { kind: t.kind, col: t.col, row: t.row };
      if (t.ref) o.ref = t.ref;
      if (t.label) o.label = t.label;
      if (t.note) o.note = t.note;
      if (t.hidden) o.hidden = true;
      return o;
    });
    fetch(saveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (r) { flash(r.ok ? "Opstilling gemt ✓" : "Fejl ved gem"); })
      .catch(function () { flash("Fejl ved gem"); });
  }

  // ── Småting ────────────────────────────────────────────────────────────────
  function grid() {
    return { cell: +board.dataset.cell || 0, x: +board.dataset.gx || 0, y: +board.dataset.gy || 0 };
  }

  function centerCell() {
    var g = grid(), Wn = +board.dataset.naturalW || 0;
    var Hn = (board.querySelector(".board-map") || {}).naturalHeight || 0;
    if (g.cell <= 0 || !Wn) return { col: 0, row: 0 };
    return {
      col: Math.max(0, Math.round((Wn / 2 - g.x) / g.cell - 0.5)),
      row: Math.max(0, Math.round((Hn / 2 - g.y) / g.cell - 0.5)),
    };
  }

  function clamp(f) { return f < 0 ? 0 : f > 1 ? 1 : f; }

  function flash(msg) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    setTimeout(function () { statusEl.textContent = ""; }, 2000);
  }

  return { init: init };
})();
