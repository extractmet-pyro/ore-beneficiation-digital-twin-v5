// Tiny DOM toolkit (no framework): element builder, tables, tabs, forms, modal, toasts.
import {esc, fmt, isNum} from '../utils/format.js';

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
export const html = s => { const t = document.createElement('template'); t.innerHTML = s.trim(); return t.content.firstChild; };
export const clear = el => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const grid = (cols, ...kids) => h('div', {class: `grid g${cols}`}, ...kids);
export const note = (text, kind = '') => h('div', {class: `note ${kind}`, html: text});
export const loading = (msg = 'Loading…') => h('div', {class: 'loading'}, h('span', {class: 'spinner'}), msg);

/** Sortable table. columns: [{key,label,fmt?,num?,render?}] or array of keys. */
export function table(rows, columns = null, {height = null, cellClass = null} = {}) {
  rows = rows || [];
  const cols = (columns || Object.keys(rows[0] || {})).map(c => typeof c === 'string' ? {key: c, label: c} : c);
  let sortKey = null, asc = true;
  const wrap = h('div', {class: 'tbl-wrap', style: height ? {maxHeight: `${height}px`} : null});
  function draw() {
    const data = [...rows];
    if (sortKey) data.sort((a, b) => { const x = a[sortKey], y = b[sortKey];
      return (x === y ? 0 : (x === null || x === undefined) ? 1 : (y === null || y === undefined) ? -1 : x > y ? 1 : -1) * (asc ? 1 : -1); });
    const tb = h('table', {class: 'tbl'},
      h('thead', {}, h('tr', {}, cols.map(c => h('th', {title: 'sort', onclick: () => { asc = sortKey === c.key ? !asc : true; sortKey = c.key; draw(); }},
        c.label, sortKey === c.key ? (asc ? ' ▲' : ' ▼') : '')))),
      h('tbody', {}, data.map(r => h('tr', {}, cols.map(c => {
        const v = r[c.key];
        if (c.render) { const out = c.render(v, r); return h('td', {class: c.num ? 'num' : ''}, out); }
        const numeric = isNum(v);
        const txt = numeric ? fmt(v, c.fmt || (Math.abs(v) >= 1000 ? ',.0f' : '.4g')) : (v === null || v === undefined ? '—' :
          (typeof v === 'object' ? JSON.stringify(v) : String(v)));
        const cls = [numeric ? 'num' : '', cellClass ? cellClass(c.key, v, r) || '' : ''].join(' ');
        return h('td', {class: cls}, txt);
      })))));
    clear(wrap).append(tb);
  }
  draw();
  return wrap;
}
export function kvTable(obj, k = 'Item', v = 'Value') {
  return table(Object.entries(obj || {}).map(([a, b]) => ({[k]: a, [v]: b})), [k, v]);
}

/** Tabs. items: [{label, render: (pane)=>void}] — panes rendered lazily on first open. */
export function tabs(items, id = 'tabs') {
  const bar = h('div', {class: 'tabs', role: 'tablist'});
  const panes = items.map(() => h('div', {class: 'tabpane'}));
  const done = new Set();
  const open = i => {
    [...bar.children].forEach((b, j) => b.classList.toggle('on', j === i));
    panes.forEach((p, j) => p.classList.toggle('on', j === i));
    if (!done.has(i)) { done.add(i); Promise.resolve(items[i].render(panes[i])).catch(e => panes[i].append(note(esc(e.message), 'err'))); }
    else window.dispatchEvent(new Event('resize'));
    sessionStorage.setItem(`tab-${id}`, i);
  };
  items.forEach((it, i) => bar.append(h('button', {role: 'tab', onclick: () => open(i)}, it.label)));
  const root = h('div', {}, bar, ...panes);
  const saved = Number(sessionStorage.getItem(`tab-${id}`) || 0);
  queueMicrotask(() => open(saved < items.length ? saved : 0));
  return root;
}

