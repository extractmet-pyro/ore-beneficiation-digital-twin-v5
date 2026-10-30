// Diagnostics: mass balances, data reconciliation, instrument residuals and the scripted event catalogue.
import * as api from '../api/client.js';
import {STATUS_COLOR} from '../utils/constants.js';
import {chart, reconciliationChart, residualChart} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {grid, h, note, numberInput, table, tabs} from '../ui/dom.js';
import {fmt} from '../utils/format.js';
import {sectionCard} from './common.js';

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const [bal, rec] = await Promise.all([api.get('balance', {plant_id: pid}), api.get('reconcile', {plant_id: pid})]);
  root.append(pageHeader('Diagnostics', {subtitle: 'Does the twin close, and do the instruments agree with it?'}));
  const closure = c => fmt((bal.rows.find(r => r.component === c) || {}).closure_pct, '.3f');
  root.append(note(`Balance closure: solids ${closure('Solids')} %, iron ${closure('Iron')} %. ` +
    `Reconciliation: raw two-product recovery ${fmt(rec.raw_recovery_pct, '.2f')} % → reconciled ` +
    `${fmt(rec.reconciled_recovery_pct, '.2f')} % (${rec.gross_error ? 'gross error suspected' : 'no gross error'}).`,
  rec.gross_error ? 'warn' : 'ok'));

  root.append(tabs([
    {label: '⚖️ Balances', render: pane => {
      pane.append(table(bal.rows.map(r => ({Component: r.component, In: r.in_tph ?? r.in_m3_h,
        Out: r.out_tph ?? r.out_m3_h, 'Error': r.error_tph ?? r.error_m3_h, 'Closure %': r.closure_pct})),
      ['Component', {key: 'In', num: true, fmt: ',.2f'}, {key: 'Out', num: true, fmt: ',.2f'},
        {key: 'Error', num: true, fmt: '+.4g'}, {key: 'Closure %', num: true, fmt: '.3f'}]));
      pane.append(sectionCard('Node-by-node check', table(bal.node_check.map(n => ({Node: n.node, 'In t/h': n.in_tph,
        'Out t/h': n.out_tph, 'Solids closure %': n.solids_closure_pct, 'Fe closure %': n.fe_closure_pct})),
      ['Node', {key: 'In t/h', num: true, fmt: ',.1f'}, {key: 'Out t/h', num: true, fmt: ',.1f'},
        {key: 'Solids closure %', num: true, fmt: '.3f'}, {key: 'Fe closure %', num: true, fmt: '.3f'}],
      {height: 420})));
      pane.append(note(bal.note));
    }},
    {label: '🧮 Reconciliation', render: pane => {
      pane.append(chart(reconciliationChart(rec.variables)));
      pane.append(table(rec.variables.map(v => ({Variable: v.variable, Measured: v.measured, Reconciled: v.reconciled,
        Adjustment: v.adjustment, 'Adjustment (σ)': v.adjustment_sigma, Suspect: v.suspect ? 'yes' : '—'})),
      ['Variable', {key: 'Measured', num: true, fmt: '.4g'}, {key: 'Reconciled', num: true, fmt: '.4g'},
        {key: 'Adjustment', num: true, fmt: '+.4g'}, {key: 'Adjustment (σ)', num: true, fmt: '+.2f'}, 'Suspect']));
      pane.append(note(`Method: ${rec.method} Adjustments larger than two standard deviations are flagged as suspect ` +
        'and point at an instrument rather than at the process.'));
    }},
    {label: '📡 Residuals', render: async pane => {
      const hrs = numberInput(48, {min: 8, max: 168, step: 8});
      const box = h('div', {});
      const draw = async () => {
        box.innerHTML = 'Loading…';
        const r = await api.get('residuals', {plant_id: pid, hours: hrs.getValue(), step_h: 1});
        box.innerHTML = '';
        box.append(chart(residualChart(r.hours, r.residual_pct, Object.keys(r.residual_pct).slice(0, 8))));
        box.append(table(r.summary.map(t => ({Tag: t.tag, 'Mean residual %': t.mean_pct, 'σ %': t.std_pct,
          'Max |residual| %': t.max_abs_pct, Status: t.status})),
        ['Tag', {key: 'Mean residual %', num: true, fmt: '+.2f'}, {key: 'σ %', num: true, fmt: '.2f'},
          {key: 'Max |residual| %', num: true, fmt: '.2f'},
          {key: 'Status', render: v => h('span', {class: 'badge', style: {background: STATUS_COLOR[v] || '#78909c'}}, v)}],
        {height: 380}));
        if (r.events && r.events.length) box.append(note(`Scripted events inside this window: ` +
          r.events.map(e => `${e.label} (h ${e.start_h}–${e.end_h})`).join(', ')));
      };
      hrs.addEventListener('change', draw);
      pane.append(h('div', {class: 'row'}, h('label', {}, 'Window (h)'), hrs), box);
      await draw();
    }},
    {label: '📅 Events', render: async pane => {
      const ev = await api.get('events');
      pane.append(note('The demo historian replays a 168-hour week containing the scripted upsets below. ' +
        'Use them to exercise the detection, diagnosis and control layers.'));
      pane.append(table(ev.events.map(e => ({Event: e.label, Type: e.type, Unit: e.unit_id, 'Start (h)': e.start_h,
        'End (h)': e.end_h, Severity: e.severity, Signature: e.signature})),
      ['Event', 'Type', 'Unit', {key: 'Start (h)', num: true, fmt: '.0f'}, {key: 'End (h)', num: true, fmt: '.0f'},
        'Severity', 'Signature'], {height: 420}));
    }},
  ], 'health'));
}
