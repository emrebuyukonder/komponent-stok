'use strict';

const S = {
  comps: [], cats: [], view: 'stock', cat: '__all', q: '',
  imp: { order: null, bom: null },
};
const KIND_LABEL = { siparis: 'Sipariş', proje: 'Proje', manuel: 'Elle', duzeltme: 'Düzeltme' };

// ------------------------------------------------------------ yardımcılar
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const lower = (s) => String(s ?? '').toLocaleLowerCase('tr');
const byId = (id) => S.comps.find((c) => c.id === id);

async function api(path, { method = 'GET', body } = {}) {
  const r = await fetch(path, {
    method, headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

let toastTimer;
function toast(msg, err = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'show' + (err ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ''), err ? 5000 : 2800);
}
const fail = (e) => toast(e.message || String(e), true);

function label(c) {
  if (!c) return '?';
  return c.mpn || [c.value, c.package].filter(Boolean).join(' ') || c.supplier_pn || (c.description || '').slice(0, 50) || '#' + c.id;
}
function fmtDate(s) {
  const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)/.exec(s || '');
  return m ? `${m[3]}.${m[2]}.${m[1]} ${m[4]}` : s;
}
const opt = (v, text, cur) => `<option value="${esc(v)}"${String(v) === String(cur) ? ' selected' : ''}>${esc(text)}</option>`;

function downloadCSV(name, rows) {
  const csv = '\ufeff' + rows.map((r) => r.map((v) => {
    const s = String(v ?? '');
    return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }).join(';')).join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function loadComps() {
  const d = await api('/api/components');
  S.comps = d.components;
  S.cats = d.categories;
}

// ------------------------------------------------------------ gezinme
function setView(v) {
  S.view = v;
  try { localStorage.setItem('stok.view', v); } catch (e) { /* yoksay */ }
  render();
}
function render() {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.view === S.view));
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + S.view));
  if (S.view === 'stock') renderStock();
  else if (S.view === 'order' || S.view === 'bom') renderImport(S.view);
  else if (S.view === 'history') renderHistory();
}

// ------------------------------------------------------------ stok görünümü
const isLow = (c) => c.min_qty > 0 && c.quantity <= c.min_qty && c.quantity > 0;

function renderStock() {
  const counts = {};
  S.comps.forEach((c) => (counts[c.category] = (counts[c.category] || 0) + 1));
  const low = S.comps.filter(isLow).length;
  const out = S.comps.filter((c) => c.quantity === 0).length;
  const btn = (k, text, n, cls = '') =>
    `<button data-cat="${esc(k)}" class="${S.cat === k ? 'active' : ''}"><span>${esc(text)}</span><span class="count ${cls}">${n}</span></button>`;
  $('#cat-list').innerHTML =
    btn('__all', 'Tüm parçalar', S.comps.length) +
    btn('__low', 'Azalanlar', low, low ? 'warnc' : '') +
    btn('__out', 'Tükenenler', out, out ? 'badc' : '') +
    '<hr>' +
    S.cats.filter((c) => counts[c]).map((c) => btn(c, c, counts[c])).join('');
  renderStockTable();
}

function renderStockTable() {
  const q = lower(S.q).trim();
  let list = S.comps.filter((c) => {
    if (S.cat === '__low' && !isLow(c)) return false;
    if (S.cat === '__out' && c.quantity !== 0) return false;
    if (!S.cat.startsWith('__') && c.category !== S.cat) return false;
    if (!q) return true;
    const hay = lower([c.mpn, c.supplier_pn, c.manufacturer, c.description, c.value, c.package, c.location, c.notes, c.category].join(' '));
    return q.split(/\s+/).every((w) => hay.includes(w));
  });
  const catOrder = Object.fromEntries(S.cats.map((c, i) => [c, i]));
  list.sort((a, b) => (catOrder[a.category] ?? 99) - (catOrder[b.category] ?? 99) || label(a).localeCompare(label(b), 'tr', { numeric: true }));
  $('#stock-count').textContent = `${list.length} parça · ${list.reduce((s, c) => s + c.quantity, 0).toLocaleString('tr')} adet`;

  if (!S.comps.length) {
    $('#stock-table').innerHTML = `<tbody><tr><td class="empty">Henüz parça yok. <b>Sipariş girişi</b> sekmesinden bir sipariş listesi yükleyin ya da <b>+ Yeni parça</b> ile elle ekleyin.</td></tr></tbody>`;
    return;
  }
  if (!list.length) {
    $('#stock-table').innerHTML = `<tbody><tr><td class="empty">Eşleşen parça yok.</td></tr></tbody>`;
    return;
  }
  const grouped = S.cat.startsWith('__');
  let lastCat = null;
  const rows = list.map((c) => {
    let head = '';
    if (grouped && c.category !== lastCat) {
      lastCat = c.category;
      head = `<tr class="cat-row"><td colspan="6">${esc(c.category)}</td></tr>`;
    }
    const sub = [c.mpn && c.value ? c.value : '', c.manufacturer, c.supplier_pn].filter(Boolean).join(' · ');
    const qcls = c.quantity === 0 ? 'out' : isLow(c) ? 'low' : '';
    return head + `<tr data-id="${c.id}">
      <td class="part"><b>${esc(label(c))}</b>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</td>
      <td class="desc">${esc(c.description)}</td>
      <td>${esc(c.package)}</td>
      <td>${esc(c.location)}</td>
      <td><div class="qty-cell">
        <button class="icon-btn" data-adj="-1" title="Stoktan düş">−</button>
        <span class="qty ${qcls}" title="${c.min_qty ? 'Min. ' + c.min_qty : ''}">${c.quantity}</span>
        <button class="icon-btn" data-adj="1" title="Stoğa ekle">+</button></div></td>
      <td class="actions"><button class="btn sm ghost" data-edit>Düzenle</button></td>
    </tr>`;
  }).join('');
  $('#stock-table').innerHTML = `<thead><tr><th>Parça</th><th>Açıklama</th><th>Kılıf</th><th>Konum</th><th class="num">Adet</th><th></th></tr></thead><tbody>${rows}</tbody>`;
}

