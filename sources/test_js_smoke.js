// test_js_smoke.js — afhængighedsfri smoke-test af character-*.js.
//
// Kør: node test_js_smoke.js   (fra sources/)
//
// JS'en er browser-globale klassiske scripts (ingen build/moduler). Her konkateneres
// de i load-orden og køres ÉN gang i en vm-kontekst — samme delte globale scope som
// browserens <script>-tags. Det fanger det `node --check` IKKE fanger: redeklaration
// (const x to steder), forkert load-orden, og globals der er udefinerede VED LOAD.
// Mock-`DND` giver serverdata; ukendte felter → [] (virker som både tom array OG objekt).
// Ingen npm — kun Nodes indbyggede fs/vm (som pytest-venv'en: dev-only, shippes ikke).
// (Fuld adfærdstest m/ jsdom = fremtid, se refaktor-plan-memoen.)
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const STATIC = path.join(__dirname, "static");

// Load-orden som i character.html.
const FILES = [
  "equipment_picker.js",
  "character-core.js",
  "character-combat.js",
  "character-spells.js",
  "character-tooltips.js",
  "character-prep-modal.js",
  "character-companion.js",
  "character-progression.js",
  "character-inventory.js",
];

// Funktioner der SKAL være globalt definerede efter load (kaldes fra inline-onclick).
const REQUIRED = [
  "showSpellTooltip", "hideSpellTooltip", "showSlaTooltip", "renderBreakdownTooltip",
  "showSkillBreakdown", "showAttackBreakdown", "showSkillTooltip", "truncDesc",
  "castSpell", "castKnownSpell", "openSummonPicker",
  "openPrepModal", "renderPrepModal", "savePrepared", "closePrepIfOutside",
];

// --- Mock server-data (window.DND) ---
const DND_BASE = {
  scriptRoot: "", name: "", cls: "", size: "", castType: "prepared",
  cureDirection: "cure", notesRaw: "",
  hpMax: 0, hpCurrent: 0, compHpMax: 0, compHpCurrent: 0, currentWeight: 0,
  baseSpeed: 30, goldCp: 0,
};
const DND = new Proxy(DND_BASE, {
  get(t, p) { return p in t ? t[p] : []; },   // ukendt felt → [] (tom array/objekt-agtig)
});

// --- Minimale browser-globals ---
function elStub() {
  return new Proxy({
    style: {}, dataset: {}, innerHTML: "", textContent: "", value: "", hidden: false,
    checked: false, children: [], classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    getBoundingClientRect: () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }),
  }, { get(t, p) { return p in t ? t[p] : () => elStub(); } });
}
const documentStub = new Proxy({
  getElementById: () => elStub(), querySelector: () => null, querySelectorAll: () => [],
  createElement: () => elStub(), addEventListener() {}, body: elStub(),
}, { get(t, p) { return p in t ? t[p] : () => elStub(); } });

const sandbox = {
  document: documentStub, console,
  fetch: () => Promise.resolve({ json: () => ({}), text: () => "" }),
  location: { reload() {}, href: "", hash: "", search: "" }, alert() {}, confirm() { return true; }, prompt() { return ""; },
  setTimeout, clearTimeout, Math, JSON, Object, Array, Date, parseInt, parseFloat, isNaN,
  Set, Map, Promise, URLSearchParams, FormData, RegExp, String, Number, Boolean, Error,
};
sandbox.window = sandbox;
sandbox.window.DND = DND;
sandbox.navigator = { userAgent: "node" };
vm.createContext(sandbox);

// Konkatenér (i load-orden) + et assertions-epilog i SAMME scope.
let code = FILES.map(f => fs.readFileSync(path.join(STATIC, f), "utf8")).join("\n;\n");
code += "\n;(function(){\n" +
  "  var need = " + JSON.stringify(REQUIRED) + ";\n" +
  "  for (var i=0;i<need.length;i++){ if (typeof window[need[i]] !== 'function') throw new Error('funktion mangler: '+need[i]); }\n" +
  "  if (window.truncDesc('kort', 100) !== 'kort') throw new Error('truncDesc: kort tekst ændret');\n" +
  "  if (!window.truncDesc(new Array(300).join('x'), 50).endsWith(' …')) throw new Error('truncDesc: lang tekst ikke afkortet');\n" +
  "  window.__SMOKE_OK__ = true;\n" +
  "})();\n";

try {
  vm.runInContext(code, sandbox, { filename: "concat" });
} catch (e) {
  console.error("SMOKE FEJL ved load/assert:", e.message);
  process.exit(1);
}
if (!sandbox.window.__SMOKE_OK__) { console.error("SMOKE: epilog kørte ikke"); process.exit(1); }
console.log("JS smoke OK — " + FILES.length + " filer loadet uden fejl, " + REQUIRED.length + " nøglefunktioner defineret.");
