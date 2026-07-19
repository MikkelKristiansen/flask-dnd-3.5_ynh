// dm-editor.js — brugervenlighed for eventyr-tekst-editoren.
//
// Fase A (denne fil): sikkerhed & ergonomi — Ctrl/Cmd-S gemmer, advarsel ved
// ugemte ændringer, og localStorage-kladde der overlever et browser-crash.
//
// Al tekst-adgang går gennem en lille ADAPTER (initEditor). Fase B (CodeMirror)
// erstatter KUN initEditor med en CM-adapter — resten af logikken er editor-
// agnostisk og røres ikke. Fase C's værktøjslinje bruger adapter.insert().
(function () {
  "use strict";
  var ta = document.querySelector("textarea[name=source]");
  if (!ta) return;
  var ref = ta.dataset.ref || "adv";
  var justSaved = ta.dataset.saved === "1";
  var KEY = "dnd-adv-draft:" + ref;

  // --- Fase B: syntaks-highlighting via CodeMirror 5 SimpleMode ---------------
  // Vores egen mode oven på CM: farver scener, read-aloud, @entiteter, billeder.
  // sol=true anchorer overskrift/blockquote til linjestart (så '>' midt i prosa
  // ikke fejl-farves). Er CM/simple ikke loadet, springes mode-def over.
  function defineAdventureMode() {
    if (!window.CodeMirror || !CodeMirror.defineSimpleMode ||
        CodeMirror.modes["dnd-adventure"]) return;
    CodeMirror.defineSimpleMode("dnd-adventure", {
      start: [
        { regex: /#{1,6}\s.*/, token: "header", sol: true },      // scener/overskrifter
        { regex: /\s*>.*/, token: "quote", sol: true },           // read-aloud/handouts
        { regex: /!\[[^\]]*\]\([^)]*\)/, token: "image" },        // billeder
        { regex: /@[A-Za-zÆØÅæøå]+\[[^\]]*\]/, token: "entity" }, // @type[id]
        { regex: /\*\*[^*]+\*\*/, token: "strong" },
        { regex: /\*[^*]+\*/, token: "em" },
        { regex: /./, token: null }                               // fremdrift
      ]
    });
  }

  // --- Editor-adapter: CodeMirror hvis tilgængelig, ellers ren textarea -------
  function initEditor(el) {
    defineAdventureMode();
    if (window.CodeMirror && CodeMirror.modes["dnd-adventure"]) {
      var cm = CodeMirror.fromTextArea(el, {
        mode: "dnd-adventure", lineNumbers: true, lineWrapping: true, tabSize: 2
      });
      cm.setSize(null, "70vh");
      cm.focus();
      return {
        getValue: function () { return cm.getValue(); },
        setValue: function (v) { cm.setValue(v); },
        onChange: function (fn) { cm.on("change", fn); },
        save: function () { cm.save(); },              // CM → underliggende textarea
        insert: function (text) { cm.replaceSelection(text); cm.focus(); },
        cm: cm
      };
    }
    return {                                            // fallback (Fase A-adfærd)
      getValue: function () { return el.value; },
      setValue: function (v) { el.value = v; },
      onChange: function (fn) { el.addEventListener("input", fn); },
      save: function () {},
      insert: function (text) {
        var s = el.selectionStart, e = el.selectionEnd;
        el.value = el.value.slice(0, s) + text + el.value.slice(e);
        el.selectionStart = el.selectionEnd = s + text.length;
        el.focus();
        fireChange();
      }
    };
  }

  var ed = initEditor(ta);
  var serverSource = ed.getValue();
  var dirty = false;

  // Eksponér adapteren så Fase B/C kan bygge videre uden at duplikere logik.
  window.DmEditor = { editor: ed, ref: ref };

  // --- Fase C: indsæt-værktøjslinje + billed-vælger ---------------------------
  // Knapper indsætter fast-tekst-skeletter ved markøren; billed-dropdownen
  // indsætter en media-reference. Alt går gennem adapter.insert (virker i både
  // CodeMirror og textarea-fallback).
  var SNIPPETS = {
    scene: "\n# Scene-titel\n\n",
    readaloud: "> **Læs højt:** \n",
    statblock: "\n## Statblok: Navn\n```\nhp: \nac: \nsaves: \nattacks: \n```\n",
    monster: "@monster[id]",
    npc: "@npc[id]"
  };
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-insert]");
    if (!b) return;
    e.preventDefault();
    if (SNIPPETS[b.dataset.insert]) ed.insert(SNIPPETS[b.dataset.insert]);
  });
  var imgSel = document.getElementById("img-insert");
  if (imgSel) imgSel.addEventListener("change", function () {
    if (imgSel.value) { ed.insert("![](media/" + imgSel.value + ")"); imgSel.selectedIndex = 0; }
  });

  function fireChange() { markDirty(); }
  function markDirty() {
    dirty = ed.getValue() !== serverSource;
    try { localStorage.setItem(KEY, ed.getValue()); } catch (e) {}
  }
  ed.onChange(markDirty);

  // Efter et vellykket gem ER server-teksten = kladden → ryd den.
  if (justSaved) { try { localStorage.removeItem(KEY); } catch (e) {} }

  // Kladde-gendannelse: en gemt kladde der afviger fra serveren = ikke-gemt arbejde.
  try {
    var draft = localStorage.getItem(KEY);
    if (draft != null && draft !== serverSource && !justSaved) showRestore(draft);
  } catch (e) {}

  function showRestore(draft) {
    var bar = document.getElementById("restore");
    if (!bar) return;
    bar.hidden = false;
    bar.querySelector(".r-yes").addEventListener("click", function () {
      ed.setValue(draft); markDirty(); bar.hidden = true; ta.focus();
    });
    bar.querySelector(".r-no").addEventListener("click", function () {
      try { localStorage.removeItem(KEY); } catch (e) {}
      bar.hidden = true;
    });
  }

  // Ctrl/Cmd-S gemmer.
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      submit();
    }
  });

  function submit() {
    var f = ta.form;
    if (f.requestSubmit) f.requestSubmit(); else f.submit();
  }

  // Ved gem: sync editor → textarea (Fase B), og behold kladden til efter reload
  // (den ryddes når siden loader igen med ?saved=1).
  ta.form.addEventListener("submit", function () {
    ed.save();
    dirty = false;
    try { localStorage.setItem(KEY, ed.getValue()); } catch (e) {}
  });

  // Advar ved ugemte ændringer (undgås ved eget gem, hvor dirty allerede er nulstillet).
  window.addEventListener("beforeunload", function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });
})();