// ------------------------------------------------------------ modallar
const modal = () => $('#modal');
function openModal(html) {
  modal().innerHTML = html;
  modal().showModal();
  const f = modal().querySelector('[autofocus]');
  if (f) { f.focus(); if (f.select) f.select(); }
}

function catOptions(cur) {
  const cats = S.cats.includes(cur) || !cur ? S.cats : [...S.cats, cur];
  return cats.map((c) => opt(c, c, cur)).join('');
}

function openEdit(c) {
  const isNew = !c;
  c = c || { category: S.cat.startsWith('__') ? '' : S.cat, quantity: 0, min_qty: 0 };
  const f = (name, lab, extra = '', cls = '') =>
    `<label class="${cls}">${lab}<input type="text" name="${name}" value="${esc(c[name] ?? '')}" ${extra}></label>`;
  openModal(`<form method="dialog" id="edit-form"><div class="modal-body">
    <h2>${isNew ? 'Yeni parça' : 'Parçayı düzenle'}</h2>
    <div class="form-grid">
      ${f('mpn', 'Üretici parça no (MPN)', 'autofocus placeholder="ör. RC0603FR-0710KL"')}
      ${f('value', 'Değer', 'placeholder="ör. 10k, 100nF, STM32F103"')}
      <label>Kategori<select name="category"><option value="">Otomatik belirle</option>${catOptions(c.category)}</select></label>
      ${f('package', 'Kılıf', 'placeholder="ör. 0603, SOT-23"')}
      ${f('manufacturer', 'Üretici')}
      ${f('supplier_pn', 'Tedarikçi kodu', 'placeholder="ör. LCSC C25804"')}
      ${f('description', 'Açıklama', '', 'full')}
      <label>Adet<input type="number" name="quantity" min="0" value="${c.quantity}"></label>
      <label>Uyarı eşiği (min. adet)<input type="number" name="min_qty" min="0" value="${c.min_qty}"></label>
      ${f('location', 'Konum', 'placeholder="ör. Kutu A / Çekmece 3"')}
      ${f('notes', 'Notlar')}
    </div></div>
    <div class="modal-foot">
      ${isNew ? '' : '<button type="button" class="btn danger" id="del-btn">Sil</button>'}
      <span class="spacer"></span>
      <button type="button" class="btn" onclick="modal().close()">Vazgeç</button>
      <button type="submit" class="btn primary">${isNew ? 'Ekle' : 'Kaydet'}</button>
    </div></form>`);
  $('#edit-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    try {
      if (isNew) await api('/api/components', { method: 'POST', body: data });
      else await api('/api/components/' + c.id, { method: 'PUT', body: data });
      modal().close();
      await loadComps();
      render();
      toast(isNew ? 'Parça eklendi' : 'Kaydedildi');
    } catch (err) { fail(err); }
  });
  const del = $('#del-btn');
  if (del) del.onclick = async () => {
    if (!confirm(`"${label(c)}" silinsin mi? Geçmiş kayıtları korunur.`)) return;
    try {
      await api('/api/components/' + c.id, { method: 'DELETE' });
      modal().close();
      await loadComps();
      render();
      toast('Parça silindi');
    } catch (err) { fail(err); }
  };
}

function openAdjust(c, sign) {
  const add = sign > 0;
  openModal(`<form method="dialog" id="adj-form"><div class="modal-body">
    <h2>${add ? 'Stoğa ekle' : 'Stoktan düş'}: ${esc(label(c))}</h2>
    <p class="muted">Şu an stokta: <b>${c.quantity}</b> adet</p>
    <div class="form-grid">
      <label>Miktar<input type="number" name="amount" min="1" value="1" autofocus required></label>
      <label>Not (isteğe bağlı)<input type="text" name="note" placeholder="${add ? 'ör. Arkadaştan aldım' : 'ör. Prototip, bozuldu'}"></label>
    </div></div>
    <div class="modal-foot"><span class="spacer"></span>
      <button type="button" class="btn" onclick="modal().close()">Vazgeç</button>
      <button type="submit" class="btn ${add ? 'primary' : 'danger-fill'}">${add ? 'Ekle' : 'Düş'}</button>
    </div></form>`);
  $('#adj-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const amount = parseInt(d.amount, 10);
    if (!(amount > 0)) return toast('Geçerli bir miktar girin', true);
    try {
      const r = await api(`/api/components/${c.id}/adjust`, { method: 'POST', body: { delta: sign * amount, note: d.note } });
      modal().close();
      await loadComps();
      render();
      toast(`${label(c)}: ${r.delta > 0 ? '+' : ''}${r.delta} adet`);
    } catch (err) { fail(err); }
  });
}

