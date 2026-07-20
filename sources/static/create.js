// create.js — karakter-generatorens klient-logik (race/klasse/evner/skills/feats/
// udstyr/spells). Udspaltet fra create.html's inline-script. Server-data læses fra
// den globale `GEN` (sat i en lille inline-blok i create.html: RACES/CLASSES/SKILLS/
// FEAT_PREREQS/FEAT_NAME_TO_ID/SK/SCRIPT_ROOT). Loades efter equipment_picker.js.
// Live thumbnail af det valgte portræt (vises kun lokalt før upload).
function previewPortrait(input){
  const box = document.getElementById('portrait-preview');
  const file = input.files && input.files[0];
  if(!file){ box.style.backgroundImage=''; box.classList.add('portrait-empty'); box.textContent='🧙'; return; }
  box.textContent='';
  box.classList.remove('portrait-empty');
  box.style.backgroundImage = `url(${URL.createObjectURL(file)})`;
  box.style.backgroundSize = 'cover';
  box.style.backgroundPosition = 'center';
}

const RACES = GEN.RACES;
const CLASSES = GEN.CLASSES;
const SKILLS = GEN.SKILLS;
const FEAT_PREREQS = GEN.FEAT_PREREQS;
const FEAT_NAME_TO_ID = GEN.FEAT_NAME_TO_ID;
const SK = GEN.SK;
const FEAT_ID_TO_NAME = Object.fromEntries(Object.entries(FEAT_NAME_TO_ID).map(([n,i])=>[i,n]));
const WEAPON_CHOICE_FEATS = ['weapon_focus','weapon_specialization','improved_critical'];
const SCHOOL_CHOICE_FEATS = ['spell_focus','greater_spell_focus'];
// Point-buy-priser (spejler rules.POINT_BUY_COST). Budget = 28.
const POINTBUY_COST = {8:0,9:1,10:2,11:3,12:4,13:5,14:6,15:8,16:10,17:13,18:16};

// Ability-score-metode: vis/skjul point-buy-tæller og rul-område.
function onMethodChange(){
  const m = document.querySelector('input[name="score_method"]:checked').value;
  document.getElementById('pointbuy-budget').style.display = (m==='pointbuy') ? '' : 'none';
  document.getElementById('roll-area').style.display = (m==='roll') ? '' : 'none';
  if (m!=='pointbuy') document.getElementById('score-err').textContent = '';
  onUpdate();
}

// Rul 4d6-drop-lavest seks gange (fri fordeling — brugeren skriver dem ind selv).
function rollScores(){
  const r1 = () => { const d=[0,0,0,0].map(()=>1+Math.floor(Math.random()*6)).sort((a,b)=>a-b); return d[1]+d[2]+d[3]; };
  const sets = Array.from({length:6}, r1).sort((a,b)=>b-a);
  document.getElementById('roll-result').textContent = 'Fordel selv: ' + sets.join(', ');
}

// Startguld: vis terningen pænt og rul den ind i gp-feltet (redigerbart bagefter).
function goldFormula(spec){ return spec ? spec.replace('*','×') + ' gp' : ''; }
function rollGold(){
  const cd = CLASSES[document.getElementById('cls').value.toLowerCase()];
  const m = (cd && cd.starting_gold || '').match(/(\d+)d(\d+)(?:\*(\d+))?/);
  if (!m) return;
  const [, n, die, mult] = m;
  let sum = 0;
  for (let i=0;i<+n;i++) sum += 1 + Math.floor(Math.random()*(+die));
  document.getElementById('gold_gp').value = sum * (mult ? +mult : 1);
  syncBudget();
}

