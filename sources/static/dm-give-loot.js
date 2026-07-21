// dm-give-loot.js — delt give-loot-submit for DM'ens inspektør-fragmenter
// (_magic.html / _magic_item.html). Loades af BÅDE play-viewet og opslagsværket, så
// "🎁 Giv til spiller" virker begge steder. Delegeret submit: base_ref/bonus ligger i
// formularens dataset (ikke felter), give-loot-URL'en i data-give-url (fuld sti m/
// evt. script_root), så filen ikke afhænger af en side-specifik ROOT-variabel.
(function () {
  document.addEventListener('submit', function (e) {
    var form = e.target.closest('.give-loot');
    if (!form) return;
    e.preventDefault();
    var res = form.querySelector('.give-result');
    var url = form.dataset.giveUrl || '/dm/api/give-loot';
    var params = new URLSearchParams(new FormData(form));   // char + evt. abilities
    params.set('base_ref', form.dataset.base);
    params.set('bonus', form.dataset.bonus);
    fetch(url, { method: 'POST', body: params })
      .then(function (r) { return r.text(); })
      .then(function (t) { if (res) { res.hidden = false; res.textContent = t; } })
      .catch(function () { if (res) { res.hidden = false; res.textContent = 'Kunne ikke give loot.'; } });
  });
})();
