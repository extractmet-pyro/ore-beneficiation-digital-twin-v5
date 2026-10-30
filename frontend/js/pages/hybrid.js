// Hybrid model — mechanistic and data driven, and the evidence that the pair is safe.
//
// The question a client actually asks is not "do you use machine learning" but "what happens
// when the machine learning is wrong". This page answers that: where each number comes from,
// whether the current operating point is inside the learned domain, and what the different
// compositions do when it is not.
import * as api from '../api/client.js';
import {attributionChart, chart, compositionErrorChart, extrapolationChart,
  importanceChart} from '../charts/plots.js';
import {metric, pageHeader} from '../ui/components.js';
import {grid, h, kvTable, note, select, table, tabs} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {sectionCard} from './common.js';

const TARGETS = ['lump_al2o3_pct', 'lump_fe_pct', 'fines_fe_pct', 'fe_recovery_pct'];

export async function render(root, ctx) {
  const pid = ctx.plantId;
  let target = 'lump_al2o3_pct';

  root.append(pageHeader('Hybrid model', {
    subtitle: 'First-principles physics with a learned correction, gated on the domain of validity'}));
  root.append(note(
    'The twin is mechanistic <b>and</b> data driven, composed rather than blended. The physics ' +
    'sets the shape of every response and can be asked about an operating point the plant has ' +
    'never run. The learned part corrects the site-specific error the physics does not contain. ' +
    'The correction is bounded in size and tapered to zero outside the data it was trained on, ' +
    'so the worst case is that the twin falls back to being purely mechanistic — never that it ' +
    'invents an answer.'));

  const host = h('div', {});
  const sel = select(TARGETS, target, {format: humanise,
    onchange: async v => { target = v; await draw(); }});
  root.append(h('div', {class: 'toolbar'}, h('label', {}, 'Target variable', sel)), host);

  async function draw() {
    host.replaceChildren(h('div', {class: 'loading'}, 'Loading hybrid model…'));
    const [cfg, attr, dom, cmp, ext] = await Promise.all([
      api.get('hyb_config', {target}),
      api.get('hyb_attribution', {plant_id: pid, target}),
      api.get('hyb_domain', {plant_id: pid, target}),
      api.get('hyb_compare', {target}),
      api.get('hyb_extrapolation', {target}),
    ]);
    host.replaceChildren(tabs([
      {label: '🧬 Architecture', render: p => archTab(p, cfg)},
      {label: '⚖️ Where the number comes from', render: p => attrTab(p, attr)},
      {label: '🎯 Domain of validity', render: p => domainTab(p, dom)},
      {label: '📊 Head to head', render: p => compareTab(p, cmp)},
      {label: '🛡️ Behaviour off-domain', render: p => extTab(p, ext, target)},
    ]));
  }
  await draw();
}

// ---------------------------------------------------------------------------- architecture
function archTab(pane, cfg) {
  pane.append(sectionCard('How the two halves are composed',
    kvTable(cfg.architecture, 'Layer', 'What it is')));

  pane.append(sectionCard('Compositions, and what each one costs you',
    note('These are the recognised ways of pairing a mechanistic model with a learned one. ' +
      `The twin runs <b>${cfg.mode}</b> in service; the others are kept so the choice can be ` +
      'argued rather than asserted.'),
    table(cfg.modes.map(m => ({Composition: m.name, 'In service': m.id === cfg.mode ? '●' : '',
      Summary: m.summary, Strength: m.strength, Weakness: m.weakness})),
    ['Composition', 'In service', 'Summary', 'Strength', 'Weakness'], {height: 340})));

  pane.append(sectionCard('Bounds and gate',
    grid(3,
      metric('Max correction', `${cfg.bounds.max_correction_sigma} σ`),
      metric('Max correction', `${(cfg.bounds.max_correction_frac * 100).toFixed(0)} % of value`),
      metric('Gate cut-off', `${cfg.gate.cutoff}× domain distance`)),
    note(`<b>Guarantee.</b> ${cfg.guarantee}`, 'ok'),
    kvTable(cfg.gate, 'Gate property', 'Value')));

  if (cfg.residual_model) {
    pane.append(sectionCard('The learned part',
      kvTable({Algorithm: cfg.residual_model.algorithm, 'Trained (UTC)': cfg.residual_model.trained_utc,
        'Training rows': cfg.residual_model.n_train, 'Test rows': cfg.residual_model.n_test,
        'Residual σ': cfg.residual_model.residual_sigma,
        'Test R²': cfg.residual_model.metrics.r2_test,
        'Cross-validated R²': cfg.residual_model.metrics.cv_r2_mean,
        Notes: cfg.residual_model.notes}, 'Property', 'Value'),
      cfg.residual_model.importance && cfg.residual_model.importance.length
        ? chart(importanceChart(cfg.residual_model.importance,
          'What the correction actually depends on'))
        : null));
  }

  if (cfg.unmodelled_effect) {
    pane.append(sectionCard('The effect the learned part is there to absorb',
      note('During development the residual model is trained against a documented effect that ' +
        'the physics deliberately does not contain, so the demonstration has something real to ' +
        'find. On a live plant this is replaced by the reconciled historian.'),
      kvTable(cfg.unmodelled_effect, 'Property', 'Value')));
  }
}