// ------------------------------------------------------------ içe aktarma (sipariş + BOM)
function importShell(kind) {
  const bom = kind === 'bom';
  return `<div class="card">
    <h2>${bom ? 'Proje BOM\'u' : 'Sipariş listesi'}</h2>
    <p class="muted">${bom
      ? 'KiCad, Altium, EasyEDA vb. programlardan aldığınız BOM dosyasını yükleyin. Önce hangi parçaların stokta olduğunu, hangilerinin eksik olduğunu görürsünüz; onaylarsanız kullanılan parçalar stoktan düşülür.'
      : 'LCSC, Mouser, DigiKey vb. sitelerden indirdiğiniz sipariş dökümünü ya da faturanın PDF dosyasını veya fotoğrafını yükleyin. Parçalar okunur, kategorilerine ayrılır ve stoğa eklenir. Stokta zaten olan parçaların adedi artırılır.'}</p>
    <label class="drop"><input type="file" ${bom ? '' : 'multiple'} accept="${bom ? '' : 'image/*,.heic,.heif,.pdf,.xml,.zip,'}.csv,.tsv,.txt,.xlsx,.xls,.htm,.html" hidden>
      <b>${bom ? 'Dosyayı' : 'Dosyayı (veya birden çok dosyayı)'} buraya bırakın</b><span>veya tıklayıp seçin · CSV, XLSX, TSV, HTML${bom ? '' : ' · <b>fatura PDF / fotoğraf / e-fatura XML</b>'}</span></label>
    <details class="paste"><summary>…ya da tabloyu kopyalayıp yapıştırın</summary>
      <textarea rows="6" placeholder="Excel'den veya web sayfasından kopyaladığınız tablo (başlık satırıyla birlikte)"></textarea>
      <button class="btn" data-act="paste">Önizle</button></details>
  </div><div class="preview"></div>`;
}

function renderImport(kind) {
  const sec = $('#view-' + kind);
  if (!sec.dataset.ready) {
    sec.innerHTML = importShell(kind);
    sec.dataset.ready = '1';
    bindImport(kind, sec);
  }
  renderPreview(kind);
}

function bindImport(kind, sec) {
  const drop = $('.drop', sec);
  const input = $('input[type=file]', sec);
  const readFile = (file) => new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => {
      const [head, b64] = String(fr.result).split(',');
      const mime = (head.match(/^data:([^;]+)/) || [])[1] || '';
      const isImage = mime.startsWith('image/') || /\.(heic|heif|jpe?g|png)$/i.test(file.name);
      resolve({ file_name: file.name, file_b64: b64, mime: isImage ? (mime || 'image/heic') : '' });
    };
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(file);
  });
  const readFiles = async (list) => {
    const files = [...list];
    if (!files.length) return;
    if (kind === 'bom' || files.length === 1) {
      if (/\.(pdf|heic|heif|jpe?g|png)$/i.test(files[0].name)) toast('Belge okunuyor…');
      return preview(kind, await readFile(files[0]));
    }
    previewMany(kind, files, readFile);
  };
  input.addEventListener('change', () => { readFiles(input.files); input.value = ''; });
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('over');
    readFiles(e.dataTransfer.files);
  });
  sec.addEventListener('click', (e) => {
    const pk = e.target.closest('[data-pick]');
    if (pk) return openPicker(kind, +pk.dataset.pick);
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    if (act === 'paste') {
      const text = $('textarea', sec).value;
      if (!text.trim()) return toast('Önce tabloyu yapıştırın', true);
      preview(kind, { file_name: 'Yapıştırılan tablo', text });
    } else if (act === 'commit') commit(kind);
    else if (act === 'cancel') { S.imp[kind] = null; renderPreview(kind); }
    else if (act === 'shortcsv') shortageCSV();
    else if (act === 'all-new' || act === 'all-skip') {
      S.imp[kind].items.forEach((it) => { if (act === 'all-skip' || it.action !== 'match') it.action = act === 'all-new' ? 'new' : 'skip'; });
      renderPreview(kind);
    } else if (act === 'goto-stock') setView('stock');
  });
  sec.addEventListener('change', (e) => {
    const t = e.target;
    const st = S.imp[kind];
    if (!st) return;
    if (t.dataset.map !== undefined || t.dataset.headerrow !== undefined) {
      const mapping = {};
      sec.querySelectorAll('[data-map]').forEach((s) => (mapping[s.dataset.map] = parseInt(s.value, 10)));
      const hr = parseInt($('[data-headerrow]', sec).value, 10) - 1;
      const headerChanged = t.dataset.headerrow !== undefined;
      preview(kind, { ...st.src, header_row: isNaN(hr) ? -1 : hr, mapping: headerChanged ? null : mapping }, true);
      return;
    }
    if (t.dataset.f === 'mult') { st.mult = Math.max(1, parseInt(t.value, 10) || 1); renderPreview(kind); return; }
    if (t.dataset.f === 'name') { st.name = t.value; return; }
    const i = t.dataset.i;
    if (i === undefined) return;
    const it = st.items[i];
    const f = t.dataset.f;
    if (f === 'match') {
      if (t.value.startsWith('c:')) { it.action = 'match'; it.component_id = parseInt(t.value.slice(2), 10); it.confidence = 'user'; }
      else it.action = t.value;
    } else if (f === 'qty') it.qty = Math.max(0, parseInt(t.value, 10) || 0);
    else it[f] = t.value;
    renderPreview(kind);
  });
}

function initItems(kind, items) {
  items.forEach((it) => {
    if (it.skip_reason) it.action = 'skip';
    else if (it.match_id) { it.action = 'match'; it.component_id = it.match_id; }
    else it.action = kind === 'order' ? 'new' : 'none';
  });
}

