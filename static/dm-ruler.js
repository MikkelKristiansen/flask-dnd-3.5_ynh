// dm-ruler.js — måle-lineal til DM-brættet (klient-kun, ingen server/persistering).
//
// En 📏-knap pr. bræt-figur slår en global lineal-tilstand til. I tilstanden slår
// token-flyt fra (via body.ruler-on-CSS), og et tryk-og-træk på brættet måler
// afstanden mellem to celler efter 3.5-reglen (diagonaler 5-10-5-10 fod). Global
// tilstand + body-klasse gør at den overlever DOM-swap af kamp-brættet (som sker ved
// hver tracker-handling) — man skal ikke slå den til igen efter hvert HP-klik.
//
// Genbruger brættets egne kroge: window.dmSnapCell (klient-px → {col,row}) og samme
// celle→%-geometri som token-layoutet (board.dataset.cell/gx/gy/naturalW).
(function () {
  var ON = false, start = null, curBoard = null;

  function setOn(v) {
    ON = v;
    document.body.classList.toggle("ruler-on", v);
    if (!v) {                                   // ryd alle overlays når linealen slås fra
      start = null; curBoard = null;
      document.querySelectorAll(".ruler-svg, .ruler-label").forEach(function (e) { e.remove(); });
    }
  }

  // Celle-center som % af brættets naturlige mål (samme matematik som token-layoutet).
  function cellCenterPct(board, col, row) {
    var img = board.querySelector(".board-map");
    var Wn = +board.dataset.naturalW || (img ? img.naturalWidth : 0);
    var Hn = img ? img.naturalHeight : 0;
    var cell = +board.dataset.cell || 0, gx = +board.dataset.gx || 0, gy = +board.dataset.gy || 0;
    if (!Wn || !Hn || cell <= 0) return null;
    return { x: (gx + (col + 0.5) * cell) / Wn * 100, y: (gy + (row + 0.5) * cell) / Hn * 100 };
  }

  // 3.5 RAW: diagonaler koster skiftevis 5-10-5-10 fod.
  //   felter = max(dx,dy) + floor(min(dx,dy)/2), ×5 fod.
  function feet35(c1, c2) {
    var dx = Math.abs(c2.col - c1.col), dy = Math.abs(c2.row - c1.row);
    return (Math.max(dx, dy) + Math.floor(Math.min(dx, dy) / 2)) * 5;
  }

  var SVGNS = "http://www.w3.org/2000/svg";
  function overlay(board) {
    var ov = board.querySelector(".ruler-svg");
    if (!ov) {
      ov = document.createElementNS(SVGNS, "svg");
      ov.setAttribute("class", "ruler-svg");
      ov.setAttribute("viewBox", "0 0 100 100");
      ov.setAttribute("preserveAspectRatio", "none");
      var line = document.createElementNS(SVGNS, "line");
      line.setAttribute("class", "ruler-line");
      line.setAttribute("vector-effect", "non-scaling-stroke");   // ens stregtykkelse trods stræk
      ov.appendChild(line);
      board.appendChild(ov);
    }
    var lbl = board.querySelector(".ruler-label");
    if (!lbl) { lbl = document.createElement("div"); lbl.className = "ruler-label"; board.appendChild(lbl); }
    return { line: ov.querySelector(".ruler-line"), lbl: lbl };
  }

  function draw(board, c1, c2) {
    var p1 = cellCenterPct(board, c1.col, c1.row), p2 = cellCenterPct(board, c2.col, c2.row);
    if (!p1 || !p2) return;
    var o = overlay(board);
    o.line.setAttribute("x1", p1.x); o.line.setAttribute("y1", p1.y);
    o.line.setAttribute("x2", p2.x); o.line.setAttribute("y2", p2.y);
    o.lbl.textContent = feet35(c1, c2) + " ft";
    o.lbl.style.left = p2.x + "%"; o.lbl.style.top = p2.y + "%";
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".board-ruler-toggle")) return;
    e.preventDefault();
    setOn(!ON);
  });

  // Tryk på brættet (tokens har pointer-events:none i lineal-tilstand → target er brættet).
  document.addEventListener("pointerdown", function (e) {
    if (!ON) return;
    var board = e.target.closest(".board");
    if (!board || e.target.closest(".board-ruler-toggle")) return;
    var c = window.dmSnapCell(board, e.clientX, e.clientY);
    if (!c) return;
    curBoard = board; start = c;
    e.preventDefault();
    draw(board, c, c);
  });
  document.addEventListener("pointermove", function (e) {
    if (!ON || !start || !curBoard) return;
    var c = window.dmSnapCell(curBoard, e.clientX, e.clientY);
    if (c) draw(curBoard, start, c);
  });
  document.addEventListener("pointerup", function () { start = null; });
})();
