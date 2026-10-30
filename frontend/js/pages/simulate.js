// Simulation / what-if: edit ore, equipment and set-points, run the twin, compare scenarios.
import * as api from '../api/client.js';
import * as S from '../state.js';
import {KPI_LABEL} from '../utils/constants.js';
import {chart, liberationChart, psdChart, responseChart, sankeyChart, tornadoChart} from '../charts/plots.js';
import {deltaGrid, pageHeader} from '../ui/components.js';
import {button, download, expander, grid, h, note, numberInput, select, table, tabs, toCSV, toast} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {constraintTable, kpiCardsFromDict, sectionCard, streamTable} from './common.js';

const GROUPS = ['ore', 'operating', 'flowsheet', 'economics'];
const SHOW = ['lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct', 'pellet_fines_fe_pct', 'lump_tph',
  'fines_tph', 'mass_yield_pct', 'fe_recovery_pct', 'tailings_fe_pct', 'energy_kwh_t',
  'fresh_water_m3_t', 'margin_usd_h'];

function fieldsFor(schema, defaults, overrides, onchange) {
  const props = schema.properties || {};
  const wrap = h('div', {class: 'form-grid'});
  for (const [key, spec] of Object.entries(props)) {
    if (spec.type === 'object' || spec.$ref || (spec.allOf && !spec.enum)) continue;   // nested equipment handled separately
    const cur = overrides[key] ?? defaults[key];
    if (typeof cur === 'boolean') {
      const el = select([{value: 'true', label: 'yes'}, {value: 'false', label: 'no'}], String(cur),
        {onchange: v => onchange(key, v === 'true')});
      wrap.append(h('div', {class: 'field'}, h('label', {}, humanise(key)), el));
      continue;
    }
    if (spec.enum || (spec.anyOf && spec.anyOf.some(a => a.enum))) {
      const opts = spec.enum || spec.anyOf.find(a => a.enum).enum;
      wrap.append(h('div', {class: 'field'}, h('label', {}, humanise(key)),
        select(opts, cur, {onchange: v => onchange(key, v)})));
      continue;
    }
    if (typeof cur !== 'number') continue;
    const el = numberInput(cur, {min: spec.minimum, max: spec.maximum,
      step: spec.type === 'integer' ? 1 : undefined, onchange: v => onchange(key, v)});
    wrap.append(h('div', {class: 'field'}, h('label', {}, humanise(key)), el,
      h('div', {class: 'hint'}, `${spec.description || ''}${spec.minimum !== undefined ? ` [${spec.minimum} – ${spec.maximum}]` : ''}`)));
  }
  return wrap;
}

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const cfg = await api.get('config_schema', {plant_id: pid});
  const overrides = {ore: {}, operating: {}, flowsheet: {}, economics: {}};
  const out = h('div', {});
  const canEdit = S.can('canEditConfig');
  root.append(pageHeader('Simulation / what-if', {subtitle: 'Every twin input is editable — ore, equipment, ' +
    'set-points and prices; results carry all streams, constraints and economics'}));
  if (!canEdit) root.append(note('Your persona can run cases but not save configuration changes.', 'warn'));

  const forms = tabs(GROUPS.map(g => ({label: {ore: '⛰️ Ore', operating: '🎚️ Set-points', flowsheet: '🏗️ Equipment',
    economics: '💵 Economics'}[g],
  render: pane => pane.append(fieldsFor(cfg[g], cfg.current[g], overrides[g], (k, v) => { overrides[g][k] = v; }))})), 'sim-forms');
  root.append(sectionCard('Inputs', forms, h('div', {class: 'row mt'},
    button('▶ Run simulation', () => run(), 'primary'),
    button('↺ Reset inputs', () => { GROUPS.forEach(g => { overrides[g] = {}; }); ctx.go('simulate'); }),
    button('💾 Save as scenario', () => {
      const name = prompt('Scenario name', `Case ${(S.get('scenarios') || []).length + 1}`);
      if (!name) return;
      S.set('scenarios', [...(S.get('scenarios') || []), {name, overrides: JSON.parse(JSON.stringify(overrides))}]);
      toast(`Scenario "${name}" saved`, 'ok');
    }))));
  root.append(out);

  async function run() {
    out.innerHTML = '';
    out.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Solving the flowsheet…'));
    const body = {plant_id: pid, include_streams: true};
    for (const g of GROUPS) if (Object.keys(overrides[g]).length) body[g] = overrides[g];
    const base = await api.post('simulate', {plant_id: pid, include_streams: false});
    const res = await api.post('simulate', body);
    S.set('lastSimulation', {overrides, kpis: res.kpis});
    const deltas = Object.fromEntries(Object.keys(res.kpis).filter(k => typeof res.kpis[k] === 'number')
      .map(k => [k, res.kpis[k] - (base.kpis[k] ?? res.kpis[k])]));
    out.innerHTML = '';
    out.append(kpiCardsFromDict(res.kpis, SHOW.slice(0, 8), {baseline: base.kpis, source: 'simulated'}));
    out.append(sectionCard('Change against the current operating point',
      deltaGrid(res.kpis, deltas, SHOW, KPI_LABEL, 4)));
    if (res.warnings && res.warnings.length) out.append(note(res.warnings.join('<br>'), 'warn'));
    out.append(tabs([
      {label: '📋 KPIs', render: p => p.append(table(Object.entries(res.kpis).map(([k, v]) =>
        ({Metric: (KPI_LABEL[k] || [humanise(k)])[0], Key: k, Value: v, Δ: deltas[k]})),
      ['Metric', 'Key', {key: 'Value', num: true, fmt: '.4g'}, {key: 'Δ', num: true, fmt: '+.4g'}], {height: 480}))},
      {label: '🔬 Streams', render: p => {
        p.append(streamTable(res.streams));
        const sel = {};
        for (const k of ['S01_rom', 'S06_lumps', 'S08_lump_ore', 'S14_spiral_cyclone_uf', 'S19_ore_fines'])
          if (res.streams[k]) sel[k.replace(/^S\d+_/, '').replace(/_/g, ' ')] = res.streams[k];
        p.append(grid(2, chart(psdChart(sel)), chart(liberationChart(sel))));
        p.append(h('div', {class: 'row'}, button('⤓ CSV', () => download('streams.csv',
          toCSV(Object.entries(res.streams).map(([n, s]) => ({stream: n, ...s, psd: undefined, liberation_spectrum: undefined}))), 'text/csv'))));
      }},
      {label: '⚙️ Units', render: p => p.append(tabs(Object.entries(res.units).map(([id, info]) => ({label: humanise(id),
        render: q => q.append(table(Object.entries(info).map(([k, v]) => ({Parameter: humanise(k), Value: v})),
          ['Parameter', {key: 'Value', num: true, fmt: '.4g'}]))})), 'sim-units'))},
      {label: '⚠️ Constraints', render: p => {
        p.append(note(`Constraint penalty: <b>${fmt(res.constraint_penalty, '.2f')}</b> — ` +
          `${res.constraints.filter(c => c.violated).length} violation(s).`,
        res.constraints.some(c => c.violated) ? 'err' : 'ok'));
        p.append(constraintTable(res.constraints));
      }},
      {label: '🔀 Mass flow', render: p => p.append(chart(sankeyChart(res.sankey)))},
    ], 'sim-out'));
  }

  root.append(sectionCard('Studies', tabs([
    {label: '📉 Sensitivity', render: pane => {
      const groupSel = select(GROUPS, 'operating');
      const varSel = select(Object.keys(cfg.current.operating), 'lump_jig_cut_sg');
      const lo = numberInput(3.4), hi = numberInput(4.8), n = numberInput(9, {min: 3, max: 25, step: 1});
      const res = h('div', {});
      groupSel.addEventListener('change', () => {
        const opts = Object.keys(cfg.current[groupSel.value]).filter(k => typeof cfg.current[groupSel.value][k] === 'number');
        varSel.innerHTML = '';
        opts.forEach(o => varSel.append(h('option', {value: o}, o)));
      });
      pane.append(h('div', {class: 'row'}, h('label', {}, 'Group'), groupSel, h('label', {}, 'Variable'), varSel,
        h('label', {}, 'From'), lo, h('label', {}, 'To'), hi, h('label', {}, 'Points'), n,
        button('▶ Sweep', async () => {
          res.innerHTML = 'Running…';
          const values = Array.from({length: n.getValue()}, (_, i) => lo.getValue() + (hi.getValue() - lo.getValue()) * i / (n.getValue() - 1));
          const s = await api.post('sensitivity', {plant_id: pid, group: groupSel.value, variable: varSel.value, values,
            kpis: ['lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct', 'fe_recovery_pct', 'mass_yield_pct',
              'margin_usd_h']});
          res.innerHTML = '';
          res.append(chart(responseChart(s.rows, 'value', ['lump_fe_pct', 'lump_al2o3_pct'],
            {value: `${s.variable}`, ...KPI_LABEL_FLAT}, `Response to ${s.variable}`)));
          res.append(chart(responseChart(s.rows, 'value', ['fe_recovery_pct', 'margin_usd_h'],
            {value: `${s.variable}`, ...KPI_LABEL_FLAT}, `Recovery and margin against ${s.variable}`)));
          res.append(table(s.rows, ['value', 'lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct', 'fe_recovery_pct',
            'mass_yield_pct', 'margin_usd_h'].map(k => ({key: k, num: true, fmt: '.4g'}))));
        }, 'primary')), res);
    }},
    {label: '🌪️ Tornado', render: async pane => {
      const t = await api.get('tornado', {plant_id: pid, kpi: 'margin_usd_h'});
      pane.append(chart(tornadoChart(t.rows, t.base, 'margin (USD/h)')));
      pane.append(table(t.rows.map(r => ({Group: r.group, Variable: r.variable, '−8 %': r.low, '+8 %': r.high, Span: r.span})),
        ['Group', 'Variable', {key: '−8 %', num: true, fmt: ',.0f'}, {key: '+8 %', num: true, fmt: ',.0f'},
          {key: 'Span', num: true, fmt: ',.0f'}], {height: 400}));
    }},
    {label: '🆚 Scenarios', render: async pane => {
      const scenarios = S.get('scenarios') || [];
      if (!scenarios.length) { pane.append(note('Save scenarios from the inputs panel to compare them here.')); return; }
      const r = await api.post('compare', {plant_id: pid, scenarios});
      pane.append(table(r.scenarios.map(s => ({Scenario: s.name, ...Object.fromEntries(SHOW.map(k => [(KPI_LABEL[k] || [k])[0], s.kpis[k]])),
        Penalty: s.constraint_penalty, Violations: (s.violations || []).join(', ') || '—'})), null, {height: 420}));
      pane.append(button('🗑 Clear scenarios', () => { S.set('scenarios', []); ctx.go('simulate'); }));
    }},
  ], 'sim-studies')));
}
const KPI_LABEL_FLAT = Object.fromEntries(Object.entries(KPI_LABEL).map(([k, v]) => [k, `${v[0]} (${v[1]})`]));