// ---------------------------------------------------------------------------- attribution
function attrTab(pane, attr) {
  const inService = attr.rows.find(r => r.mode === attr.in_service_mode) || {};
  pane.append(grid(4,
    metric('In service', humanise(attr.in_service_mode)),
    metric('Prediction', fmt(inService.value, '.4g')),
    metric('Plant measurement', fmt(attr.plant_measurement, '.4g')),
    metric('Domain', attr.domain.verdict,
      null, {deltaText: `confidence ${(attr.domain.confidence * 100).toFixed(0)} %`})));

  pane.append(sectionCard('Mechanistic against learned',
    chart(attributionChart(attr.rows)),
    note('A number an operator cannot decompose is a number an operator will not act on. Every ' +
      'prediction the desk shows carries this split.')));

  pane.append(sectionCard('Every composition at this operating point',
    table(attr.rows.map(r => ({Composition: humanise(r.mode), Value: r.value,
      'Mechanistic %': r.attribution ? r.attribution.mechanistic_pct : null,
      'Learned %': r.attribution ? r.attribution.learned_pct : null,
      Gate: r.gate, 'Error vs plant': r.error, Note: r.note || r.error})),
    ['Composition', {key: 'Value', num: true, fmt: '.4g'},
      {key: 'Mechanistic %', num: true, fmt: '.1f'}, {key: 'Learned %', num: true, fmt: '.1f'},
      {key: 'Gate', num: true, fmt: '.2f'}, {key: 'Error vs plant', num: true, fmt: '+.4f'},
      'Note'], {height: 300})));
}

// ---------------------------------------------------------------------------- domain
function domainTab(pane, dom) {
  const d = dom.domain;
  const kind = d.verdict === 'inside' ? 'ok' : (d.verdict === 'edge' ? 'warn' : 'bad');
  pane.append(note(
    d.verdict === 'inside'
      ? 'The current operating point is inside the data the correction was learned from. The ' +
        'full correction is applied.'
      : d.verdict === 'edge'
        ? `The operating point is at the edge of the learned domain (binding check: ` +
          `<b>${d.binding_check}</b>). The correction is tapered to ` +
          `${(d.confidence * 100).toFixed(0)} % of its value.`
        : 'The operating point is outside the learned domain. The correction is switched off and ' +
          'the twin is answering purely from the physics.', kind));

  pane.append(grid(4,
    metric('Verdict', d.verdict),
    metric('Confidence', `${(d.confidence * 100).toFixed(0)} %`),
    metric('Mahalanobis ratio', fmt(d.mahalanobis_ratio, '.2f')),
    metric('Nearest-neighbour ratio', fmt(d.nearest_neighbour_ratio, '.2f'))));

  pane.append(sectionCard('The three checks',
    note('A point is only as trustworthy as its worst check. The box check asks whether each ' +
      'variable is in range; the Mahalanobis distance asks whether the <i>combination</i> is ' +
      'plausible; the nearest-neighbour distance catches holes inside the range that the first ' +
      'two miss entirely.'),
    kvTable({'In box': d.in_box ? 'yes' : 'no',
      'Box ratio': d.box_ratio, 'Mahalanobis': d.mahalanobis,
      'Mahalanobis ratio (1.0 = 95th percentile of training)': d.mahalanobis_ratio,
      'Nearest-neighbour ratio': d.nearest_neighbour_ratio,
      'Taper begins at': d.thresholds.taper_from, 'Correction off at': d.thresholds.cutoff},
    'Check', 'Value')));

  if (d.features_outside && d.features_outside.length) {
    pane.append(sectionCard('Variables outside the trained range',
      table(d.features_outside.map(f => ({Feature: humanise(f.feature), Value: f.value,
        'Trained from': f.trained_lo, 'Trained to': f.trained_hi,
        'Outside by (% of range)': f.outside_by_pct_of_range})),
      ['Feature', {key: 'Value', num: true, fmt: '.4g'},
        {key: 'Trained from', num: true, fmt: '.4g'}, {key: 'Trained to', num: true, fmt: '.4g'},
        {key: 'Outside by (% of range)', num: true, fmt: '.1f'}])));
  }

  pane.append(sectionCard('Trained envelope',
    table(dom.envelope.map(e => ({Feature: humanise(e.feature), From: e.lo, Mean: e.mean, To: e.hi,
      Current: dom.features[e.feature]})),
    ['Feature', {key: 'From', num: true, fmt: '.4g'}, {key: 'Mean', num: true, fmt: '.4g'},
      {key: 'To', num: true, fmt: '.4g'}, {key: 'Current', num: true, fmt: '.4g'}],
    {height: 420})));
}

