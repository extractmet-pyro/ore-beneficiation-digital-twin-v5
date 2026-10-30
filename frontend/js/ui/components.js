// Operator-desk components: header, KPI cards, metrics, alarms, advisories, move acceptance, legends.
import * as S from '../state.js';
import {KPI_FMT, LOWER_IS_BETTER, SOURCE, STATUS_ICON} from '../utils/constants.js';
import {ageStr, esc, fmt, money, toDisplay, tsShort} from '../utils/format.js';
import {button, confirmDialog, grid, h, table, toast} from './dom.js';
import {lastStatus} from '../api/client.js';

export const badge = (text, cls) => h('span', {class: `badge ${cls}`}, text);
export const statusBadge = s => badge(String(s).toUpperCase(), `s-${s}`);

export function pageHeader(title, {subtitle = '', timestamp = null, event = null} = {}) {
  const mode = lastStatus.mode;
  const chip = {live: ['LIVE BACKEND', 'live'], mock: ['MOCK MODE', 'mock'], 'mock-fallback': ['MOCK (backend unreachable)', 'down']}[mode] || ['—', ''];
  return h('div', {class: 'row between mb'},
    h('div', {}, h('div', {class: 'title'}, title), h('div', {class: 'subtitle'}, subtitle)),
    h('div', {class: 'row'}, event ? h('span', {class: 'chip down'}, `EVENT: ${event}`) : null,
      h('span', {class: `chip ${chip[1]}`}, chip[0]), h('span', {class: 'chip'}, S.get('persona')),
      timestamp ? h('span', {class: 'chip', title: timestamp}, `updated ${tsShort(timestamp)} · ${ageStr(timestamp)}`) : null));
}
export function sourceLegend() {
  return h('div', {class: 'legend'}, Object.entries(SOURCE).map(([k, v]) => h('b', {class: `src-${k}`}, `${v.icon} ${v.label}`)));
}

export function kpiCard(k) {
  const sys = S.get('unitSystem');
  const spec = KPI_FMT[k.key] || '.3g';
  const hib = k.higher_is_better ?? !LOWER_IS_BETTER.has(k.key);
  const [v, u] = toDisplay(k.value, k.unit, sys);
  const [t] = toDisplay(k.target, k.unit, sys), [f] = toDisplay(k.forecast, k.unit, sys), [b] = toDisplay(k.baseline, k.unit, sys);
  const src = SOURCE[k.source] || SOURCE.measured;
  const meta = [];
  if (t !== null && t !== undefined) {
    const d = v !== null && v !== undefined ? v - t : null;
    const good = d !== null && ((d >= 0) === hib);
    meta.push(`target ${fmt(t, spec)} <span class="${good ? 'up' : 'dn'}">(${fmt(d, '+' + spec.replace('+', ''))})</span>`);
  }
  if (f !== null && f !== undefined) meta.push(`8 h fcst ${fmt(f, spec)}`);
  if (b !== null && b !== undefined) meta.push(`twin ${fmt(b, spec)}`);
  return h('div', {class: `kpi ${k.status || 'normal'}`, title: k.hint || ''},
    h('div', {class: 'lab'}, h('span', {}, k.label), h('span', {style: {color: src.color}, title: src.label}, src.icon)),
    h('div', {class: 'val'}, fmt(v, spec), h('span', {class: 'unit'}, u)),
    h('div', {class: 'meta', html: meta.join(' · ')}));
}
export const kpiGrid = (kpis, cols = 6) => grid(cols, kpis.map(kpiCard));

export function metric(label, value, delta = null, {inverse = false, deltaText = null} = {}) {
  let dEl = null;
  if (delta !== null && delta !== undefined && Number.isFinite(delta)) {
    const good = inverse ? delta <= 0 : delta >= 0;
    dEl = h('div', {class: `d ${Math.abs(delta) < 1e-12 ? '' : good ? 'up' : 'dn'}`}, deltaText ?? fmt(delta, '+.3g'));
  } else if (deltaText) dEl = h('div', {class: 'd', style: {color: 'var(--sub)'}}, deltaText);
  return h('div', {class: 'metric'}, h('div', {class: 'l'}, label), h('div', {class: 'v'}, value), dEl);
}
export function deltaGrid(kpis, deltas, keys, labels, cols = 6) {
  return grid(cols, keys.map(k => { const [lab, unit] = labels[k] || [k, ''];
    const spec = KPI_FMT[k] || '.3g';
    return metric(`${lab} (${unit})`, fmt(kpis[k], spec), deltas[k], {inverse: LOWER_IS_BETTER.has(k), deltaText: fmt(deltas[k], '+' + spec.replace(',', '').replace('+', ''))}); }));
}