// ---------------------------------------------------------------- form controls
export function field(label, control, hint = '') {
  return h('div', {class: 'field'}, h('label', {}, label), control, hint ? h('div', {class: 'hint'}, hint) : null);
}
export function numberInput(value, {min, max, step, disabled, onchange} = {}) {
  const el = h('input', {type: 'number', value, min, max, step: step ?? 'any', disabled});
  if (onchange) el.addEventListener('change', () => onchange(Number(el.value)));
  el.getValue = () => (el.value === '' ? null : Number(el.value));
  return el;
}
export function select(options, value, {disabled, onchange, format} = {}) {
  const el = h('select', {disabled}, options.map(o => { const v = typeof o === 'object' ? o.value : o;
    return h('option', {value: v, selected: String(v) === String(value) || null}, typeof o === 'object' ? o.label : (format ? format(o) : o)); }));
  if (onchange) el.addEventListener('change', () => onchange(el.value));
  return el;
}
export function slider(value, min, max, {step, onchange} = {}) {
  const out = h('span', {class: 'mono', style: {fontSize: '.8rem'}}, fmt(value, '.4g'));
  const el = h('input', {type: 'range', min, max, step: step ?? (max - min) / 200, value});
  el.addEventListener('input', () => { out.textContent = fmt(Number(el.value), '.4g'); onchange && onchange(Number(el.value)); });
  const w = h('div', {class: 'row'}, h('div', {class: 'grow'}, el), out);
  w.getValue = () => Number(el.value);
  return w;
}
export function toggle(label, checked, onchange) {
  const cb = h('input', {type: 'checkbox', checked: checked || null, onchange: () => onchange && onchange(cb.checked)});
  const w = h('label', {class: 'switch'}, cb, label);
  w.input = cb;
  return w;
}
export function seg(options, value, onchange) {
  const w = h('div', {class: 'seg'});
  options.forEach(o => { const v = typeof o === 'object' ? o.value : o;
    w.append(h('button', {class: v === value ? 'on' : '', onclick: e => { [...w.children].forEach(b => b.classList.remove('on'));
      e.currentTarget.classList.add('on'); onchange(v); }}, typeof o === 'object' ? o.label : o)); });
  return w;
}
export const button = (label, onclick, cls = '', attrs = {}) => h('button', {class: `btn ${cls}`, onclick, ...attrs}, label);
export const expander = (title, body, open = false) => h('details', {class: 'exp', open: open || null}, h('summary', {}, title), body);

// ---------------------------------------------------------------- feedback
export function toast(msg, kind = '', ms = 4500) {
  const t = h('div', {class: `toast ${kind}`}, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), ms);
}
/** Confirmation dialog; resolves true/false. `requireCheck` adds a mandatory acknowledgement checkbox. */
export function confirmDialog(title, body, {okLabel = 'Confirm', requireCheck = null, danger = false} = {}) {
  return new Promise(resolve => {
    const root = document.getElementById('modal-root');
    const ok = button(okLabel, () => done(true), danger ? 'danger' : 'primary', {disabled: requireCheck ? true : null});
    const chk = requireCheck ? toggle(requireCheck, false, v => { ok.disabled = !v; }) : null;
    const bg = h('div', {class: 'modal-bg', onclick: e => { if (e.target === bg) done(false); }},
      h('div', {class: 'modal', role: 'dialog'}, h('h3', {}, title), typeof body === 'string' ? h('div', {html: body}) : body,
        chk ? h('div', {class: 'mt'}, chk) : null,
        h('div', {class: 'row mt', style: {justifyContent: 'flex-end'}}, button('Cancel', () => done(false)), ok)));
    function done(v) { bg.remove(); resolve(v); }
    root.append(bg);
  });
}
export function download(filename, content, mime = 'application/json') {
  const a = h('a', {href: URL.createObjectURL(new Blob([content], {type: mime})), download: filename});
  document.body.append(a); a.click(); a.remove();
}
export function toCSV(rows) {
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const q = v => { const s = v === null || v === undefined ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [cols.join(','), ...rows.map(r => cols.map(c => q(r[c])).join(','))].join('\n');
}
