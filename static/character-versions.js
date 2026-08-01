// ── Noter og versionshistorik (Noter-fanen) ───────────────────────────────
// Noterne renderes med en lille markdown-delmængde; versionerne er snapshots
// af hele arket, som kan gendannes eller navngives ("efter session 12").
// escHtml kommer fra character-core.js.

// ── Markdown renderer ──────────────────────────────────────────────────────
function renderMd(raw) {
  if (!raw || !raw.trim())
    return '<em style="color:var(--muted)">Ingen noter endnu — tryk ✎ Rediger</em>';
  const out = [];
  let inList = false;
  for (const line of raw.split('\n')) {
    let l = escHtml(line)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>');
    if (/^#{1,4} /.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      const depth = line.match(/^(#{1,4})/)[1].length;
      out.push(`<${depth <= 2 ? 'h3' : 'h4'}>${l.replace(/^#{1,4} /, '')}</${depth <= 2 ? 'h3' : 'h4'}>`);
    } else if (/^- /.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${l.slice(2)}</li>`);
    } else if (/^-{3,}$/.test(line.trim())) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr>');
    } else if (line.trim() === '') {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<br>');
    } else {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(l + '<br>');
    }
  }
  if (inList) out.push('</ul>');
  return out.join('');
}


// ── Notes ─────────────────────────────────────────────────────────────────
let _notesRaw = D.notesRaw;
document.getElementById('notes-view').innerHTML = renderMd(_notesRaw);

function toggleNotesEdit() {
  document.getElementById('notes-textarea').value = _notesRaw;
  document.getElementById('notes-view').style.display = 'none';
  document.getElementById('notes-edit-area').style.display = 'block';
  document.getElementById('notes-edit-btn').style.display = 'none';
}
function cancelNotesEdit() {
  document.getElementById('notes-view').style.display = 'block';
  document.getElementById('notes-edit-area').style.display = 'none';
  document.getElementById('notes-edit-btn').style.display = '';
}
async function saveNotes() {
  const text = document.getElementById('notes-textarea').value;
  const r = await fetch(BASE + '/api/notes', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({char: CHAR, notes: text}),
  });
  if (r.ok) {
    _notesRaw = text;
    document.getElementById('notes-view').innerHTML = renderMd(_notesRaw);
    cancelNotesEdit();
  }
}

// ── Versioner ─────────────────────────────────────────────────────────────
// Alle tre kald ender med at genindlæse siden: en gendannelse ændrer hele
// arket, og en navngivning ændrer rækkefølgen/mærkaterne i listen.

function _versionPost(url, body, hvad) {
  return fetch(BASE + url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(Object.assign({char: CHAR}, body))
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) window.location.reload();
    else alert(`Kunne ikke ${hvad}: ` + (data.error || "ukendt fejl"));
  })
  .catch(() => alert(`Kunne ikke ${hvad} (netværksfejl).`));
}

function restoreSnapshot(file, label) {
  if (!confirm(`Gendan tilstanden fra ${label}?\n\nDen nuværende tilstand gemmes som et snapshot først, så du kan fortryde.`)) return;
  _versionPost("/api/restore", {snapshot: file}, "gendanne");
}

function saveNamedVersion() {
  const name = prompt("Navn på versionen — fx “Session 12” eller “Før dragen”:\n\n" +
                      "Navngivne versioner slettes aldrig automatisk.");
  if (name === null) return;                 // annulleret
  if (!name.trim()) { alert("Versionen skal have et navn."); return; }
  _versionPost("/api/version/save", {name: name}, "gemme versionen");
}

function renameVersion(file, current) {
  const name = prompt("Navn på versionen (tomt felt fjerner navnet igen):", current || "");
  if (name === null) return;                 // annulleret
  if (name === current) return;              // uændret
  _versionPost("/api/version/rename", {snapshot: file, name: name}, "omdøbe versionen");
}
