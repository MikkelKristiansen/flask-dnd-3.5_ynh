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

  // --- Editor-adapter (textarea-udgave; Fase B leverer en CodeMirror-udgave) ---
  function initEditor(el) {
    return {
      getValue: function () { return el.value; },
      setValue: function (v) { el.value = v; },
      onChange: function (fn) { el.addEventListener("input", fn); },
      save: function () {},                 // textarea er allerede live; intet at synce
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
