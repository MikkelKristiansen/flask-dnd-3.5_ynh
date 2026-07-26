/* dm-combat-board.js — træk combatant-tokens under kamp.
 *
 * Ansvar: gør combatant-tokens (`.tok[data-cid]`) på det aktive kamp-bræt
 * trækbare; ved slip snappes til nærmeste grid-celle (delt window.dmSnapCell fra
 * _board.html) og den nye position POST'es til /move. REN UI — serveren ejer
 * positionen; efter et flyt kaldes onMoved() (play refetcher brættet, så tur/HP-
 * overlay følger med). Adskilt fra opstillings-editoren (dm-board-editor.js):
 * den redigerer en forfattet fil, denne muterer live kamp-tilstand.
 *
 * Brug: DmCombatBoard.attach({ root, slug, onMoved }). Kaldes igen efter hver
 * bræt-swap (nye DOM-tokens = nye handlers).
 */
window.DmCombatBoard = (function () {
  "use strict";

  function clamp(f) { return f < 0 ? 0 : f > 1 ? 1 : f; }

  function attach(opts) {
    var fig = document.querySelector('.board-fig[data-combat="1"]');
    if (!fig) return;
    var board = fig.querySelector(".board");
    if (!board) return;
    board.querySelectorAll(".tok[data-cid]").forEach(function (tok) {
      tok.addEventListener("pointerdown", function (ev) {
        ev.preventDefault();
        tok.setPointerCapture(ev.pointerId);
        var rect = board.getBoundingClientRect();
        var moved = false;
        function move(e) {
          moved = moved || Math.abs(e.clientX - ev.clientX) > 4 ||
            Math.abs(e.clientY - ev.clientY) > 4;
          tok.style.left = clamp((e.clientX - rect.left) / rect.width) * 100 + "%";
          tok.style.top = clamp((e.clientY - rect.top) / rect.height) * 100 + "%";
        }
        function up(e) {
          tok.releasePointerCapture(ev.pointerId);
          tok.removeEventListener("pointermove", move);
          tok.removeEventListener("pointerup", up);
          if (!moved) return;                         // rent klik → ingen flytning
          var cell = window.dmSnapCell(board, e.clientX, e.clientY);
          if (!cell) { if (opts.onMoved) opts.onMoved(); return; }   // intet grid → gendan
          var fd = new FormData();
          fd.set("cid", tok.dataset.cid);
          fd.set("col", cell.col);
          fd.set("row", cell.row);
          fetch(opts.root + "/dm/api/encounter/" + encodeURIComponent(opts.slug) + "/move",
                { method: "POST", body: fd })
            .then(function () { if (opts.onMoved) opts.onMoved(); })
            .catch(function () { if (opts.onMoved) opts.onMoved(); });
        }
        tok.addEventListener("pointermove", move);
        tok.addEventListener("pointerup", up);
      });
    });
  }

  return { attach: attach };
})();