// Birden çok sipariş dosyasını (ör. eski faturaların PDF'leri) tek önizlemede birleştirir.
async function previewMany(kind, files, readFile) {
  const items = [];
  const failed = [];
  for (let i = 0; i < files.length; i++) {
    toast(`Okunuyor ${i + 1}/${files.length}: ${files[i].name}`);
    try {
      const src = await readFile(files[i]);
      const d = await api('/api/import/preview', { method: 'POST', body: { kind, ...src } });
      d.items.forEach((it) => (it.source = files[i].name));
      items.push(...d.items);
      if (!d.items.length) failed.push(`${files[i].name} (parça satırı yok)`);
    } catch (e) { failed.push(`${files[i].name} (${e.message})`); }
  }
  initItems(kind, items);
  S.imp[kind] = {
    headers: [], mapping: {}, fields: {}, items, failed,
    src: { file_name: `${files.length} dosya`, multi: true },
    mult: 1, name: `${files.length - failed.length} fatura`, done: null,
  };
  renderPreview(kind);
  if (failed.length) toast(`${failed.length} dosya okunamadı`, true);
  else toast(`${files.length} dosyadan ${items.length} satır okundu`);
}

async function preview(kind, src, keepOpen = false) {
  try {
    const d = await api('/api/import/preview', { method: 'POST', body: { kind, ...src } });
    const prev = S.imp[kind];
    initItems(kind, d.items);
    const base = (src.file_name || '').replace(/\.[^.]+$/, '');
    S.imp[kind] = {
      ...d, src: { file_name: src.file_name, file_b64: src.file_b64, text: src.text, mime: src.mime },
      mult: prev?.mult || 1, name: prev && keepOpen ? prev.name : base, mapOpen: keepOpen, done: null,
    };
    renderPreview(kind);
    if (!d.items.length) toast('Tabloda parça satırı bulunamadı. Sütun eşleştirmesini kontrol edin.', true);
  } catch (e) { fail(e); }
}

function mappingPanel(st) {
  const opts = (sel) => opt(-1, '— yok —', sel) + st.headers.map((h, i) => opt(i, h, sel)).join('');
  return `<details class="mapping card"${st.mapOpen ? ' open' : ''}><summary>Sütun eşleştirme
      <span class="muted small">— otomatik algılandı; yanlış okunan bir şey varsa buradan düzeltin</span></summary>
    <div class="map-grid">
      ${Object.entries(st.fields).map(([f, lab]) => `<label>${esc(lab)}<select data-map="${f}">${opts(st.mapping[f])}</select></label>`).join('')}
      <label>Başlık satırı no<input type="number" min="0" data-headerrow value="${st.header_row + 1}"></label>
    </div></details>`;
}

// ------------------------------------------------------------ eşleşme seçici (kategorili açılır pencere)
function pickButton(it, i) {
  let text = 'Atlandı', cls = 'skip';
  if (it.action === 'match') { const c = byId(it.component_id); text = c ? label(c) : '?'; cls = ''; }
  else if (it.action === 'new') { text = '+ Yeni parça olarak ekle'; cls = 'new'; }
  else if (it.action === 'none') { text = '✕ Stokta yok'; cls = 'none'; }
  const cand = it.action === 'match' && it.confidence !== 'user' && it.candidates.find((c) => c.id === it.component_id);
  return `<button type="button" class="pick ${cls}" data-pick="${i}" title="Değiştirmek için tıklayın">
      <span class="pick-text">${esc(text)}</span><span class="caret">▾</span></button>
    ${cand ? `<div class="hint muted">${esc(cand.reason)}</div>` : ''}${it.confidence === 'user' ? '<div class="hint muted">Elle seçildi</div>' : ''}`;
}

let P = null; // açık seçici durumu
function compHay(c) {
  return lower([label(c), c.mpn, c.supplier_pn, c.manufacturer, c.description, c.value, c.package, c.location, c.notes].join(' '));
}

function openPicker(kind, i) {
  const it = S.imp[kind].items[i];
  const cands = it.candidates.filter((c) => byId(c.id));
  P = { kind, i, q: '', cat: cands.length ? '__cand' : (S.comps.some((c) => c.category === it.category) ? it.category : '__all') };
  const what = [it.designators?.join(', '), it.mpn || it.value, it.package_raw || it.package, it.description]
    .filter(Boolean).join(' · ');
  const special = (act, text, cls = '') => `<button type="button" class="btn sm ${cls}" data-special="${act}">${text}</button>`;
  openModal(`<div class="picker">
    <div class="pk-head">
      <div class="pk-title"><h2>Stoktaki karşılığını seçin</h2><div class="muted small" title="${esc(what)}">${esc(what)}</div></div>
      <button type="button" class="icon-btn" data-close title="Kapat">✕</button>
    </div>
    <div class="pk-search">
      <input type="search" id="pk-q" placeholder="Ara: değer, pin sayısı, kılıf, açıklama, kod…" autocomplete="off" autofocus>
      ${kind === 'order' ? special('new', '+ Yeni parça') : special('none', '✕ Stokta yok', 'danger')}
      ${special('skip', 'Atla')}
    </div>
    <div class="pk-body"><nav class="pk-cats side"></nav><div class="pk-list"></div></div>
  </div>`);
  modal().classList.add('wide');
  renderPicker();
  const q = $('#pk-q');
  q.addEventListener('input', () => { P.q = q.value; if (P.q.trim() && P.cat === '__cand') P.cat = '__all'; renderPicker(); });
  q.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const first = $('.pk-row', modal());
    if (first) pickChoose(+first.dataset.cid);
  });
}

