// Operator desk bootstrap: hash router, sidebar (plant/persona/theme/units/mock/refresh), top bar, API status, auth gate.
import * as api from './api/client.js';
import * as S from './state.js';
import {h, clear, note, loading, select, toggle, button, toast} from './ui/dom.js';
import {PAGES, PERSONAS} from './utils/constants.js';
import {esc} from './utils/format.js';

const cfg = window.OBDT_CONFIG || {};
const pageModules = {
  home: () => import('./pages/home.js'), overview: () => import('./pages/overview.js'), live: () => import('./pages/live.js'),
  units: () => import('./pages/units.js'), simulate: () => import('./pages/simulate.js'), optimize: () => import('./pages/optimize.js'),
  gravity: () => import('./pages/gravity.js'), mpc: () => import('./pages/mpc.js'), ml: () => import('./pages/ml.js'), advisory: () => import('./pages/advisory.js'),
  health: () => import('./pages/health.js'), quality: () => import('./pages/quality.js'), admin: () => import('./pages/admin.js'),
  hybrid: () => import('./pages/hybrid.js'), plant3d: () => import('./pages/plant3d.js'),
  validation: () => import('./pages/validation.js'),
};
let cleanup = null, refreshTimer = null, renderSeq = 0;

export function currentRoute() {
  const [id, q] = (location.hash.replace(/^#\/?/, '') || 'home').split('?');
  return {id: pageModules[id] ? id : 'home', params: Object.fromEntries(new URLSearchParams(q || ''))};
}
export function go(id, params = {}) {
  const qs = new URLSearchParams(params).toString();
  location.hash = `#/${id}${qs ? '?' + qs : ''}`;
}
window.OBDT_GO = go;

function applyTheme() {
  document.documentElement.dataset.theme = S.get('theme');
  document.getElementById('app').classList.toggle('collapsed', !!S.get('collapsed'));
}

async function renderSidebar() {
  const sb = clear(document.getElementById('sidebar'));
  const {id} = currentRoute();
  sb.append(h('div', {class: 'brand'}, h('img', {src: 'assets/logo.svg', alt: ''}),
    h('div', {}, h('b', {}, cfg.APP_TITLE || 'Industry-X Ore Beneficiation Twin'), h('small', {}, 'Operator desk · HTML/CSS/JS · Three.js'))));
  sb.append(h('nav', {class: 'nav'}, PAGES.map(p => h('a', {href: `#/${p.id}`, class: p.id === id ? 'active' : '', title: p.desc},
    h('span', {class: 'ic'}, p.icon), h('span', {class: 'lbl'}, p.label)))));
  const blk = h('div', {class: 'side-block'});
  let plants = [];
  try { plants = (await api.get('plants')).plants; } catch (e) { plants = [{plant_id: S.get('plantId'), name: S.get('plantId'), grinding_circuit: ''}]; }
  if (!plants.some(p => p.plant_id === S.get('plantId'))) S.set('plantId', plants[0].plant_id);
  blk.append(h('label', {}, 'Plant / line'), select(plants.map(p => ({value: p.plant_id, label: `${p.plant_id} — ${p.name || ''}`})),
    S.get('plantId'), {onchange: v => { S.set('plantId', v); S.set('selectedUnit', null); route(); }}));
  blk.append(h('label', {}, 'Persona'), select(Object.keys(PERSONAS), S.get('persona'), {onchange: v => { S.set('persona', v); route(); }}),
    h('div', {class: 'subtitle', style: {marginTop: '4px'}}, PERSONAS[S.get('persona')].focus));
  blk.append(h('label', {}, 'Display'), h('div', {class: 'row'},
    toggle('Dark', S.get('theme') === 'dark', v => { S.set('theme', v ? 'dark' : 'light'); applyTheme(); route(); }),
    toggle('Imperial', S.get('unitSystem') === 'imperial', v => { S.set('unitSystem', v ? 'imperial' : 'metric'); route(); })));
  blk.append(h('label', {}, 'Data'), toggle('Mock mode (offline data)', api.useMock(), v => { S.set('mockOverride', v); api.clearCache(); route(); }));
  blk.append(h('div', {class: 'row mt'}, button('↻ Refresh', () => { api.clearCache(); route(); }),
    toggle('Auto', S.get('autoRefresh'), v => { S.set('autoRefresh', v); scheduleRefresh(); }),
    select([30, 60, 120, 300].map(s => ({value: s, label: `${s}s`})), S.get('refreshS'), {onchange: v => { S.set('refreshS', Number(v)); scheduleRefresh(); }})));
  blk.append(h('label', {}, 'API status'), statusTile());
  blk.append(h('div', {class: 'mt'}, button(S.get('collapsed') ? '»' : '« Collapse', () => { S.set('collapsed', !S.get('collapsed')); applyTheme(); renderSidebar(); })));
  sb.append(blk);
}

function statusTile() {
  const el = h('div', {class: 'tile', id: 'api-tile'});
  const draw = s => {
    const color = s.mode === 'live' && s.ok ? 'var(--ok)' : (s.mode === 'mock' ? 'var(--warn)' : 'var(--alarm)');
    el.innerHTML = `<b style="color:${color}">● ${esc(String(s.mode).toUpperCase())}</b><br><span class="subtitle">last: ${esc(s.endpoint || '—')} · ${s.latencyMs ? s.latencyMs.toFixed(0) + ' ms' : '—'} · ${esc(s.time || '')}</span>` +
      (s.error ? `<div class="subtitle" style="color:var(--warn)">⚠ ${esc(s.error.slice(0, 200))}</div>` : '');
  };
  draw(api.lastStatus); api.onStatus(draw);
  return el;
}

function renderTopbar() {
  const tb = clear(document.getElementById('topbar'));
  const {id} = currentRoute();
  const p = PAGES.find(x => x.id === id);
  tb.append(h('div', {class: 'row'}, h('span', {style: {fontSize: '1.3rem'}}, p.icon), h('div', {}, h('b', {}, p.label), h('div', {class: 'subtitle'}, p.desc))),
    h('div', {class: 'row'}, h('span', {class: 'chip'}, `Plant ${S.get('plantId')}`), h('span', {class: 'chip'}, `${cfg.APP_ENV || 'development'}`),
      h('span', {class: 'chip', id: 'clock'}, new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC')));
}

function scheduleRefresh() {
  clearInterval(refreshTimer);
  if (S.get('autoRefresh')) refreshTimer = setInterval(() => { const {id} = currentRoute();
    if (['overview', 'live', 'advisory', 'mpc'].includes(id)) { api.clearCache(); route(); } }, S.get('refreshS') * 1000);
}

export async function route() {
  const seq = ++renderSeq;
  applyTheme();
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  renderTopbar();
  await renderSidebar();
  if (seq !== renderSeq) return;
  const view = clear(document.getElementById('view'));
  view.append(loading('Loading page…'));
  const {id, params} = currentRoute();
  try {
    const mod = await pageModules[id]();
    const root = h('div', {});
    const ctx = {plantId: S.get('plantId'), params, go, isCurrent: () => seq === renderSeq};
    const out = await mod.render(root, ctx);
    if (seq !== renderSeq) { if (typeof out === 'function') out(); return; }
    clear(view).append(root);
    cleanup = typeof out === 'function' ? out : null;
  } catch (e) {
    console.error(e);
    clear(view).append(note(`<b>${esc(e.status ? `Backend error (${e.status})` : 'Error')}:</b> ${esc(e.message)}` +
      (e.detail ? `<pre>${esc(JSON.stringify(e.detail, null, 1)).slice(0, 1500)}</pre>` : ''), 'err'));
  }
}

async function sha256(t) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)); return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join(''); }
function authGate() {
  if ((cfg.AUTH_MODE || 'none') !== 'password' || !cfg.APP_PASSWORD_SHA256 || sessionStorage.getItem('obdt-auth') === '1') return Promise.resolve();
  return new Promise(resolve => {
    const pw = h('input', {type: 'password', placeholder: 'Access password'});
    const box = h('div', {class: 'modal-bg'}, h('div', {class: 'modal'}, h('h3', {}, '🔒 Industry-X Ore Beneficiation Twin — sign in'), pw,
      h('div', {class: 'row mt'}, button('Sign in', async () => {
        if ((await sha256(pw.value)) === cfg.APP_PASSWORD_SHA256.toLowerCase()) { sessionStorage.setItem('obdt-auth', '1'); box.remove(); resolve(); }
        else toast('Incorrect password', 'err'); }, 'primary'))));
    pw.addEventListener('keydown', e => { if (e.key === 'Enter') box.querySelector('button').click(); });
    document.getElementById('modal-root').append(box);
  });
}

window.addEventListener('hashchange', route);
setInterval(() => { const c = document.getElementById('clock'); if (c) c.textContent = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC'; }, 30000);
authGate().then(() => { route(); scheduleRefresh(); });
