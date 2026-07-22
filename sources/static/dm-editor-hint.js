// dm-editor-hint.js — @type[id]-autocomplete for eventyr-editoren (Fase D).
//
// Kobler sig på CodeMirror-instansen (window.DmEditor.editor.cm) fra dm-editor.js.
// DB-typer (monster/faelde/dør) hentes fra /dm/api/entity-ids (cachet pr. type);
// dokument-lokale typer (npc/brev/kort/gaade) completes fra selve buffer-teksten.
// Uden CM (textarea-fallback) gør filen ingenting.
(function () {
  "use strict";
  var ed = window.DmEditor && window.DmEditor.editor;
  var cm = ed && ed.cm;
  if (!cm || !window.CodeMirror || !cm.showHint) return;

  var ta = document.querySelector("textarea[name=source]");
  var API = (ta && ta.dataset.entityApi) || "";

  // Spejler dm_parser.slugify (æ→ae, ø→oe, å→aa, resten → '-') så doc-lokale id'er
  // matcher det parseren udleder af fx '## Brev: Titel'.
  function slugify(s) {
    return s.trim().toLowerCase()
      .replace(/æ/g, "ae").replace(/ø/g, "oe").replace(/å/g, "aa")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  var CACHE = {};
  var DB_TYPE = { monster: "monster", faelde: "faelde", "dør": "door", door: "door",
                  genstand: "genstand", specifik: "specifik" };
  function fetchIds(type, cb) {
    var key = DB_TYPE[type];
    if (!key || !API) { cb([]); return; }
    if (CACHE[key]) { cb(CACHE[key]); return; }
    fetch(API + "?type=" + key)
      .then(function (r) { return r.json(); })
      .then(function (d) { CACHE[key] = d; cb(d); })
      .catch(function () { cb([]); });
  }

  var DOC_LABEL = { npc: "NPC", brev: "Brev", kort: "Kort", gaade: "Gåde", "gåde": "Gåde" };
  function docLocalIds(type) {
    var label = DOC_LABEL[type];
    if (!label) return [];
    var re = new RegExp("^##\\s+" + label + ":\\s*(.+)$", "i");
    var out = [], seen = {}, lines = cm.getValue().split("\n");
    for (var i = 0; i < lines.length; i++) {
      var m = re.exec(lines[i].trim());
      if (m) {
        var title = m[1].trim(), id = slugify(title);
        if (id && !seen[id]) { seen[id] = 1; out.push({ id: id, name: title }); }
      }
    }
    return out;
  }

  function entityHint(cmInst, callback) {
    var cur = cmInst.getCursor();
    var pre = cmInst.getLine(cur.line).slice(0, cur.ch);
    var m = /@([A-Za-zÆØÅæøå]+)\[([^\]]*)$/.exec(pre);
    if (!m) return;
    var type = m[1].toLowerCase(), prefix = m[2].toLowerCase();
    var from = window.CodeMirror.Pos(cur.line, cur.ch - m[2].length);
    var close = cmInst.getLine(cur.line).charAt(cur.ch) === "]" ? "" : "]";
    function done(items) {
      var list = items
        .filter(function (it) { return it.id.toLowerCase().indexOf(prefix) !== -1; })
        .slice(0, 50)
        .map(function (it) {
          return { text: it.id + close,
                   displayText: it.name ? it.id + " — " + it.name : it.id };
        });
      callback({ list: list, from: from, to: cur });
    }
    if (DOC_LABEL[type]) done(docLocalIds(type));
    else fetchIds(type, done);
  }
  entityHint.async = true;

  // Åbn forslagslisten mens der skrives inde i @type[ … .
  cm.on("inputRead", function (cmInst) {
    var cur = cmInst.getCursor();
    var pre = cmInst.getLine(cur.line).slice(0, cur.ch);
    if (/@[A-Za-zÆØÅæøå]+\[[^\]]*$/.test(pre)) {
      cmInst.showHint({ hint: entityHint, completeSingle: false });
    }
  });
})();
