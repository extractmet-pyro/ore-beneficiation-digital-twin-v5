// Model predictive control: identification, move plan, predicted trajectories, closed-loop study, DCS hand-over.
import * as api from '../api/client.js';
import * as S from '../state.js';
import {chart, closedLoopChart, gainHeatmap, moveChart, mpcTrajectoryChart, mvTrajectoryChart,
  stepResponseChart} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {button, confirmDialog, download, expander, grid, h, note, numberInput, select, table, tabs, toast,
  toggle} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {sectionCard} from './common.js';

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const [cfg, ident] = await Promise.all([api.get('mpc_config'), api.get('mpc_identification', {plant_id: pid})]);
  root.append(pageHeader('Model predictive control', {subtitle: cfg.formulation}));
  root.append(note(`Identified around the current operating point in ${fmt(ident.identified_s, '.1f')} s ` +
    `(${ident.mv_keys.length} MVs × ${ident.cv_keys.length} CVs, condition number ${fmt(ident.condition_number, '.0f')}). ` +
    ident.note));

  const targets = {};
  const tuning = {horizon: 24, control_horizon: 4, dt_min: 5.0, slack_weight: 2500};
  const solveOut = h('div', {});

  root.append(tabs([
    {label: '🎛️ Controller', render: async pane => {
      const tgtFields = h('div', {class: 'form-grid'});
      for (const cv of cfg.cvs) {
        const el = numberInput(cv.target, {step: 'any', onchange: v => { targets[cv.key] = v; }});
        tgtFields.append(h('div', {class: 'field'}, h('label', {}, `${cv.label} (${cv.unit})`), el,
          h('div', {class: 'hint'}, `zone ${cv.lo} – ${cv.hi} · weight ${cv.weight} · priority ${cv.priority}`)));
      }
      const hz = numberInput(tuning.horizon, {min: 6, max: 60, step: 1, onchange: v => { tuning.horizon = v; }});
      const ch = numberInput(tuning.control_horizon, {min: 1, max: 10, step: 1, onchange: v => { tuning.control_horizon = v; }});
      const dt = numberInput(tuning.dt_min, {min: 1, max: 30, step: 1, onchange: v => { tuning.dt_min = v; }});
      const sw = numberInput(tuning.slack_weight, {min: 100, max: 20000, step: 100, onchange: v => { tuning.slack_weight = v; }});
      pane.append(sectionCard('Targets', tgtFields));
      pane.append(sectionCard('Tuning', h('div', {class: 'row'}, h('label', {}, 'Prediction horizon (steps)'), hz,
        h('label', {}, 'Control horizon'), ch, h('label', {}, 'Interval (min)'), dt, h('label', {}, 'Slack weight'), sw,
        button('▶ Solve MPC', () => solve(), 'primary'))));
      pane.append(sectionCard('Manipulated variables', table(cfg.mvs.map(m => ({Variable: m.label, Key: m.key,
        Unit: m.unit, Low: m.lo, High: m.hi, 'Max move / cycle': m.max_move, 'Move cost': m.cost, Area: m.area})),
      ['Variable', 'Key', 'Unit', {key: 'Low', num: true, fmt: '.4g'}, {key: 'High', num: true, fmt: '.4g'},
        {key: 'Max move / cycle', num: true, fmt: '.4g'}, {key: 'Move cost', num: true, fmt: '.2f'}, 'Area'])));
      pane.append(solveOut);
    }},
    {label: '🧮 Model', render: async pane => {
      pane.append(chart(gainHeatmap(ident.gain_matrix, ident.mv_keys, ident.cv_keys)));
      const cvSel = select(ident.cv_keys, 'lump_al2o3_pct');
      const stepBox = h('div', {});
      const drawStep = async () => {
        stepBox.innerHTML = 'Loading…';
        const sr = await api.get('mpc_step', {plant_id: pid, cv: cvSel.value, horizon_min: 120});
        stepBox.innerHTML = '';
        stepBox.append(chart(stepResponseChart(sr.models, sr.cv)));
        stepBox.append(table(Object.entries(sr.models).map(([mv, m]) => ({MV: mv, Gain: m.gain,
          'τ (min)': m.tau_min, 'Dead time (min)': m.dead_time_min})),
        ['MV', {key: 'Gain', num: true, fmt: '.5g'}, {key: 'τ (min)', num: true, fmt: '.1f'},
          {key: 'Dead time (min)', num: true, fmt: '.1f'}]));
      };
      cvSel.addEventListener('change', drawStep);
      pane.append(sectionCard('Step responses', h('div', {class: 'row'}, h('label', {}, 'Controlled variable'), cvSel), stepBox));
      await drawStep();
      pane.append(expander('Full FOPDT model matrix', table(Object.values(ident.models).map(m => ({CV: m.cv, MV: m.mv,
        Gain: m.gain, 'τ (min)': m.tau_min, 'Dead time (min)': m.dead_time_min, Units: m.units})),
      ['CV', 'MV', {key: 'Gain', num: true, fmt: '.5g'}, {key: 'τ (min)', num: true, fmt: '.1f'},
        {key: 'Dead time (min)', num: true, fmt: '.1f'}, 'Units'], {height: 420})));
    }},
    {label: '🔁 Closed loop', render: pane => {
      const steps = numberInput(48, {min: 12, max: 200, step: 6});
      const dcv = select(ident.cv_keys, 'lump_al2o3_pct');
      const mag = numberInput(0.62, {step: 0.05});
      const noise = numberInput(0.35, {min: 0, max: 3, step: 0.05});
      const box = h('div', {});
      pane.append(sectionCard('Disturbance study', h('div', {class: 'row'}, h('label', {}, 'Steps'), steps,
        h('label', {}, 'Disturbed CV'), dcv, h('label', {}, 'Step size'), mag, h('label', {}, 'Noise (%)'), noise,
        button('▶ Simulate', async () => {
          box.innerHTML = '';
          box.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Running the controller…'));
          const n = steps.getValue();
          const dist = {[dcv.value]: Array.from({length: n}, (_, i) => (i < Math.round(n / 8) ? 0 : mag.getValue()))};
          const r = await api.post('mpc_simulate', {plant_id: pid, steps: n, disturbance: dist, tuning,
            noise_pct: noise.getValue(), compare: true});
          box.innerHTML = '';
          const cl = r.closed_loop;
          box.append(note(`Disturbance: ${dcv.value} ${mag.getValue() > 0 ? '+' : ''}${mag.getValue()} after ` +
            `${Math.round(n / 8)} intervals. Constraint excursions: ${cl.metrics.violations}.`));
          if (r.comparison) box.append(table(Object.entries(r.comparison).map(([k, v]) => ({CV: k,
            'MPC RMSE': v.mpc_rmse, 'Open-loop RMSE': v.open_loop_rmse, 'Improvement %': v.improvement_pct})),
          ['CV', {key: 'MPC RMSE', num: true, fmt: '.4g'}, {key: 'Open-loop RMSE', num: true, fmt: '.4g'},
            {key: 'Improvement %', num: true, fmt: '.1f'}]));
          box.append(sectionCard('Controlled variables', chart(closedLoopChart(cl, ident.cv_keys.slice(0, 4)))));
          box.append(sectionCard('Manipulated variables', chart(mvTrajectoryChart(cl, ident.mv_keys.slice(0, 6)))));
          box.append(sectionCard('Controller effort', table(Object.entries(cl.metrics.mv_travel).map(([k, v]) =>
            ({MV: k, 'Total travel': v})), ['MV', {key: 'Total travel', num: true, fmt: '.4g'}])));
        }, 'primary')), box));
    }},
    {label: '📡 Hand-over', render: async pane => {
      pane.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Solving for the current state…'));
      const sol = await api.post('mpc_solve', {plant_id: pid, mode: 'advisory'});
      pane.innerHTML = '';
      const p = sol.handover;
      pane.append(note(`Payload issued ${p.issued_utc} · valid until ${p.valid_until_utc} · mode <b>${p.mode}</b> · ` +
        `checksum <code>${p.checksum}</code>. The twin verifies each move before it is offered.`));
      pane.append(table(p.setpoints.map(s => ({'DCS tag': s.tag, Variable: s.mv, Current: s.current, 'New set-point': s.value,
        'Δ': s.delta, Unit: s.unit, 'Ramp / min': s.ramp_rate_per_min})),
      ['DCS tag', 'Variable', {key: 'Current', num: true, fmt: '.4g'}, {key: 'New set-point', num: true, fmt: '.4g'},
        {key: 'Δ', num: true, fmt: '+.4g'}, 'Unit', {key: 'Ramp / min', num: true, fmt: '.4g'}]));
      pane.append(h('div', {class: 'row mt'},
        button('⤓ JSON payload', () => download('mpc_handover.json', JSON.stringify(p, null, 2))),
        button('✅ Log hand-over', async () => {
          const ok = await confirmDialog('Hand over to the DCS',
            `<p>${p.setpoints.length} set-points will be logged for implementation in the DCS. The twin is advisory: ` +
            'the control-room operator must confirm each move.</p>',
            {okLabel: 'Log hand-over', requireCheck: 'I confirm the moves are safe for current plant conditions'});
          if (!ok) return;
          S.logAction('mpc_handover', `${p.setpoints.length} set-points, checksum ${p.checksum}`);
          toast('Hand-over logged', 'ok');
        }, 'primary', {disabled: S.can('canAccept') ? null : true})));
      pane.append(sectionCard('Twin verification of the proposed move', table(Object.entries(sol.benefit).map(([k, v]) =>
        ({KPI: humanise(k), 'Δ vs current': v})), ['KPI', {key: 'Δ vs current', num: true, fmt: '+.4g'}]),
      (sol.twin_verification.violations || []).length
        ? note(`Violations after the move: ${sol.twin_verification.violations.join(', ')}`, 'warn')
        : note('No constraint violations after the proposed move.', 'ok')));
    }},
  ], 'mpc'));

  async function solve() {
    solveOut.innerHTML = '';
    solveOut.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Solving the quadratic programme…'));
    const sol = await api.post('mpc_solve', {plant_id: pid, targets, tuning, mode: 'advisory'});
    solveOut.innerHTML = '';
    solveOut.append(note(`Solver: <b>${sol.status}</b> in ${fmt(sol.solve_ms, '.0f')} ms (${sol.iterations} iterations) · ` +
      `objective ${fmt(sol.objective, '.4g')} · horizon ${sol.horizon_min} min, control horizon ${sol.control_horizon_min} min` +
      (sol.constraint_active.length ? ` · soft constraints active on: <b>${sol.constraint_active.join(', ')}</b>` : ''),
    sol.status === 'optimal' ? 'ok' : 'warn'));
    solveOut.append(grid(2, chart(moveChart(sol.moves, sol.u_next, sol.u_now)),
      chart(mpcTrajectoryChart(sol, 'lump_al2o3_pct', sol.dt_min))));
    solveOut.append(sectionCard('Predicted trajectories',
      grid(2, Object.keys(sol.predicted).slice(0, 4).map(cv => chart(mpcTrajectoryChart(sol, cv, sol.dt_min))))));
    solveOut.append(sectionCard('Model bias (measurement − twin)', table(Object.entries(sol.bias).map(([k, v]) =>
      ({CV: k, Measured: sol.measured[k], 'Twin model': sol.model[k], Bias: v})),
    ['CV', {key: 'Measured', num: true, fmt: '.4g'}, {key: 'Twin model', num: true, fmt: '.4g'},
      {key: 'Bias', num: true, fmt: '+.4g'}])));
    solveOut.append(sectionCard('Operator guidance', table((sol.guidance || []).map(g => ({Priority: g.priority,
      Item: g.constraint, Status: g.status, Action: g.action})),
    [{key: 'Priority', num: true}, 'Item', 'Status', 'Action'], {height: 320})));
  }
}