function renderPicker() {
  const it = S.imp[P.kind].items[P.i];
  const words = lower(P.q).trim().split(/\s+/).filter(Boolean);
  const ok = (c) => !words.length || words.every((w) => compHay(c).includes(w));
  const candById = Object.fromEntries(it.candidates.map((c) => [c.id, c]));
  const cands = it.candidates.map((c) => byId(c.id)).filter((c) => c && ok(c));
  const pool = S.comps.filter(ok);
  const counts = {};
  pool.forEach((c) => (counts[c.category] = (counts[c.category] || 0) + 1));
  if (!P.cat.startsWith('__') && !counts[P.cat] && words.length) P.cat = '__all';

  const nb = (k, text, n) => `<button type="button" data-pcat="${esc(k)}" class="${P.cat === k ? 'active' : ''}">
    <span>${esc(text)}</span><span class="count">${n}</span></button>`;
  $('.pk-cats', modal()).innerHTML =
    (it.candidates.length ? nb('__cand', '★ Önerilenler', cands.length) : '') +
    nb('__all', 'Tümü', pool.length) + '<hr>' +
    S.cats.filter((c) => counts[c]).map((c) => nb(c, c + (c === it.category ? ' •' : ''), counts[c])).join('');

  const cur = it.action === 'match' ? it.component_id : null;
  const row = (c) => {
    const cand = candById[c.id];
    const sub = [c.mpn && c.value ? c.value : '', c.description !== label(c) ? c.description : '', c.supplier_pn !== label(c) ? c.supplier_pn : '']
      .filter(Boolean).join(' · ');
    return `<button type="button" class="pk-row ${c.id === cur ? 'sel' : ''}" data-cid="${c.id}">
      <span class="pk-main"><b>${esc(label(c))}</b>${sub ? `<span class="sub">${esc(sub)}</span>` : ''}</span>
      ${cand ? `<span class="pill ${cand.score >= 80 ? 'ok' : cand.score >= 55 ? 'info' : 'mute'}" title="Eşleşme puanı ${cand.score}">${esc(cand.reason)}</span>` : ''}
      <span class="pk-pkg muted small">${esc(c.package && c.package !== label(c) ? c.package : '')}</span>
      <span class="pk-qty ${c.quantity ? '' : 'out'}">${c.quantity} ad.</span>
    </button>`;
  };
  let html = '';
  if (P.cat === '__cand') {
    html = cands.map(row).join('');
  } else {
    const list = P.cat === '__all' ? pool : pool.filter((c) => c.category === P.cat);
    const catOrder = Object.fromEntries(S.cats.map((c, k) => [c, c === it.category ? -1 : k]));
    list.sort((a, b) => (catOrder[a.category] ?? 99) - (catOrder[b.category] ?? 99) || label(a).localeCompare(label(b), 'tr', { numeric: true }));
    let last = null;
    html = list.map((c) => {
      const head = P.cat === '__all' && c.category !== last ? `<div class="pk-group">${esc((last = c.category))}</div>` : '';
      return head + row(c);
    }).join('');
  }
  $('.pk-list', modal()).innerHTML = html || '<div class="empty">Eşleşen parça yok.</div>';
}

function pickChoose(cid, special) {
  const it = S.imp[P.kind].items[P.i];
  if (special) it.action = special;
  else { it.action = 'match'; it.component_id = cid; it.confidence = 'user'; }
  const kind = P.kind;
  modal().close();
  renderPreview(kind);
}

modal().addEventListener('click', (e) => {
  if (!P || !modal().classList.contains('wide')) return;
  const t = e.target;
  if (t.closest('[data-close]')) return modal().close();
  const pc = t.closest('[data-pcat]');
  if (pc) { P.cat = pc.dataset.pcat; return renderPicker(); }
  const r = t.closest('[data-cid]');
  if (r) return pickChoose(+r.dataset.cid);
  const sp = t.closest('[data-special]');
  if (sp) pickChoose(null, sp.dataset.special);
});
modal().addEventListener('close', () => { modal().classList.remove('wide'); P = null; });

// ------------------------------------------------------------ KiCad tarzı yeniden adlandırma
async function openRename() {
  let sug;
  try { ({ suggestions: sug } = await api('/api/rename/suggest')); } catch (e) { return fail(e); }
  if (!sug.length) return toast('Önerilecek yeni ad yok — stoktaki adlar zaten düzgün görünüyor');
  const FL = { mpn: 'MPN', value: 'Değer', package: 'Kılıf' };
  const rows = sug.map((s, k) => {
    const c = byId(s.id);
    return `<tr><td><input type="checkbox" data-rn="${k}" checked></td>
      <td class="part"><b>${esc(label(c))}</b><div class="sub">${esc(c.description)}</div></td>
      <td>${Object.entries(s.new).map(([f, v]) => `<div class="small"><span class="muted">${FL[f]}:</span> ${s.old[f] ? `<s class="muted">${esc(s.old[f])}</s> → ` : ''}<b>${esc(v)}</b></div>`).join('')}</td></tr>`;
  }).join('');
  openModal(`<form method="dialog" id="rn-form"><div class="modal-body">
    <h2>KiCad tarzı adlandırma</h2>
    <p class="muted small">Açıklamalardan çıkarılan bilgilerle (aile, pin sayısı, adım, yön…) parçalara KiCad kütüphanesine benzer
      değer ve kılıf adı önerilir. Böylece stok listesinde "20259" gibi kodlar yerine anlamlı adlar görünür ve BOM eşleşmesi kolaylaşır.
      Tedarikçi kodu ve açıklama değişmez.</p>
    <div class="table-wrap rn-wrap"><table class="grid"><thead><tr><th></th><th>Parça</th><th>Önerilen</th></tr></thead><tbody>${rows}</tbody></table></div>
    </div><div class="modal-foot"><span class="spacer"></span>
      <button type="button" class="btn" onclick="modal().close()">Vazgeç</button>
      <button type="submit" class="btn primary">Seçilenleri uygula</button></div></form>`);
  modal().classList.add('wide');
  $('#rn-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const changes = sug.filter((_, k) => $(`[data-rn="${k}"]`).checked).map((s) => ({ id: s.id, fields: s.new }));
    try {
      const r = await api('/api/rename/apply', { method: 'POST', body: { changes } });
      modal().close();
      await loadComps();
      render();
      toast(`${r.updated} parça yeniden adlandırıldı`);
    } catch (err) { fail(err); }
  });
}