// ---------------------------------------------------------------------------- compare
function compareTab(pane, cmp) {
  const r = cmp.results;
  pane.append(grid(4,
    metric('Mechanistic RMSE', fmt(r.mechanistic_only.rmse, '.4f')),
    metric('Hybrid RMSE', fmt(r.gated_residual.rmse, '.4f')),
    metric('Improvement', `${cmp.improvement_vs_mechanistic_pct} %`),
    metric('Best by RMSE', humanise(cmp.best_by_rmse))));

  pane.append(sectionCard('Error on data none of the models were trained on',
    chart(compositionErrorChart(r)),
    table(Object.entries(r).map(([k, v]) => ({Composition: humanise(k), Bias: v.bias, MAE: v.mae,
      RMSE: v.rmse, 'Max |error|': v.max_abs, 'R²': v.r2})),
    ['Composition', {key: 'Bias', num: true, fmt: '+.4f'}, {key: 'MAE', num: true, fmt: '.4f'},
      {key: 'RMSE', num: true, fmt: '.4f'}, {key: 'Max |error|', num: true, fmt: '.4f'},
      {key: 'R²', num: true, fmt: '.4f'}]),
    note(cmp.note)));

  pane.append(sectionCard('Sample of the comparison',
    table(cmp.samples.slice(0, 40).map(s => ({Actual: s.actual, Mechanistic: s.mechanistic,
      Hybrid: s.hybrid, 'Data only': s.data_only, Domain: s.in_domain})),
    [{key: 'Actual', num: true, fmt: '.4f'}, {key: 'Mechanistic', num: true, fmt: '.4f'},
      {key: 'Hybrid', num: true, fmt: '.4f'}, {key: 'Data only', num: true, fmt: '.4f'},
      'Domain'], {height: 320})));
}

// ---------------------------------------------------------------------------- extrapolation
function extTab(pane, ext, target) {
  const c = ext.conclusion;
  pane.append(note(ext.statement, 'ok'));
  pane.append(grid(4,
    metric('Gate at the limit', fmt(c.gate_at_limit, '.2f')),
    metric('Gated hybrid vs physics', c.gated_converges_to_mechanistic ? 'identical' : 'diverges'),
    metric('Ungated departure', fmt(c.ungated_departure, '.4f')),
    metric('Data-only departure', fmt(c.data_only_departure, '.4f'))));

  pane.append(sectionCard('Walking the operating point out of the training data',
    chart(extrapolationChart(ext.rows, humanise(target))),
    note('This is the test that settles the mechanistic-versus-data-driven argument. As the ' +
      'operating point leaves the learned domain the gate closes and the gated hybrid converges ' +
      'exactly onto the mechanistic prediction. The data-only model keeps answering — and has ' +
      'no defined accuracy at all out there.')));

  pane.append(sectionCard('Step by step',
    table(ext.rows.map(r => ({Step: r.step, Distance: r.distance_from_centre, Domain: r.domain,
      Confidence: r.confidence, Mechanistic: r.mechanistic, 'Gated hybrid': r.gated_hybrid,
      'Ungated hybrid': r.ungated_hybrid, 'Data only': r.data_only,
      'Correction applied': r.correction_applied, Clamped: r.clamped ? 'yes' : '—'})),
    [{key: 'Step', num: true}, {key: 'Distance', num: true, fmt: '.2f'}, 'Domain',
      {key: 'Confidence', num: true, fmt: '.2f'}, {key: 'Mechanistic', num: true, fmt: '.4f'},
      {key: 'Gated hybrid', num: true, fmt: '.4f'}, {key: 'Ungated hybrid', num: true, fmt: '.4f'},
      {key: 'Data only', num: true, fmt: '.4f'},
      {key: 'Correction applied', num: true, fmt: '+.4f'}, 'Clamped'], {height: 330})));
}
