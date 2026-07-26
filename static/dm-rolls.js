// dm-rolls.js — gør statblok-tal i kamp-konsollen til ét-kliks-terningkast.
//
// Ét ansvar: fang klik på .roll-knapper (til-hit / skade / crit / save), kald
// den DELTE terning-rute /api/roll (samme som spillersiden bruger — den ved intet
// om spillere vs. monstre, den ruller bare et udtryk) og skriv resultatet i
// #roll-log. Klik-håndteringen er event-delegation, fordi #tracker (og dermed
// knapperne) re-renderes ved hver kamp-handling — loggen selv bor UDEN FOR
// #tracker, så den overlever de swaps.
(function () {
  "use strict";
  var cfg = document.getElementById("dm-cfg");
  if (!cfg) return;
  var ROOT = cfg.dataset.root || "";
  var log = document.getElementById("roll-log");

  // Crit i 3.5 = gang HELE skade-udtrykket (terning-antal OG modifier) med
  // multiplikatoren. "1d8+1" ×3 → "3d8+3". Regex matcher dice.py's parser.
  function critExpr(expr, mult) {
    var m = /^(\d*)d(\d+)([+-]\d+)?$/.exec(expr.replace(/\s+/g, "").toLowerCase());
    if (!m) return expr;                          // uparsbart → rul som normalt
    var count = (parseInt(m[1], 10) || 1) * mult;
    var mod = (parseInt(m[3], 10) || 0) * mult;
    return count + "d" + m[2] + (mod ? (mod > 0 ? "+" : "") + mod : "");
  }

  function addRow(label, data) {
    if (!log) return;
    var empty = log.querySelector(".rl-empty");
    if (empty) empty.remove();
    var rolls = (data.rolls && data.rolls.length) ? data.rolls.join("+") : "";
    var mod = data.modifier ? (data.modifier > 0 ? "+" : "") + data.modifier : "";
    var detail = (rolls ? "[" + rolls + mod + "]" : "") + (data.floored ? " (min)" : "");

    var row = document.createElement("div");
    row.className = "rl-row";
    var l = document.createElement("span"); l.className = "rl-lbl"; l.textContent = label;
    var t = document.createElement("span"); t.className = "rl-tot"; t.textContent = data.total;
    var d = document.createElement("span"); d.className = "rl-det"; d.textContent = detail;
    row.appendChild(l); row.appendChild(t); row.appendChild(d);
    log.insertBefore(row, log.firstChild);
    while (log.children.length > 8) log.removeChild(log.lastChild);   // behold seneste 8
  }

  function clearLog() {
    if (!log) return;
    log.innerHTML = '<div class="rl-empty">Klik en bonus, skade eller save i '
      + "statblokkene for at rulle.</div>";
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest("#roll-clear")) { clearLog(); return; }
    var btn = e.target.closest(".roll");
    if (!btn || !btn.dataset.roll) return;
    e.preventDefault();
    var expr = btn.dataset.roll;
    if (btn.dataset.crit) expr = critExpr(expr, parseInt(btn.dataset.crit, 10) || 2);
    var url = ROOT + "/api/roll/" + encodeURIComponent(expr);
    if (btn.dataset.min) url += "?min=" + encodeURIComponent(btn.dataset.min);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) { if (!data.error) addRow(btn.dataset.label || expr, data); })
      .catch(function () {});
  });
})();
