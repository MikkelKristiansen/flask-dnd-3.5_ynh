// dm-play.js — DM play-viewets interaktive lag: lightbox (handouts/statblokke),
// statblok-fetch, kamp-bræt-sync efter tracker-handlinger, give-loot-submit,
// kort-fuldbredde-toggle. Udspaltet fra play.html's inline-script (rent JS —
// konfig læses fra #dm-cfg-DOM'en: data-root/data-adv). Loades efter
// dm-combat-board.js / dm-rolls.js (samme position i body).
(function () {
  var lb = document.getElementById('lightbox');
  var body = lb.querySelector('.lb-body');
  var title = lb.querySelector('.lb-title');
  var cfg = document.getElementById('dm-cfg');
  var ROOT = cfg.dataset.root, ADV = cfg.dataset.adv;

  function openDoc(key) {                       // handout (renderet skjult i siden)
    var src = document.getElementById('doc-' + key.replace(':', '-'));
    if (!src) return;
    title.textContent = src.dataset.title || '';
    body.innerHTML = src.innerHTML;
    lb.hidden = false;
  }
  function openStat(ref) {                       // monster/npc → hent statblok
    var parts = ref.split('/');                  // "type/id"
    title.textContent = 'Statblok';
    body.innerHTML = '<p class="lb-loading">Henter …</p>';
    lb.hidden = false;
    fetch(ROOT + '/dm/api/statblock/' + encodeURIComponent(ADV) + '/'
          + encodeURIComponent(parts[0]) + '/' + encodeURIComponent(parts[1]))
      .then(function (r) { return r.text(); })
      .then(function (html) { body.innerHTML = html; })
      .catch(function () { body.innerHTML = '<p>Kunne ikke hente statblok.</p>'; });
  }
  function close() { lb.hidden = true; body.innerHTML = ''; }

  // Dør-markør → statblok + kamp-HP-tracker (session-scoped: col/row identificerer
  // instansen). Uden aktiv kamp giver endpointet bare den statiske dør.
  function openDoor(el) {
    var ref = el.dataset.mref, col = el.dataset.col || 0, row = el.dataset.row || 0;
    title.textContent = '🚪 Dør';
    body.innerHTML = '<p class="lb-loading">Henter …</p>';
    lb.hidden = false;
    fetch(ROOT + '/dm/api/encounter/' + encodeURIComponent(cfg.dataset.slug)
          + '/door/' + encodeURIComponent(ref) + '?col=' + col + '&row=' + row)
      .then(function (r) { return r.text(); })
      .then(function (html) { body.innerHTML = html; })
      .catch(function () { body.innerHTML = '<p>Kunne ikke hente dør.</p>'; });
  }

  // Justér en dørs kamp-HP. Kaldes fra inline onclick i det fetch'ede fragment, så
  // funktionen eksponeres globalt. Opdaterer HP-tallet live (server = sandhedskilde).
  window.adjDoorHp = function (ref, col, row, delta, reset) {
    var params = new URLSearchParams({ ref: ref, col: col, row: row });
    if (reset) params.set('reset', '1'); else params.set('delta', delta);
    fetch(ROOT + '/dm/api/encounter/' + encodeURIComponent(cfg.dataset.slug) + '/door_hp',
          { method: 'POST', body: params })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) return;
        var el = document.getElementById('door-hp-' + ref + '-' + col + '-' + row);
        if (!el) return;
        var done = d.current === 0;
        el.textContent = done ? 'smadret' : (d.current + '/' + d.max);
        el.classList.toggle('expired', done);
      });
  };

  var MARKER_LABEL = { trap: '🪤 Fælde', door: '🚪 Dør', treasure: '💰 Skat', note: '📌 Note' };
  function openMarker(el) {                       // markør på brættet → note-detalje
    // En fælde-markør bundet til en fælde i kataloget → åbn dens statblok
    // (samme opslag som @faelde i prosaen). Ubundet → fald tilbage på noten.
    if (el.dataset.mkind === 'trap' && el.dataset.mref) {
      openStat('faelde/' + el.dataset.mref);
      return;
    }
    // En dør-markør bundet til en dør i kataloget → åbn dens statblok. Under kamp
    // beriges den med en HP-tracker (col/row identificerer dør-instansen). Ubundet →
    // fald tilbage på noten.
    if (el.dataset.mkind === 'door' && el.dataset.mref) {
      openDoor(el);
      return;
    }
    title.textContent = MARKER_LABEL[el.dataset.mkind] || '📌 Markør';
    var p = document.createElement('p');
    var note = el.dataset.mnote || '';
    if (note) { p.textContent = note; } else { p.className = 'note'; p.textContent = 'Ingen note.'; }
    body.innerHTML = '';
    body.appendChild(p);
    lb.hidden = false;
  }

  document.addEventListener('click', function (e) {
    var doc = e.target.closest('.ent-link');
    if (doc) { e.preventDefault(); openDoc(doc.dataset.doc); return; }
    var stat = e.target.closest('.ent-stat');
    if (stat) { e.preventDefault(); openStat(stat.dataset.stat); return; }
    var marker = e.target.closest('.tok[data-marker]');
    if (marker) { e.preventDefault(); openMarker(marker); return; }
    if (e.target === lb || e.target.closest('.lb-close')) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !lb.hidden) close();
  });

  // Giv-loot-formularen bor i det fetch'ede magisk-item-fragment → delegeret submit.
  // FormData tager char + alle afkrydsede abilities (name=abilities) med; base_ref/
  // bonus ligger i dataset (ikke form-felter), så de sættes eksplicit.
  document.addEventListener('submit', function (e) {
    var form = e.target.closest('.give-loot');
    if (!form) return;
    e.preventDefault();
    var res = form.querySelector('.give-result');
    var params = new URLSearchParams(new FormData(form));
    params.set('base_ref', form.dataset.base);
    params.set('bonus', form.dataset.bonus);
    fetch(ROOT + '/dm/api/give-loot', { method: 'POST', body: params })
      .then(function (r) { return r.text(); })
      .then(function (t) { res.hidden = false; res.textContent = t; })
      .catch(function () { res.hidden = false; res.textContent = 'Kunne ikke give loot.'; });
  });

  // Kryds en ability af/til i byggeren → genopbyg @magisk-ident'en og re-fetch
  // fragmentet, så navn + pris opdateres live (server = sandhedskilde).
  document.addEventListener('change', function (e) {
    if (!e.target.matches('.give-loot input[name="abilities"]')) return;
    var form = e.target.closest('.give-loot');
    var baseId = (form.dataset.base || '').split('/')[1];
    var checked = Array.prototype.map.call(
      form.querySelectorAll('input[name="abilities"]:checked'),
      function (c) { return c.value; });
    var ident = baseId + '+' + form.dataset.bonus + (checked.length ? ',' + checked.join(',') : '');
    openStat('magisk/' + ident);
  });

  // Kamp-brættet holdes synkront med trackeren: efter enhver kamp-handling
  // (start/tur/HP/afslut) refetches bræt-fragmentet og #board-slot swappes, så
  // positioner, HP og aktiv-tur-ring følger med. Server = sandhedskilde.
  var SLUG = cfg.dataset.slug;
  function attachCombat() {                            // (gen)tilknyt træk-flyt til kamp-tokens
    if (window.DmCombatBoard)
      DmCombatBoard.attach({ root: ROOT, slug: SLUG, onMoved: refreshBoard });
  }
  function refreshBoard() {
    var slot = document.getElementById('board-slot');
    if (!slot) return;
    fetch(ROOT + '/dm/api/encounter/' + encodeURIComponent(SLUG) + '/board')
      .then(function (r) { return r.status === 200 ? r.text() : null; })
      .then(function (html) {
        if (html === null) return;
        slot.innerHTML = html;
        if (window.dmLayoutAll) window.dmLayoutAll();     // swappet <script> kører ikke selv
        attachCombat();                                   // nye DOM-tokens = nye handlers
      })
      .catch(function () {});
  }
  attachCombat();                                      // kamp allerede i gang ved sideload

  // Encounter-tracker: alle handlinger er <form class="enc-f"> → POST via fetch,
  // og #tracker erstattes med det re-renderede fragment (server = sandhedskilde).
  var tracker = document.getElementById('tracker');
  document.addEventListener('submit', function (e) {
    var f = e.target.closest('.enc-f');
    if (!f) return;
    e.preventDefault();
    var btn = e.submitter;
    if (btn && btn.dataset.confirm && !confirm(btn.dataset.confirm)) return;
    var fd = new FormData(f);
    if (btn && btn.dataset.sign) {                 // HP: skade (−) / helbred (＋)
      var amt = parseInt(fd.get('amount') || '0', 10) || 0;
      fd.set('delta', btn.dataset.sign === '-' ? -amt : amt);
    }
    fetch(f.action, { method: 'POST', body: fd })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        tracker.innerHTML = html;
        // Kamp-tilstand: udvid konsollen når en kamp er aktiv (.enc-top findes kun da).
        document.querySelector('.layout').classList.toggle(
          'combat', !!tracker.querySelector('.enc-top'));
        refreshBoard();
      })
      .catch(function () {});
  });

  // Kort-bredde-toggle: skift kamp-kortet mellem to kolonner og fuld bredde.
  // Klassen sidder på .layout (uden for #tracker), så valget overlever tracker-
  // swaps; det huskes pr. session i localStorage. Knap-teksten viser handlingen.
  (function () {
    var layout = document.querySelector('.layout');
    var btn = document.getElementById('map-toggle');
    if (!layout || !btn) return;
    var KEY = 'dm-mapfull-' + cfg.dataset.slug;
    function sync() {
      var full = layout.classList.contains('mapfull');
      btn.textContent = full ? '⧉ Kort: to kolonner' : '⛶ Kort: fuld bredde';
    }
    if (localStorage.getItem(KEY) === '1') layout.classList.add('mapfull');
    sync();
    btn.addEventListener('click', function () {
      var full = layout.classList.toggle('mapfull');
      localStorage.setItem(KEY, full ? '1' : '0');
      sync();
    });
  })();
})();