function partCell(it) {
  const main = it.mpn || it.value || it.supplier_pn || it.description.slice(0, 40);
  const sub = [it.mpn && it.value ? it.value : '', it.manufacturer, it.supplier_pn !== main ? it.supplier_pn : ''].filter(Boolean).join(' · ');
  return `<td class="part"><b>${esc(main)}</b>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}
    ${it.description && it.description !== main ? `<div class="sub" title="${esc(it.description)}">${esc(it.description.slice(0, 70))}${it.description.length > 70 ? '…' : ''}</div>` : ''}
    ${it.attrs && (it.attrs.mount || it.attrs.ctype || it.attrs.pot) ? `<div class="sub">${esc([it.attrs.mount, it.attrs.ctype, it.attrs.pot ? 'potansiyometre' : ''].filter(Boolean).join(' · '))}</div>` : ''}
    ${it.source ? `<div class="sub">📄 ${esc(it.source)}</div>` : ''}</td>`;
}

function renderPreview(kind) {
  const box = $(`#view-${kind} .preview`);
  const st = S.imp[kind];
  if (!st) { box.innerHTML = ''; return; }
  if (st.done) { box.innerHTML = st.done; return; }
  box.innerHTML = kind === 'order' ? orderPreview(st) : bomPreview(st);
}

