// Machine-learning layer: soft sensors, hybrid twin correction, importance, drift and anomalies.
import * as api from '../api/client.js';
import {anomalyChart, chart, driftChart, importanceChart, learningCurveChart, parityChart, pdpChart,
  scanChart} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {button, grid, h, note, numberInput, select, table, tabs, toast} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {sectionCard} from './common.js';

const TARGETS = ['lump_al2o3_pct', 'lump_fe_pct', 'fines_fe_pct', 'fe_recovery_pct', 'margin_usd_h'];

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const status = await api.get('ml_status');
  root.append(pageHeader('Machine-learning layer', {subtitle: status.note}));
  root.append(note(`${status.n_models} trained model(s) · dataset ${status.dataset_n ?? '—'} samples · ` +
    `features: ${status.features.length} · algorithms: ${status.algorithms.join(', ')}`));

  root.append(tabs([
    {label: '🔮 Soft sensors', render: async pane => {
      pane.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Scoring the current state…'));
      const pred = await api.post('ml_predict', {plant_id: pid, targets: TARGETS});
      pane.innerHTML = '';
      pane.append(table(pred.predictions.map(p => ({Target: humanise(p.label), Prediction: p.value,
        'Plant / twin': p.actual, Error: p.error, '95 % interval': `${fmt(p.interval_95[0], '.3f')} – ${fmt(p.interval_95[1], '.3f')}`,
        'R² (hold-out)': p.metrics.r2_test, RMSE: p.metrics.rmse_test, Algorithm: p.algorithm})),
      ['Target', {key: 'Prediction', num: true, fmt: '.4g'}, {key: 'Plant / twin', num: true, fmt: '.4g'},
        {key: 'Error', num: true, fmt: '+.4g'}, '95 % interval', {key: 'R² (hold-out)', num: true, fmt: '.3f'},
        {key: 'RMSE', num: true, fmt: '.4g'}, 'Algorithm']));
      pane.append(grid(2, chart(parityChart(pred.predictions, 'Model vs plant at the current operating point')),
        sectionCard('Feature vector', table(Object.entries(pred.features).map(([k, v]) => ({Feature: humanise(k), Value: v})),
          ['Feature', {key: 'Value', num: true, fmt: '.4g'}], {height: 320}))));
    }},
    {label: '🧬 Hybrid twin', render: async pane => {
      const tsel = select(TARGETS, 'lump_al2o3_pct');
      const box = h('div', {});
      const draw = async () => {
        box.innerHTML = 'Loading…';
        const hy = await api.get('ml_hybrid', {plant_id: pid, target: tsel.value});
        box.innerHTML = '';
        box.append(note(hy.note));
        box.append(table([{Model: 'First-principles twin only', Prediction: hy.twin_only, Error: hy.twin_error},
          {Model: 'Hybrid (twin + learned residual)', Prediction: hy.hybrid.value, Error: hy.hybrid_error}],
        ['Model', {key: 'Prediction', num: true, fmt: '.4g'}, {key: 'Error', num: true, fmt: '+.4g'}]));
        box.append(grid(2, sectionCard('Residual-model quality', table(Object.entries(hy.metrics).map(([k, v]) =>
          ({Metric: humanise(k), Value: v})), ['Metric', {key: 'Value', num: true, fmt: '.4g'}])),
        sectionCard('What the residual model uses', chart(importanceChart(hy.importance, 'Residual drivers')))));
      };
      tsel.addEventListener('change', draw);
      pane.append(h('div', {class: 'row'}, h('label', {}, 'Target'), tsel), box);
      await draw();
    }},
    {label: '🔍 Explainability', render: async pane => {
      const tsel = select(TARGETS, 'lump_al2o3_pct');
      const fsel = select(['lump_jig_cut_sg', 'scrubber_speed_pct_critical', 'scrubber_water_m3_h',
        'spiral_conc_splitter', 'whims_field_tesla', 'fe_head_pct', 'al2o3_head_pct', 'clay_share',
        'liberation_d50_um'], 'lump_jig_cut_sg');
      const box = h('div', {});
      const draw = async () => {
        box.innerHTML = 'Loading…';
        const [imp, lc, pdp, scan] = await Promise.all([
          api.get('ml_importance', {target: tsel.value}), api.get('ml_learning_curve', {target: tsel.value}),
          api.get('ml_pdp', {target: tsel.value, feature: fsel.value}),
          api.get('ml_scan', {plant_id: pid, target: tsel.value, feature: fsel.value})]);
        box.innerHTML = '';
        box.append(grid(2, chart(importanceChart(imp.importance)), chart(learningCurveChart(lc.curve))));
        box.append(grid(2, chart(pdpChart(pdp)), chart(scanChart(scan.rows, scan.feature, scan.target))));
        box.append(note(`Surrogate error against the twin over this scan: <b>${fmt(scan.rmse_vs_twin, '.4g')}</b>. ` +
          'Where the two curves separate, trust the first-principles twin — the surrogate is extrapolating.'));
      };
      tsel.addEventListener('change', draw);
      fsel.addEventListener('change', draw);
      pane.append(h('div', {class: 'row'}, h('label', {}, 'Target'), tsel, h('label', {}, 'Feature'), fsel), box);
      await draw();
    }},
    {label: '🚨 Anomalies', render: async pane => {
      const hours = numberInput(48, {min: 6, max: 168, step: 6});
      const box = h('div', {});
      const draw = async () => {
        box.innerHTML = 'Loading…';
        const a = await api.get('ml_anomaly', {plant_id: pid, hours: hours.getValue(), step_h: 1});
        box.innerHTML = '';
        box.append(note(`${a.n_flagged} flagged operating point(s) in the window. Detector trained ${a.detector.trained_utc} ` +
          `on ${a.detector.features.length} features; threshold ${fmt(a.detector.threshold, '.3f')}.`,
        a.n_flagged ? 'warn' : 'ok'));
        box.append(chart(anomalyChart(a.rows)));
        if (a.flagged.length) box.append(table(a.flagged.map(r => ({Hour: r.hour, Score: r.anomaly_score,
          Severity: r.severity, Mahalanobis: r.mahalanobis, 'Top driver': r.drivers[0] && r.drivers[0].feature,
          'z-score': r.drivers[0] && r.drivers[0].z_score, Events: (r.events || []).join(', ') || '—'})),
        [{key: 'Hour', num: true, fmt: '.1f'}, {key: 'Score', num: true, fmt: '.3f'}, 'Severity',
          {key: 'Mahalanobis', num: true, fmt: '.1f'}, 'Top driver', {key: 'z-score', num: true, fmt: '.2f'}, 'Events'],
        {height: 320}));
      };
      hours.addEventListener('change', draw);
      pane.append(h('div', {class: 'row'}, h('label', {}, 'Window (h)'), hours), box);
      await draw();
    }},
    {label: '📉 Drift', render: async pane => {
      const d = await api.get('ml_drift', {plant_id: pid});
      pane.append(note(`Plant drift between replay hours ${d.windows.reference_h.join('–')} and ` +
        `${d.windows.current_h.join('–')}: <b>${d.overall}</b> (${d.n_drifted} drifted feature(s)). ` +
        `Design-space check: ${d.design_space.overall} — ${d.design_space.note}`,
      d.n_drifted ? 'warn' : 'ok'));
      pane.append(chart(driftChart(d.features)));
      pane.append(table(d.features.map(f => ({Feature: humanise(f.feature), PSI: f.psi, Status: f.status,
        'Reference mean': f.reference_mean, 'Current mean': f.current_mean, 'Shift %': f.shift_pct})),
      ['Feature', {key: 'PSI', num: true, fmt: '.4f'}, 'Status', {key: 'Reference mean', num: true, fmt: '.4g'},
        {key: 'Current mean', num: true, fmt: '.4g'}, {key: 'Shift %', num: true, fmt: '+.2f'}], {height: 380}));
    }},
    {label: '🗂️ Registry', render: async pane => {
      const models = await api.get('ml_models');
      pane.append(table(models.models.map(m => ({Model: m.key, Target: humanise(m.target), Algorithm: m.algorithm,
        Hybrid: m.hybrid ? 'yes' : '—', 'R² test': m.metrics.r2_test, 'CV R²': m.metrics.cv_r2_mean,
        RMSE: m.metrics.rmse_test, MAE: m.metrics.mae_test, 'σ residual': m.residual_sigma,
        Train: m.n_train, Test: m.n_test, Version: m.version, Trained: m.trained_utc})),
      ['Model', 'Target', 'Algorithm', 'Hybrid', {key: 'R² test', num: true, fmt: '.3f'},
        {key: 'CV R²', num: true, fmt: '.3f'}, {key: 'RMSE', num: true, fmt: '.4g'}, {key: 'MAE', num: true, fmt: '.4g'},
        {key: 'σ residual', num: true, fmt: '.4g'}, {key: 'Train', num: true}, {key: 'Test', num: true}, 'Version', 'Trained'],
      {height: 360}));
      const alg = select(status.algorithms, 'gradient_boosting');
      const n = numberInput(260, {min: 80, max: 1200, step: 20});
      pane.append(sectionCard('Retrain', h('div', {class: 'row'}, h('label', {}, 'Algorithm'), alg,
        h('label', {}, 'Twin samples'), n, button('🔄 Retrain models', async () => {
          toast('Retraining — this rebuilds the dataset from the twin…');
          const r = await api.post('ml_retrain', {algorithm: alg.value, n_samples: n.getValue(), targets: TARGETS});
          toast(`Retrained ${r.trained.length} model(s) on ${r.n_samples} samples`, 'ok');
          ctx.go('ml');
        }, 'primary'))));
      pane.append(sectionCard('Training history', table(status.history.map(hh => ({Model: hh.key, Version: hh.version,
        'R² test': hh.metrics.r2_test, 'CV R²': hh.metrics.cv_r2_mean, Trained: hh.trained_utc})),
      ['Model', 'Version', {key: 'R² test', num: true, fmt: '.3f'}, {key: 'CV R²', num: true, fmt: '.3f'}, 'Trained'])));
    }},
  ], 'ml'));
}