export function alarmPanel(alerts, {max = 12, title = 'Active alarms & alerts'} = {}) {
  const wrap = h('div', {});
  let sev = new Set(['alarm', 'warning']);
  const list = h('div', {});
  const key = a => `${a.key || ''}|${(a.message || '').slice(0, 40)}`;
  function draw() {
    list.innerHTML = '';
    const acked = new Set(S.get('acked') || []);
    const rows = alerts.filter(a => sev.has(a.severity || 'warning')).slice(0, max);
    if (!alerts.length) { list.append(h('div', {class: 'note ok'}, 'No active alarms — all constraints within limits')); return; }
    rows.forEach(a => list.append(h('div', {class: `alarm-row ${a.severity || 'warning'} ${acked.has(key(a)) ? 'acked' : ''}`},
      h('div', {}, STATUS_ICON[a.severity] || '🟠'),
      h('div', {}, h('div', {class: 'msg', html: `<b>[${esc(a.unit_id || 'plant')}]</b> ${esc(a.message || '')}`}),
        h('div', {class: 'hint'}, `${a.hint || ''}${a.source ? ' · source: ' + a.source : ''}${a.since ? ' · since ' + a.since : ''}${acked.has(key(a)) ? ' · ACKNOWLEDGED' : ''}`)))));
  }
  const filt = h('div', {class: 'row'}, ['alarm', 'warning', 'info'].map(s => {
    const cb = h('input', {type: 'checkbox', checked: sev.has(s) || null, onchange: () => { cb.checked ? sev.add(s) : sev.delete(s); draw(); }});
    return h('label', {class: 'switch'}, cb, s); }),
    button('Acknowledge all', () => { S.set('acked', [...new Set([...(S.get('acked') || []), ...alerts.map(key)])].slice(-500)); draw(); }));
  wrap.append(h('h4', {}, `🚨 ${title} (${alerts.length})`), filt, list);
  draw();
  return wrap;
}

export function advisoryCards(items) {
  if (!items || !items.length) return h('div', {class: 'note ok'}, 'No advisories — operating point is within the recommended envelope.');
  return h('div', {}, items.map(a => h('div', {class: `adv ${a.priority || ''}`}, h('b', {}, a.action),
    h('small', {}, `[${a.unit_id}] ${a.reason} · impact: ${a.impact} · confidence ${fmt(a.confidence, '.0%')} · source ${a.value_source || ''}`))));
}

export function recommendationsTable(recs) {
  return table(recs.map(r => ({Tag: r.tag, Variable: r.label, Current: r.current, 'First move': r.first_move, 'SS target': r.target,
    Unit: r.unit, 'Δ margin alone (USD/h)': r.impact_margin_usd_h, 'Δ recovery (pts)': r.impact_recovery_pct,
    'Confirm?': r.requires_confirmation ? 'yes' : '—'})));
}

/** Two-step (select + confirm dialog with acknowledgement) acceptance of recommended first moves. */
export function acceptMoves(recs) {
  if (!recs || !recs.length) return h('div');
  const canAccept = S.can('canAccept');
  const checks = recs.map(r => h('input', {type: 'checkbox', disabled: canAccept ? null : true}));
  const box = h('div', {class: 'card mt'}, h('h4', {}, 'Accept recommended first moves'),
    canAccept ? null : h('div', {class: 'note warn'}, 'Your persona cannot accept setpoint moves.'),
    grid(3, recs.map((r, i) => h('label', {class: 'switch'}, checks[i], `${r.label}: ${fmt(r.current, '.4g')} → ${fmt(r.first_move, '.4g')} ${r.unit}`))),
    h('div', {class: 'mt'}, button('✅ Accept & log selected moves', async () => {
      const chosen = recs.filter((_, i) => checks[i].checked);
      if (!chosen.length) { toast('Select at least one move'); return; }
      const crit = chosen.filter(r => r.requires_confirmation);
      const ok = await confirmDialog('Confirm setpoint moves',
        `<p>You are about to accept <b>${chosen.length}</b> move(s)${crit.length ? `, including critical MVs: <b>${crit.map(r => esc(r.label)).join(', ')}</b>` : ''}.</p>
         <p>The twin is advisory: moves must be implemented and confirmed in the DCS by the control-room operator.</p>
         <ul>${chosen.map(r => `<li>${esc(r.tag)} ${esc(r.label)}: ${fmt(r.current, '.4g')} → <b>${fmt(r.first_move, '.4g')}</b> ${esc(r.unit)} (target ${fmt(r.target, '.4g')})</li>`).join('')}</ul>`,
        {okLabel: 'Accept & log', requireCheck: 'I confirm the moves are safe for current plant conditions'});
      if (!ok) return;
      chosen.forEach(r => S.logAction('accept_move', `${r.tag} ${r.label}: ${fmt(r.current, '.4g')} → ${fmt(r.first_move, '.4g')} (target ${fmt(r.target, '.4g')}, est. ${money(r.impact_margin_usd_h)}/h)`));
      toast(`${chosen.length} move(s) logged to the operator log`, 'ok');
    }, 'primary', {disabled: canAccept ? null : true})));
  return box;
}