// Escape til HTML-attribut (skill-beskrivelser i title= indeholder " og &).
function escAttr(s){ return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;'); }

// Terning fra streng: "2d10" → rul; "1" → tallet selv.
function rollDice(spec){
  const m = String(spec||'').match(/(\d+)d(\d+)/);
  if (!m) return parseInt(spec,10) || 0;
  let sum = 0; for (let i=0;i<+m[1];i++) sum += 1 + Math.floor(Math.random()*(+m[2]));
  return sum;
}
// Auto-rul højde/vægt/alder fra SRD-tabellen (race + klassegruppe + køn).
// Samme højde-modifier-rul bruges til både højde og vægt (SRD-reglen).
function rollBio(){
  const rd = RACES[document.getElementById('race').value.toLowerCase()];
  const cd = CLASSES[document.getElementById('cls').value.toLowerCase()];
  const bio = rd && rd.bio;
  if (!bio || !bio.adulthood) return;
  const g = document.getElementById('gender').value === 'Kvinde' ? 'female' : 'male';
  const group = (cd && cd.age_group) || 'medium';
  const age = bio.adulthood + rollDice(bio.age_dice[group]);
  const hmod = rollDice(bio.height_mod);
  const tot = bio.height_base[g] + hmod;
  const weight = bio.weight_base[g] + hmod * rollDice(bio.weight_mod);
  document.getElementById('age').value = age + ' år';
  document.getElementById('height').value = `${Math.floor(tot/12)}'${tot%12}"`;
  document.getElementById('weight').value = weight + ' lb';
}

// Vis/skjul våben-dropdown når en våben-feat krydses af/fra.
// prefix = 'feat' (alm. feats) eller 'bfeat' (fighter-bonus-feats).
function toggleFeatWeapon(fid, prefix){
  prefix = prefix || 'feat';
  const cb = document.getElementById(prefix+'_'+fid);
  const sel = document.getElementById(prefix+'wpn_'+fid);
  if(!cb || !sel) return;
  sel.style.display = cb.checked ? 'block' : 'none';
  if(!cb.checked) sel.value = '';
}

// Vis/skjul troldskole-dropdown når en skole-feat (Spell Focus m.fl.) krydses af/fra.
function toggleFeatSchool(fid, prefix){
  prefix = prefix || 'feat';
  const cb = document.getElementById(prefix+'_'+fid);
  const sel = document.getElementById(prefix+'sch_'+fid);
  if(!cb || !sel) return;
  sel.style.display = cb.checked ? 'block' : 'none';
  if(!cb.checked) sel.value = '';
}

const ABILITY_RE = /^(str|dex|con|int|wis|cha)\s+(\d+)$/i;
const BAB_RE = /(?:base attack bonus|bab)\s*\+?(\d+)/i;
const LEVEL_RE = /level\s+(\d+)/i;

function mod(score){ return Math.floor((score - 10) / 2); }

// Spejler character.feat_prereq_unmet — returnerer ikke-opfyldte klausuler.
function featUnmet(prereq, owned, finalScores, bab, canTurn){
  if(!prereq || prereq.trim().toLowerCase()==='none') return [];
  const unmet=[];
  prereq.split(',').forEach(cl=>{
    cl=cl.trim(); if(!cl) return;
    let m=cl.match(ABILITY_RE);
    if(m){ if((finalScores[m[1].toLowerCase()]||10) < parseInt(m[2])) unmet.push(cl); return; }
    m=cl.match(BAB_RE);
    if(m){ if(bab < parseInt(m[1])) unmet.push(cl); return; }
    m=cl.match(LEVEL_RE);
    if(m){ if(parseInt(m[1]) > 1) unmet.push(cl); return; }  // generatoren er altid level 1
    const low=cl.toLowerCase();
    if(low.includes('turn') && low.includes('undead')){ if(!canTurn) unmet.push(cl); return; }
    if(low.includes('wild shape')){ unmet.push(cl); return; }  // ingen klasse har wild shape ved level 1
    if(owned.has(low)) return;   // kvalificeret valg-feat ejet (fx 'spell focus (conjuration)')
    // Valg-feat med specifikt valg, ikke ejet → kræver præcis det valg.
    const mc = low.match(/^(.*?)\s*\(.+\)$/);
    if(mc){
      const base = FEAT_NAME_TO_ID[mc[1].trim()];
      if(WEAPON_CHOICE_FEATS.includes(base) || SCHOOL_CHOICE_FEATS.includes(base)){ unmet.push(cl); return; }
    }
    if(low.startsWith('proficiency')) return;
    const fid=FEAT_NAME_TO_ID[low];
    if(fid!==undefined){ if(!owned.has(fid)) unmet.push(cl); return; }
  });
  return unmet;
}

function buildSkillList(){
  const cls = document.getElementById('cls').value.toLowerCase();
  const classSkills = new Set(CLASSES[cls].class_skills);
  // klasse-skills først, så resten — alfabetisk i hver gruppe
  const sorted = [...SKILLS].sort((a,b)=>{
    const ca = classSkills.has(a.id), cb = classSkills.has(b.id);
    if (ca !== cb) return ca ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const html = sorted.map(s=>{
    const isCls = classSkills.has(s.id);
    const cap = isCls ? 4 : 2;
    return `<div class="skill-row">
      <span class="nm" title="${escAttr(s.description)}">${s.name}${isCls?'<span class="cls">klasse</span>':''}</span>
      <span class="ab">${s.ability||''}</span>
      <input type="number" name="skill_${s.id}" data-cls="${isCls?1:0}" min="0" max="${cap}" value="0" oninput="onUpdate()">
    </div>`;
  }).join('');
  document.getElementById('skill-list').innerHTML = html;
}


function onUpdate(){
  const race = document.getElementById('race').value;
  const cls = document.getElementById('cls').value;
  const rd = RACES[race.toLowerCase()];
  const cd = CLASSES[cls.toLowerCase()];

  // Ability score-preview
  let intMod = 0, ok = true;
  const finalScores = {};
  ['str','dex','con','int','wis','cha'].forEach(a=>{
    const base = parseInt(document.getElementById('score_'+a).value || '0', 10);
    const adj = rd.ability_adjust[a] || 0;
    const fin = base + adj;
    finalScores[a] = fin;
    if (a==='int') intMod = mod(fin);
    const sign = adj>0?`+${adj}`:(adj<0?`${adj}`:'');
    document.getElementById('final_'+a).textContent =
      `${fin} (${mod(fin)>=0?'+':''}${mod(fin)})${sign?' '+sign:''}`;
    if (base<3 || base>20) ok=false;
  });

  // Ability-score-metode: point-buy-validering (scores 8-18, budget 28)
  const method = document.querySelector('input[name="score_method"]:checked').value;
  let scoreErr = '';
  if (method === 'pointbuy') {
    let cost = 0, pbValid = true;
    ['str','dex','con','int','wis','cha'].forEach(a=>{
      const v = parseInt(document.getElementById('score_'+a).value||'0',10);
      const c = POINTBUY_COST[v];
      if (c === undefined) pbValid = false; else cost += c;
    });
    const pe = document.getElementById('pointbuy-budget');
    pe.innerHTML = `Brugt <b>${cost}</b> af <b>28</b> point (scores 8-18 før race)`;
    pe.classList.toggle('over', !pbValid || cost>28);
    if (!pbValid) scoreErr = 'Alle scores skal være 8-18 ved point-buy.';
    else if (cost>28) scoreErr = `For mange point brugt (${cost}/28).`;
    if (!pbValid || cost>28) ok = false;
  }
  document.getElementById('score-err').textContent = scoreErr;

  // Skills budget
  const budget = Math.max(1, cd.skill_base + intMod + (race==='Human'?1:0)) * 4;
  let spent = 0;
  document.querySelectorAll('#skill-list input').forEach(inp=>{
    const r = parseInt(inp.value||'0',10);
    const isCls = inp.dataset.cls==='1';
    spent += r * (isCls?1:2);
  });
  const bEl = document.getElementById('skill-budget');
  bEl.innerHTML = `Brugt <b>${spent}</b> af <b>${budget}</b> point (klasse-skill = 1/rank, cross-class = 2/rank)`;
  bEl.classList.toggle('over', spent>budget);
  document.getElementById('skill-err').textContent = spent>budget ? 'For mange skill points.' : '';

  // Feats — antal + prerequisite-tjek
  const need = rd.feat_count;
  const checkedEls = [...document.querySelectorAll('input[name="feats"]:checked')];
  const bonusEls = [...document.querySelectorAll('input[name="bonus_feats"]:checked')];
  const chosen = checkedEls.length;
  document.getElementById('feat-budget').innerHTML = `Vælg <b>${need}</b> feat(s) — valgt <b>${chosen}</b>`;
  document.getElementById('feat-note').textContent =
    cd.bonus_feats.length ? `Klassen giver desuden gratis: ${cd.bonus_feats.join(', ')} (tæller ikke med).` : '';
  // Owned = valgte + fighter-bonus + klassens gratis feats (feat-kæder gælder når valgt).
  const owned = new Set(checkedEls.map(e=>e.value)
    .concat(bonusEls.map(e=>e.value)).concat(cd.bonus_feats));
  // Kvalificerede labels for valgte skole-feats ('spell focus (conjuration)'), så
  // navne-baserede prereqs (Augment Summoning) matcher det valgte.
  checkedEls.concat(bonusEls).forEach(e=>{
    if (SCHOOL_CHOICE_FEATS.includes(e.value)) {
      const pre = (e.name === 'bonus_feats') ? 'bfeat' : 'feat';
      const sch = (document.getElementById(pre+'sch_'+e.value)||{}).value;
      if (sch) owned.add(`${(FEAT_ID_TO_NAME[e.value]||e.value).toLowerCase()} (${sch.toLowerCase()})`);
    }
  });
  const prereqProblems = [];
  checkedEls.forEach(e=>{
    const miss = featUnmet(FEAT_PREREQS[e.value]||'', owned, finalScores, cd.bab1, cd.turn_undead);
    if (miss.length) prereqProblems.push(`${FEAT_ID_TO_NAME[e.value]||e.value} kræver: ${miss.join(', ')}`);
    // Våben-feats: et våben skal være valgt.
    if (WEAPON_CHOICE_FEATS.includes(e.value)) {
      const sel = document.getElementById('featwpn_'+e.value);
      if (sel && !sel.value) prereqProblems.push(`${FEAT_ID_TO_NAME[e.value]||e.value}: vælg et våben`);
    }
    // Skole-feats: en troldskole skal være valgt.
    if (SCHOOL_CHOICE_FEATS.includes(e.value)) {
      const sel = document.getElementById('featsch_'+e.value);
      if (sel && !sel.value) prereqProblems.push(`${FEAT_ID_TO_NAME[e.value]||e.value}: vælg en troldskole`);
    }
  });
  let featErr = '';
  if (chosen !== need) featErr = `Skal være ${need}.`;
  else if (prereqProblems.length) featErr = '⚠ ' + prereqProblems.join(' · ');
  document.getElementById('feat-err').textContent = featErr;
  const featsOk = (chosen === need) && prereqProblems.length === 0;

  // Bonus-feats (klasser med bonus_feat_choices > 0; pulje varierer pr. klasse)
  const bfSec = document.getElementById('bonus-feat-section');
  let bfOk = true;
  if ((cd.bonus_feat_choices || 0) > 0){
    bfSec.classList.remove('hidden');
    // Vis kun feats i den valgte klasses pulje; afkryds skjulte.
    const clsLower = cls.toLowerCase();
    bfSec.querySelectorAll('.feat-row').forEach(row=>{
      const show = (row.dataset.pool||'').split(' ').includes(clsLower);
      row.style.display = show ? '' : 'none';
      if (!show){ const cb = row.querySelector('input[name="bonus_feats"]'); if (cb) cb.checked = false; }
    });
    const bfEls = [...bfSec.querySelectorAll('input[name="bonus_feats"]:checked')];
    const bfNeed = cd.bonus_feat_choices;
    const ignore = cd.bonus_feat_ignore_prereqs;   // monk får sin bonus-feat uden prereqs
    const bfProblems = [];
    bfEls.forEach(e=>{
      if (!ignore){
        const miss = featUnmet(FEAT_PREREQS[e.value]||'', owned, finalScores, cd.bab1, cd.turn_undead);
        if (miss.length) bfProblems.push(`${FEAT_ID_TO_NAME[e.value]||e.value} kræver: ${miss.join(', ')}`);
      }
      if (WEAPON_CHOICE_FEATS.includes(e.value)) {
        const sel = document.getElementById('bfeatwpn_'+e.value);
        if (sel && !sel.value) bfProblems.push(`${FEAT_ID_TO_NAME[e.value]||e.value}: vælg et våben`);
      }
      if (SCHOOL_CHOICE_FEATS.includes(e.value)) {
        const sel = document.getElementById('bfeatsch_'+e.value);
        if (sel && !sel.value) bfProblems.push(`${FEAT_ID_TO_NAME[e.value]||e.value}: vælg en troldskole`);
      }
    });
    document.getElementById('bonus-feat-budget').innerHTML =
      `Vælg <b>${bfNeed}</b> bonus-feat(s) — valgt <b>${bfEls.length}</b>`;
    let bfErr = '';
    if (bfEls.length !== bfNeed) bfErr = `Skal være ${bfNeed}.`;
    else if (bfProblems.length) bfErr = '⚠ ' + bfProblems.join(' · ');
    document.getElementById('bonus-feat-err').textContent = bfErr;
    bfOk = (bfEls.length === bfNeed) && bfProblems.length === 0;
  } else {
    bfSec.classList.add('hidden');
  }

  // Domæner (kun cleric)
  const domSec = document.getElementById('domain-section');
  let domOk = true;
  if (cd.needs_domains){
    domSec.classList.remove('hidden');
    const dc = document.querySelectorAll('input[name="domains"]:checked').length;
    domOk = dc===2;
    document.getElementById('domain-err').textContent = domOk ? '' : 'Vælg præcis 2 domæner.';
  } else {
    domSec.classList.add('hidden');
  }

  // Kendte spells (spontane castere + wizard) — vises kun for castere i SK.
  const skOk = renderSpellsKnown(cls, intMod);

  // Sprog (automatiske + bonussprog = Int-mod)
  const langOk = renderLanguages(race, cls, intMod);

  // Favored enemy-felt (kun ranger)
  document.getElementById('favored-wrap').classList.toggle('hidden', cls!=='Ranger');
  document.getElementById('combat-style-wrap').classList.toggle('hidden', cls!=='Ranger');

  // Dyreledsager (kun klasser med companion ved level 1 = druide)
  document.getElementById('companion-section').classList.toggle('hidden', !cd.has_companion);

  // Startguld-formel for den valgte klasse
  document.getElementById('gold-formula').textContent =
    cd.starting_gold ? '(' + goldFormula(cd.starting_gold) + ')' : '';

  // Submit-spærring
  const valid = ok && spent<=budget && featsOk && bfOk && domOk && skOk && langOk;
  document.getElementById('submit-btn').disabled = !valid;
}

// Spell-vælger ved oprettelse. Konfiguration pr. klasse kommer fra SK (server):
//   cantrips/first = {mode, list, n/base}. mode 'auto' = alle gives (read-only,
//   wizard-cantrips), 'pick' = vælg fast n (sorcerer/bard), 'int' = vælg base +
//   Int-mod (wizard 1.-levels). Listerne bygges kun når klassen skifter (bevarer
//   afkrydsninger); antal + validering genberegnes hver gang (Int kan ændres).
function renderSpellsKnown(cls, intMod){
  const sec = document.getElementById('spells-known-section');
  const cfg = SK[cls.toLowerCase()];
  if (!cfg){
    sec.classList.add('hidden');
    document.getElementById('sk-field-0').value = '';
    document.getElementById('sk-field-1').value = '';
    return true;
  }
  sec.classList.remove('hidden');
  let ok = true;
  const errs = [];

  function group(kind, gcfg, listId, labelId, wrapId, fieldId){
    const wrap = document.getElementById(wrapId);
    if (!gcfg){
      wrap.classList.add('hidden');
      document.getElementById(fieldId).value = '';
      return;
    }
    wrap.classList.remove('hidden');
    const list = document.getElementById(listId);
    const auto = gcfg.mode === 'auto';
    const need = auto ? gcfg.list.length
               : (gcfg.mode === 'int' ? gcfg.base + Math.max(0, intMod) : gcfg.n);
    // Byg listen kun når klassen skifter (så afkrydsninger bevares ved re-render).
    const sig = cls;
    if (list.dataset.sig !== sig){
      if (auto){
        list.innerHTML = `<div class="sk-auto">${gcfg.list.map(o=>o.name).join(', ')}</div>`;
      } else {
        list.innerHTML = `<div class="sk-list">` + gcfg.list.map(o=>
          `<label class="sk-item"><input type="checkbox" value="${o.id}" onchange="onUpdate()"> ${o.name}` +
          (o.school ? ` <span class="sk-school">${o.school}</span>` : '') + `</label>`).join('') + `</div>`;
      }
      list.dataset.sig = sig;
    }
    const chosen = auto ? gcfg.list.map(o=>o.id)
                        : [...list.querySelectorAll('input:checked')].map(i=>i.value);
    document.getElementById(fieldId).value = JSON.stringify(chosen);
    const lvlName = kind === 'cantrips' ? 'cantrips (0-level)' : '1.-levels spells';
    const lbl = document.getElementById(labelId);
    if (auto){
      lbl.textContent = `Alle ${need} ${lvlName} gives automatisk til din spellbog.`;
    } else {
      lbl.innerHTML = `Vælg <b>${need}</b> ${lvlName} — valgt <b>${chosen.length}</b>`;
      if (chosen.length !== need){ ok = false; errs.push(`Vælg ${need} ${lvlName}.`); }
    }
  }

  group('cantrips', cfg.cantrips, 'sk-cantrip-list', 'sk-cantrip-label', 'sk-cantrip-wrap', 'sk-field-0');
  group('first', cfg.first, 'sk-first-list', 'sk-first-label', 'sk-first-wrap', 'sk-field-1');
  document.getElementById('spells-known-err').textContent = errs.join(' · ');
  return ok;
}

// Byg sprog-blokken: automatiske som chips + N bonussprog-vælgere (N = Int-mod).
// Vælgerne genbygges kun når antal/pulje ændres (bevarer brugerens valg).
function renderLanguages(race, cls, intMod){
  const rd = RACES[race.toLowerCase()], cd = CLASSES[cls.toLowerCase()];
  const auto = [...rd.languages_auto];
  cd.languages_auto.forEach(l=>{ if(!auto.includes(l)) auto.push(l); });
  let pool = [...rd.languages_bonus];
  cd.languages_bonus.forEach(l=>{ if(!pool.includes(l)) pool.push(l); });
  pool = pool.filter(l=>!auto.includes(l)).sort();
  const count = Math.max(0, intMod);

  document.getElementById('lang-auto').innerHTML =
    '<span style="color:var(--muted);font-size:.8rem">Automatiske: </span>' +
    (auto.length ? auto.map(l=>`<span class="lang-chip">${l}</span>`).join('') : '—');

  const wrap = document.getElementById('lang-bonus');
  const sig = count + '|' + pool.join(',');
  if (wrap.dataset.sig !== sig){
    const prev = [...wrap.querySelectorAll('select')].map(s=>s.value);
    let html = '';
    if (count === 0){
      html = '<span style="color:var(--muted);font-size:.8rem">Ingen bonussprog (Int-mod ≤ 0).</span>';
    }
    for (let i=0;i<count;i++){
      const keep = (prev[i] && pool.includes(prev[i])) ? prev[i] : '';
      html += `<select name="languages" class="lang-select" onchange="onUpdate()">` +
        `<option value="">— vælg bonussprog —</option>` +
        pool.map(l=>`<option value="${l}"${l===keep?' selected':''}>${l}</option>`).join('') +
        `</select>`;
    }
    wrap.innerHTML = html;
    wrap.dataset.sig = sig;
  }

  const vals = [...wrap.querySelectorAll('select')].map(s=>s.value).filter(Boolean);
  const dup = new Set(vals).size !== vals.length;
  let err = '';
  if (vals.length !== count) err = `Vælg ${count} bonussprog.`;
  else if (dup) err = 'Samme sprog valgt flere gange.';
  document.getElementById('lang-err').textContent = err;
  return vals.length === count && !dup;
}

// Udrustningsbutikken: generator-formularen ejer kontekst (klasse/styrke/størrelse/
// race) + budget; butikken regner selv proficiency/anbefalet/vægt server-side og
// markerer uvant grej med ⚠. Vi fodrer den bare med formularens aktuelle værdier.
function pickerCtx(){
  const rd = RACES[document.getElementById('race').value.toLowerCase()] || {};
  // Endelig STR = basis + race-justering (bæreevnen afhænger af den endelige score).
  const baseStr = parseInt(document.getElementById('score_str').value || '10', 10) || 10;
  const adj = (rd.ability_adjust && rd.ability_adjust.str) || 0;
  return {
    cls:  document.getElementById('cls').value.toLowerCase(),
    race: document.getElementById('race').value.toLowerCase(),
    str:  baseStr + adj,
    size: rd.size || 'medium',
  };
}
// Samlet budget i kobber (cp): pp×1000 + gp×100 + sp×10 + cp.
function budgetCp(){
  const v = (id) => parseInt(document.getElementById(id).value || '0', 10) || 0;
  return v('gold_pp')*1000 + v('gold_gp')*100 + v('gold_sp')*10 + v('gold_cp');
}
function syncBudget(){ if (window.EquipmentPicker) EquipmentPicker.setBudget(budgetCp()); }
function syncPickerContext(){ if (window.EquipmentPicker) EquipmentPicker.setContext(pickerCtx()); }

// Genbyg skill-listen + opdatér butikken når klasse/race/styrke skifter.
document.getElementById('cls').addEventListener('change', ()=>{ buildSkillList(); onUpdate(); rollBio(); syncPickerContext(); });
document.getElementById('race').addEventListener('change', syncPickerContext);
document.getElementById('score_str').addEventListener('input', syncPickerContext);

buildSkillList();
onUpdate();
rollBio();
EquipmentPicker.init({ base: GEN.SCRIPT_ROOT, ...pickerCtx(), budgetCp: budgetCp() });