function orderPreview(st) {
  const n = { match: 0, new: 0, skip: 0 };
  st.items.forEach((it) => (n[it.action] = (n[it.action] || 0) + 1));
  const rows = st.items.map((it, i) => {
    const warn = it.action === 'match' && it.confidence === 'low';
    return `<tr class="${it.action === 'skip' ? 'skipped' : ''}">
      ${partCell(it)}
      <td><select data-i="${i}" data-f="category">${catOptions(it.category)}</select></td>
      <td><input type="text" class="w-s" data-i="${i}" data-f="value" value="${esc(it.value)}"></td>
      <td><input type="text" class="w-s" data-i="${i}" data-f="package" value="${esc(it.package)}"></td>
      <td class="num"><input type="number" class="w-n" min="0" data-i="${i}" data-f="qty" value="${it.qty}"></td>
      <td>${pickButton(it, i)}
        ${warn ? '<div class="hint warn">Emin değilim — kontrol edin</div>' : ''}
        ${it.skip_reason ? `<div class="hint warn">${esc(it.skip_reason)}</div>` : ''}
        ${it.pack > 1 ? `<div class="hint muted">${it.pack}'li paket: adet, paket sayısı × ${it.pack} olarak hesaplandı</div>` : ''}</td>
    </tr>`;
  }).join('');
  const total = st.items.filter((it) => it.action !== 'skip').reduce((s, it) => s + it.qty, 0);
  const photo = st.src.mime ? `<details class="card photo" open><summary>Fatura fotoğrafı
      <span class="muted small">— okunan satırları fotoğrafla karşılaştırın; yanlış okunan değer, adet veya kategoriyi tabloda düzeltebilirsiniz</span></summary>
      <img src="data:${esc(st.src.mime)};base64,${st.src.file_b64}" alt="Fatura fotoğrafı"></details>`
    : st.src.multi ? (st.failed.length ? `<div class="card"><b>Okunamayan dosyalar:</b><ul>${st.failed.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>` : '')
    : mappingPanel(st);
  return `${photo}
    <div class="card">
      <div class="prev-head">
        <h3 style="margin:0">${esc(st.src.file_name)}</h3>
        <div class="summary">
          <span class="pill ok">${n.match} stokta var → adet artacak</span>
          <span class="pill info">${n.new} yeni parça</span>
          ${n.skip ? `<span class="pill mute">${n.skip} atlanacak</span>` : ''}
        </div>
        <span class="spacer"></span>
        <div class="bom-ctrl"><label>Sipariş adı<input type="text" data-f="name" value="${esc(st.name)}" size="24"></label></div>
      </div>
      <div class="table-wrap"><table class="grid">
        <thead><tr><th>Parça</th><th>Kategori</th><th>Değer</th><th>Kılıf</th><th class="num">Adet</th><th>Stoktaki karşılığı</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="empty">Satır yok</td></tr>'}</tbody></table></div>
      <div class="footer-actions">
        <button class="btn ghost" data-act="cancel">Vazgeç</button>
        <button class="btn primary" data-act="commit" ${n.match + n.new ? '' : 'disabled'}>Stoğa ekle (${n.match + n.new} kalem, ${total.toLocaleString('tr')} adet)</button>
      </div>
    </div>`;
}

function bomNeed(st) {
  const need = {};
  st.items.forEach((it) => { if (it.action === 'match') need[it.component_id] = (need[it.component_id] || 0) + it.qty * st.mult; });
  return need;
}

function bomStatus(st, it, need) {
  if (it.action === 'skip') return { cls: 'mute', text: 'Atlandı', key: 'skip' };
  if (it.action === 'none') return { cls: 'bad', text: 'Stokta yok', key: 'none' };
  const c = byId(it.component_id);
  const total = need[it.component_id];
  if (c.quantity >= total) return { cls: 'ok', text: 'Yeterli', key: 'ok' };
  return { cls: 'warn', text: `${total - c.quantity} eksik`, key: 'short' };
}

function shortageList(st) {
  const need = bomNeed(st);
  const out = [];
  Object.entries(need).forEach(([id, n]) => {
    const c = byId(+id);
    if (c && c.quantity < n) out.push({ name: label(c), mpn: c.mpn, spn: c.supplier_pn, mfr: c.manufacturer, value: c.value, pkg: c.package, desc: c.description, need: n, have: c.quantity });
  });
  st.items.forEach((it) => {
    if (it.action === 'none') out.push({ name: it.mpn || it.value || it.description, mpn: it.mpn, spn: it.supplier_pn, mfr: it.manufacturer, value: it.value, pkg: it.package, desc: it.description, need: it.qty * st.mult, have: 0, refs: it.designators.join(' ') });
  });
  return out;
}

function bomPreview(st) {
  const need = bomNeed(st);
  const cnt = { ok: 0, short: 0, none: 0, skip: 0 };
  const rows = st.items.map((it, i) => {
    const s = bomStatus(st, it, need);
    cnt[s.key]++;
    const c = it.action === 'match' ? byId(it.component_id) : null;
    const refs = it.designators.join(', ');
    const warn = it.action === 'match' && it.confidence === 'low';
    return `<tr class="${it.action === 'skip' ? 'skipped' : ''}">
      <td class="small" title="${esc(refs)}">${esc(refs.length > 28 ? refs.slice(0, 28) + '…' : refs)}</td>
      ${partCell(it)}
      <td>${esc(it.package)}</td>
      <td class="num"><input type="number" class="w-n" min="0" data-i="${i}" data-f="qty" value="${it.qty}"></td>
      <td class="num">${it.action === 'skip' ? '—' : it.qty * st.mult}</td>
      <td class="num">${c ? c.quantity : '—'}</td>
      <td><span class="pill ${s.cls}">${s.text}</span></td>
      <td>${pickButton(it, i)}${warn ? '<div class="hint warn">Emin değilim — kontrol edin</div>' : ''}
        ${it.action === 'none' && it.candidates.length && byId(it.candidates[0].id) ? `<div class="hint">Alternatif: ${esc(label(byId(it.candidates[0].id)))} — ${esc(it.candidates[0].reason)}</div>` : ''}</td>
    </tr>`;
  }).join('');
  const shorts = shortageList(st);
  const deduct = Object.entries(need).reduce((s, [id, n]) => s + Math.min(n, byId(+id)?.quantity || 0), 0);
  const shortTable = shorts.length ? `<div class="card">
      <h3>Sipariş edilmesi gerekenler (${shorts.length} kalem)</h3>
      <div class="table-wrap"><table class="grid"><thead><tr><th>Parça</th><th>Kılıf</th><th>Tedarikçi kodu</th><th class="num">Gerekli</th><th class="num">Stokta</th><th class="num">Alınacak</th></tr></thead><tbody>
      ${shorts.map((s) => `<tr><td class="part"><b>${esc(s.name)}</b>${s.desc && s.desc !== s.name ? `<div class="sub">${esc(s.desc.slice(0, 80))}</div>` : ''}</td><td>${esc(s.pkg)}</td><td>${esc(s.spn)}</td>
        <td class="num">${s.need}</td><td class="num">${s.have}</td><td class="num"><b>${s.need - s.have}</b></td></tr>`).join('')}
      </tbody></table></div>
      <div class="footer-actions"><button class="btn" data-act="shortcsv">Eksik listesini indir (CSV)</button></div>
    </div>` : '';
  return `${mappingPanel(st)}
    <div class="card">
      <div class="prev-head">
        <div class="bom-ctrl">
          <label>Proje adı<input type="text" data-f="name" value="${esc(st.name)}" size="24"></label>
          <label>Kaç adet yapılacak?<input type="number" min="1" data-f="mult" value="${st.mult}" style="width:90px"></label>
        </div>
        <span class="spacer"></span>
        <div class="summary">
          <span class="pill ok">${cnt.ok} yeterli</span>
          ${cnt.short ? `<span class="pill warn">${cnt.short} eksik</span>` : ''}
          ${cnt.none ? `<span class="pill bad">${cnt.none} stokta yok</span>` : ''}
          ${cnt.skip ? `<span class="pill mute">${cnt.skip} atlandı</span>` : ''}
        </div>
      </div>
      <div class="table-wrap"><table class="grid">
        <thead><tr><th>Referans</th><th>Parça</th><th>Kılıf</th><th class="num">Kart başı</th><th class="num">Toplam</th><th class="num">Stokta</th><th>Durum</th><th>Stoktaki karşılığı</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="8" class="empty">Satır yok</td></tr>'}</tbody></table></div>
      <div class="footer-actions">
        <button class="btn ghost" data-act="cancel">Vazgeç</button>
        <button class="btn danger-fill" data-act="commit" ${deduct ? '' : 'disabled'}>Stoktan düş (${deduct.toLocaleString('tr')} adet)</button>
      </div>
    </div>${shortTable}`;
}

function shortageCSV() {
  const st = S.imp.bom;
  const rows = [['Parça', 'MPN', 'Tedarikçi Kodu', 'Üretici', 'Değer', 'Kılıf', 'Açıklama', 'Gerekli', 'Stokta', 'Alınacak']];
  shortageList(st).forEach((s) => rows.push([s.name, s.mpn, s.spn, s.mfr, s.value, s.pkg, s.desc, s.need, s.have, s.need - s.have]));
  downloadCSV(`${(st.name || 'proje').replace(/[^\wçğıöşüÇĞİÖŞÜ.-]+/g, '_')}_eksikler.csv`, rows);
}

async function commit(kind) {
  const st = S.imp[kind];
  const items = st.items.map((it) => ({
    action: it.action, component_id: it.component_id, qty: it.qty,
    mpn: it.mpn, supplier_pn: it.supplier_pn, manufacturer: it.manufacturer, description: it.description,
    category: it.category, value: it.value, package: it.package, learn: it.confidence === 'user',
    label: it.mpn || it.value || it.description,
  }));
  if (kind === 'bom') {
    const shorts = shortageList(st).length;
    const msg = `"${st.name || 'Proje'}" × ${st.mult} için kullanılan parçalar stoktan düşülecek.` +
      (shorts ? `\n\n${shorts} kalem eksik: bunların stokta olan kısmı düşülür, kalanı proje kaydına "eksik" olarak yazılır.` : '');
    if (!confirm(msg)) return;
  }
  try {
    const r = await api('/api/import/commit', { method: 'POST', body: { kind, name: st.name, multiplier: st.mult, items } });
    await loadComps();
    st.done = kind === 'order'
      ? `<div class="card result"><h3>Sipariş stoğa işlendi</h3><p>${r.lines} kalem eklendi${r.created ? `, bunlardan ${r.created} tanesi yeni parça` : ''}.</p>
         <div class="footer-actions" style="justify-content:flex-start"><button class="btn primary" data-act="goto-stock">Stoğa git</button><button class="btn" data-act="cancel">Yeni dosya yükle</button></div></div>`
      : `<div class="card result"><h3>Proje stoktan düşüldü</h3><p>${r.used.toLocaleString('tr')} adet parça düşüldü.${r.shortages.length ? ` ${r.shortages.length} kalem eksikti; liste Geçmiş sekmesinde proje kaydında duruyor.` : ''}</p>
         <div class="footer-actions" style="justify-content:flex-start"><button class="btn primary" data-act="goto-stock">Stoğa git</button><button class="btn" data-act="cancel">Yeni BOM yükle</button></div></div>`;
    renderPreview(kind);
    toast('İşlem kaydedildi — Geçmiş sekmesinden geri alabilirsiniz');
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------ geçmiş
async function renderHistory() {
  const box = $('#history');
  try {
    const { batches } = await api('/api/batches');
    if (!batches.length) { box.innerHTML = '<div class="card empty">Henüz işlem yok.</div>'; return; }
    box.innerHTML = batches.map((b) => {
      const plus = b.lines.filter((l) => l.delta > 0).reduce((s, l) => s + l.delta, 0);
      const minus = b.lines.filter((l) => l.delta < 0).reduce((s, l) => s - l.delta, 0);
      const shorts = b.info?.shortages || [];
      const lines = b.lines.map((l) => `<tr><td>${esc(l.label)}</td><td class="num ${l.delta > 0 ? 'plus' : 'minus'}">${l.delta > 0 ? '+' : ''}${l.delta}</td></tr>`).join('');
      return `<div class="card hist ${b.undone ? 'undone' : ''}">
        <div class="hist-head">
          <span class="pill k-${b.kind}">${KIND_LABEL[b.kind] || b.kind}</span>
          <b>${esc(b.name)}${b.multiplier > 1 ? ` × ${b.multiplier}` : ''}</b>
          <span class="muted small">${fmtDate(b.created_at)}</span>
          <span class="spacer"></span>
          ${plus ? `<span class="plus small">+${plus}</span>` : ''}${minus ? `<span class="minus small">−${minus}</span>` : ''}
          ${shorts.length ? `<span class="pill warn">${shorts.length} eksik</span>` : ''}
          ${b.undone ? '<span class="pill mute">Geri alındı</span>' : `<button class="btn sm ghost" data-undo="${b.id}">Geri al</button>`}
        </div>
        ${b.lines.length || shorts.length ? `<details><summary class="small">${b.lines.length} kalem${shorts.length ? ' · eksik listesi' : ''}</summary>
          ${lines ? `<table>${lines}</table>` : ''}
          ${shorts.length ? `<table><tr><td colspan="2"><b class="small">Eksik kalan parçalar</b></td></tr>${shorts.map((s) => `<tr><td>${esc(s.label)}</td><td class="num minus">${s.short} eksik</td></tr>`).join('')}</table>` : ''}
        </details>` : ''}
      </div>`;
    }).join('');
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------ olaylar
document.querySelector('.tabs').addEventListener('click', (e) => {
  const t = e.target.closest('.tab');
  if (t) setView(t.dataset.view);
});
$('#btn-new').addEventListener('click', () => openEdit(null));
$('#btn-rename').addEventListener('click', openRename);
$('#cat-list').addEventListener('click', (e) => {
  const b = e.target.closest('[data-cat]');
  if (b) { S.cat = b.dataset.cat; renderStock(); }
});
$('#search').addEventListener('input', (e) => { S.q = e.target.value; renderStockTable(); });
$('#stock-table').addEventListener('click', (e) => {
  const tr = e.target.closest('tr[data-id]');
  if (!tr) return;
  const c = byId(+tr.dataset.id);
  const adj = e.target.closest('[data-adj]');
  if (adj) openAdjust(c, +adj.dataset.adj);
  else if (e.target.closest('[data-edit]')) openEdit(c);
});
$('#history').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-undo]');
  if (!b || !confirm('Bu işlem geri alınsın mı? Stok miktarları işlemden önceki haline döner.')) return;
  try {
    await api(`/api/batches/${b.dataset.undo}/undo`, { method: 'POST' });
    await loadComps();
    renderHistory();
    toast('Geri alındı');
  } catch (err) { fail(err); }
});
modal().addEventListener('click', (e) => { if (e.target === modal()) modal().close(); });


(async () => {
  try { S.view = localStorage.getItem('stok.view') || 'stock'; } catch (e) { /* yoksay */ }
  try { await loadComps(); } catch (e) { fail(e); }
  render();
})();
