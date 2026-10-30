// Supervisory optimisation: constrained set-point search, robustness and trade-off curves.
import * as api from '../api/client.js';
import * as S from '../state.js';
import {KPI_LABEL} from '../utils/constants.js';
import {chart, constraintChart, histogram, paretoChart, trend} from '../charts/plots.js';
import {acceptMoves, deltaGrid, pageHeader} from '../ui/components.js';
import {button, download, grid, h, note, numberInput, select, table, tabs, toCSV, toggle} from '../ui/dom.js';
import {fmt, humanise, money} from '../utils/format.js';
import {constraintTable, sectionCard} from './common.js';

const SHOW = ['margin_usd_h', 'fe_recovery_pct', 'lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct',
  'lump_tph', 'mass_yield_pct', 'saleable_tph', 'energy_kwh_t', 'cost_usd_product_t'];

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const cat = await api.get('optimize_catalogue');
  const objectives = cat.objectives, mvs = cat.decision_variables;
  let objective = 'margin';
  const chosen = new Set(['lump_jig_cut_sg', 'lump_jig_hutch_water_m3_h', 'scrubber_speed_pct_critical',
    'scrubber_water_m3_h', 'spiral_conc_splitter', 'spiral_middling_splitter', 'table_conc_cut',
    'whims_field_tesla']);
  const evals = numberInput(200, {min: 40, max: 2000, step: 20});
  const out = h('div', {});
  root.append(pageHeader('Supervisory optimisation', {subtitle: 'Constrained search over the manipulated variables, ' +
    'solved against the first-principles twin'}));
  root.append(sectionCard('Set up',
    h('div', {class: 'row'}, h('label', {}, 'Objective'),
      select(objectives.map(o => ({value: o.key, label: `${o.label} (${o.unit})`})), objective,
        {onchange: v => { objective = v; }}), h('label', {}, 'Evaluations'), evals,
      button('▶ Optimise', () => run(), 'primary')),
    h('div', {class: 'subtitle mt'}, 'Decision variables'),
    grid(3, mvs.map(m => toggle(`${m.label} (${m.unit})`, chosen.has(m.key),
      v => { v ? chosen.add(m.key) : chosen.delete(m.key); })))));
  root.append(out);

  async function run() {
    out.innerHTML = '';
    out.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Searching the feasible set…'));
    const r = await api.post('optimize', {plant_id: pid, objective, mv_keys: [...chosen], max_evals: evals.getValue()});
    S.set('lastOptimization', r);
    out.innerHTML = '';
    out.append(note(`<b>${r.objective.label}</b> — ${r.status} after ${r.evaluations} twin evaluations ` +
      `(${fmt(r.runtime_s, '.1f')} s). Constraint penalty ${fmt(r.constraint_penalty, '.2f')}.`,
    r.constraint_penalty > 0 ? 'warn' : 'ok'));
    out.append(sectionCard('Benefit', deltaGrid(r.optimised_kpis, r.improvement, SHOW, KPI_LABEL, 4)));
    const recs = Object.entries(r.setpoints).map(([k, v]) => {
      const spec = mvs.find(m => m.key === k) || {label: k, unit: ''};
      return {tag: k, label: spec.label, unit: spec.unit, current: r.current[k], first_move: r.current[k] + (v - r.current[k]) * 0.4,
        target: v, impact_margin_usd_h: r.improvement.margin_usd_h, impact_recovery_pct: r.improvement.fe_recovery_pct,
        requires_confirmation: ['rom_feed_tph', 'trommel_aperture_mm', 'secondary_css_mm'].includes(k)};
    });
    out.append(tabs([
      {label: '🎚️ Set-points', render: p => {
        p.append(table(recs.map(x => ({Variable: x.label, Unit: x.unit, Current: x.current, 'First move (40 %)': x.first_move,
          'Optimiser target': x.target, 'Δ': x.target - x.current})),
        ['Variable', 'Unit', {key: 'Current', num: true, fmt: '.4g'}, {key: 'First move (40 %)', num: true, fmt: '.4g'},
          {key: 'Optimiser target', num: true, fmt: '.4g'}, {key: 'Δ', num: true, fmt: '+.4g'}]));
        p.append(acceptMoves(recs));
        p.append(h('div', {class: 'row mt'}, button('⤓ CSV', () => download('setpoints.csv', toCSV(recs), 'text/csv'))));
      }},
      {label: '📈 Convergence', render: p => p.append(chart(trend(r.convergence.map(c => c.eval),
        {Objective: {y: r.convergence.map(c => c.objective), source: 'simulated'},
          Penalty: {y: r.convergence.map(c => c.penalty), source: 'recommended', axis: 'y2'}},
        'Optimiser progress', 320)))},
      {label: '⚠️ Constraints', render: p => { p.append(chart(constraintChart(r.constraints)));
        p.append(constraintTable(r.constraints)); }},
      {label: '🎲 Robustness', render: async p => {
        p.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Sampling ore variability…'));
        const mc = await api.post('monte_carlo', {plant_id: pid, setpoints: r.setpoints, samples: 14, ore_sigma_pct: 4});
        p.innerHTML = '';
        p.append(note(`Feasible in <b>${fmt(mc.feasible_pct, '.0f')} %</b> of ${mc.samples} ore realisations ` +
          `(±${mc.ore_sigma_pct} % on head grade, clay content, liberation and hardness).`, mc.feasible_pct > 80 ? 'ok' : 'warn'));
        p.append(grid(2, chart(histogram(mc.rows.map(x => x.lump_al2o3_pct), 'Lump alumina distribution', '% Al₂O₃')),
          chart(histogram(mc.rows.map(x => x.fe_recovery_pct), 'Fe recovery distribution', '%'))));
        p.append(table(mc.rows, null, {height: 320}));
      }},
      {label: '⚖️ Trade-offs', render: async p => {
        p.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Mapping the frontier…'));
        const pr = await api.post('pareto', {plant_id: pid, x_kpi: 'fe_recovery_pct', y_kpi: 'lump_fe_pct', samples: 48});
        p.innerHTML = '';
        p.append(chart(paretoChart(pr.points, pr.frontier, 'Plant Fe recovery (%)', 'Lump ore Fe grade (%)')));
        p.append(note('The frontier here is a three-product trade-off, not the usual two-product one: ' +
          'tonnes rejected from the lump are recrushed and recovered in the fines circuit at a different ' +
          'grade and a different price, so the best point depends on the price deck of the day.'));
        p.append(table(pr.frontier.map(f => ({'Fe recovery %': f.x, 'Lump % Fe': f.y,
          'Lump % Al₂O₃': f.lump_al2o3_pct, 'Margin USD/h': f.margin_usd_h, ...f.setpoints})), null, {height: 340}));
      }},
    ], 'opt-out'));
  }
}
