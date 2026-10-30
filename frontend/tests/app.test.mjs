import assert from 'node:assert/strict';
import {after, test} from 'node:test';
import {dom, errors, plots} from './setup.mjs';

const settle = (ms = 60) => new Promise(r => setTimeout(r, ms));
const PAGES = ['home', 'overview', 'live', 'units', 'gravity', 'simulate', 'optimize', 'mpc', 'ml',
  'hybrid', 'plant3d', 'validation', 'advisory', 'health', 'quality', 'admin'];
const PLANTS = ['IX-OB-01', 'IX-OB-02', 'IX-OB-03'];
const doc = dom.window.document;
// the desk keeps UI timers alive (clock, auto-refresh) — end the process once all tests have reported
after(() => setTimeout(() => process.exit(process.exitCode || 0), 100));

test('format helpers', async () => {
  const {fmt, money, humanise} = await import('../js/utils/format.js');
  assert.equal(fmt(1234.5, ',.1f'), '1,234.5');
  assert.equal(fmt(0.123, '.1%'), '12.3%');
  assert.equal(fmt(3, '+.2f', 'pts'), '+3.00 pts');
  assert.equal(fmt(null), '—');
  assert.equal(money(95400), '$95.4 k');
  assert.equal(humanise('lump_jig_hutch_water_m3_h'), 'Lump jig hutch water m³ h');
});

test('mock layer serves every GET endpoint and validates against the schemas', async () => {
  const mock = await import('../js/api/mock.js');
  const {validate} = await import('../js/api/schemas.js');
  const {ENDPOINTS} = await import('../js/api/endpoints.js');
  for (const [name, ep] of Object.entries(ENDPOINTS)) {
    if (ep.method !== 'GET') continue;
    const d = await mock.respond(name, {plant_id: 'IX-OB-02', unit_id: 'lump_jig'},
      {plant_id: 'IX-OB-02', hours: 24, target: 'lump_al2o3_pct', feature: 'lump_jig_cut_sg'});
    assert.deepEqual(ep.schema ? validate(ep.schema, d) : [], [], name);
  }
  const live = await mock.respond('live', {plant_id: 'IX-OB-01'});
  assert.ok(Math.abs(Date.parse(live.timestamp) - Date.now()) < 180e3, 'timestamps shifted to now');
  const base = await mock.respond('simulate', {}, {}, {plant_id: 'IX-OB-01'});
  const tighter = await mock.respond('simulate', {}, {}, {plant_id: 'IX-OB-01',
    operating: {lump_jig_cut_sg: 4.7}});
  assert.ok(tighter.kpis.lump_fe_pct > base.kpis.lump_fe_pct, 'a tighter jig cut lifts the lump grade');
  assert.ok(tighter.kpis.lump_al2o3_pct < base.kpis.lump_al2o3_pct, '... and drops the lump alumina');
});

test('the twin makes three products, each on specification', async () => {
  const mock = await import('../js/api/mock.js');
  for (const pid of PLANTS) {
    const s = await mock.respond('simulate', {}, {}, {plant_id: pid});
    const k = s.kpis;
    assert.ok(k.lump_tph > 0 && k.fines_tph > 0 && k.pellet_fines_tph > 0, `${pid} three products`);
    assert.ok(k.lump_fe_pct > 58 && k.lump_fe_pct < 70, `${pid} lump Fe`);
    assert.ok(k.lump_al2o3_pct < 3.2, `${pid} lump alumina`);
    assert.ok(k.fines_fe_pct > 60, `${pid} fines Fe`);
    assert.ok(k.fe_recovery_pct > 80 && k.fe_recovery_pct <= 100, `${pid} recovery`);
    assert.ok(k.energy_kwh_t < 5, `${pid} energy — this circuit does not grind`);
    const rom = s.streams.S01_rom, lump = s.streams.S08_lump_ore;
    assert.ok(lump.fe_pct > rom.fe_pct, `${pid} the lump jig upgrades`);
    assert.equal(rom.psd.size_um.length, 36);
    assert.equal(rom.liberation_spectrum.length, 15);
  }
});

test('washability and partition payloads carry the gravity physics', async () => {
  const mock = await import('../js/api/mock.js');
  const w = await mock.respond('washability', {plant_id: 'IX-OB-01'});
  assert.ok(w.concentration_criterion > 2.4, 'gravity separation is viable on this ore');
  const rom = w.streams['ROM feed'];
  assert.ok(rom.sg_mid.length === rom.mass_pct.length);
  assert.ok(rom.fe_pct[rom.fe_pct.length - 1] > rom.fe_pct[0], 'denser fractions are richer');
  const jig = await mock.respond('unit', {plant_id: 'IX-OB-01', unit_id: 'lump_jig'});
  const pc = jig.curves.partition_curve;
  assert.ok(pc.length > 10 && pc[0].sg < pc[pc.length - 1].sg);
  assert.ok(pc[0].to_sinks_pct < pc[pc.length - 1].to_sinks_pct, 'heavy particles report to the sinks');
  assert.ok(jig.curves.ep_by_size.length > 10, 'Ep is resolved by particle size');
  const spirals = await mock.respond('unit', {plant_id: 'IX-OB-01', unit_id: 'spirals'});
  assert.ok(spirals.curves.size_window.length > 10, 'the spiral has a working size window');
});

test('flowsheet SVG builds for every plant', async () => {
  const mock = await import('../js/api/mock.js');
  const {buildSVG} = await import('../js/viz/flowsheet.js');
  for (const pid of PLANTS) {
    const fs = await mock.respond('flowsheet', {plant_id: pid});
    const svg = buildSVG(fs, {lump_jig: 'alarm', scrubber: 'caution'}, true);
    assert.ok(svg.startsWith('<svg'), pid);
    for (const label of ['Rotary scrubber', 'Lump jig', 'Screw classifier', 'Spiral concentrators',
      'Shaking tables', 'WHIMS', 'LUMP ORE', 'SINTER FINES', 'PELLET FEED'])
      assert.ok(svg.includes(label), `${pid} missing ${label}`);
    assert.ok(!/&(?!amp;|lt;|gt;|quot;|#)/.test(svg), `${pid} unescaped ampersand`);
  }
});

test('every page renders through the router, every tab opens, no uncaught errors', async () => {
  await import('../js/main.js');
  const S = await import('../js/state.js');
  for (const plant of PLANTS) {
    S.set('plantId', plant);
    S.set('mockOverride', true);
    for (const p of PAGES) {
      dom.window.location.hash = `#/${p}`;
      const {route} = await import('../js/main.js');
      await route();
      await settle(150);
      const view = doc.getElementById('view');
      for (const b of [...view.querySelectorAll('.tabs button')]) { b.click(); await settle(55); }
      await settle(220);
      const errs = [...view.querySelectorAll('.note.err')].map(e => e.textContent)
        .filter(t => !t.includes('3-D scene unavailable'));
      assert.deepEqual(errs, [], `${plant}/${p} errors`);
    }
  }
  assert.ok(plots.length > 120, `charts drawn: ${plots.length}`);
  assert.deepEqual(errors, []);
});

test('simulation, optimisation, MPC and ML flows run from the UI', async () => {
  const {route} = await import('../js/main.js');
  const S = await import('../js/state.js');
  S.set('plantId', 'IX-OB-01');
  const clickText = async (txt, wait = 500) => {
    const b = [...doc.querySelectorAll('#view button')].find(x => x.textContent.includes(txt));
    assert.ok(b, `button "${txt}" not found`);
    b.click();
    await settle(wait);
  };
  dom.window.location.hash = '#/simulate'; await route(); await settle(220);
  await clickText('Run simulation');
  assert.ok(S.get('lastSimulation'), 'simulation stored in state');

  dom.window.location.hash = '#/optimize'; await route(); await settle(220);
  await clickText('Optimise', 700);
  assert.ok(S.get('lastOptimization'), 'optimisation stored in state');
  assert.ok(Object.keys(S.get('lastOptimization').setpoints).length > 0);

  dom.window.location.hash = '#/mpc'; await route(); await settle(260);
  doc.querySelector('#view .tabs button').click(); await settle(260);
  await clickText('Solve MPC', 900);
  assert.ok(doc.getElementById('view').textContent.includes('Predicted trajectories'));

  dom.window.location.hash = '#/gravity'; await route(); await settle(320);
  assert.ok(doc.getElementById('view').textContent.includes('Concentration criterion'));
});

test('MPC payload carries a DCS hand-over and beats open loop on the alumina zone', async () => {
  const mock = await import('../js/api/mock.js');
  const sol = await mock.respond('mpc_solve', {}, {}, {plant_id: 'IX-OB-01'});
  assert.ok(['optimal', 'suboptimal'].includes(sol.status));
  assert.ok(sol.handover.setpoints.every(s => s.tag && s.ramp_rate_per_min !== undefined));
  assert.equal(sol.handover.checksum.length, 16);
  // Compare the loops only where the disturbance actually pushes the plant out of its zone.
  // Where the open loop never leaves the zone there is nothing for the controller to improve,
  // and comparing two near-zero RMSEs grades the arithmetic rather than the controller.
  // Materiality: the lump-alumina assay repeats to about 0.06 %, so a zone excursion smaller
  // than 0.01 % is below anything the plant can measure and is not a control defect.
  const MATERIAL = 0.01;
  let tested = 0;
  for (const pid of PLANTS) {
    const sim = await mock.respond('mpc_simulate', {}, {}, {plant_id: pid});
    const cmp = sim.comparison.lump_al2o3_pct;
    assert.ok(cmp.mpc_rmse <= Math.max(cmp.open_loop_rmse, MATERIAL),
      `${pid}: closed loop must not cause a material zone excursion ` +
      `(${cmp.mpc_rmse} against open loop ${cmp.open_loop_rmse})`);
    if (cmp.open_loop_rmse < MATERIAL) continue;    // the zone was never materially threatened
    tested++;
    assert.ok(cmp.mpc_rmse < cmp.open_loop_rmse,
      `${pid}: closed loop holds the alumina zone better (${cmp.mpc_rmse} vs ${cmp.open_loop_rmse})`);
    assert.ok(cmp.improvement_pct > 20,
      `${pid}: a supervisory controller that only just beats doing nothing is not worth buying`);
  }
  assert.ok(tested > 0, 'at least one reference plant must be driven out of its alumina zone');
});

test('machine-learning payloads expose metrics, drift and anomalies', async () => {
  const mock = await import('../js/api/mock.js');
  const models = await mock.respond('ml_models');
  assert.ok(models.models.length >= 3);
  assert.ok(models.models.every(m => m.metrics.r2_test > 0.2), 'models learn the twin');
  const imp = await mock.respond('ml_importance', {}, {target: 'lump_al2o3_pct'});
  assert.ok(imp.importance.length > 4);
  const an = await mock.respond('ml_anomaly', {plant_id: 'IX-OB-01'});
  assert.ok(an.rows.length > 5 && an.rows.every(r => typeof r.anomaly_score === 'number'));
  const dr = await mock.respond('ml_drift', {plant_id: 'IX-OB-01'});
  assert.ok(dr.features.length > 5 && dr.features.every(f => typeof f.psi === 'number'));
});

/* ===============================================================================================
   v5 — plant 3-D model, hybrid model, validation and acceptance.
   ============================================================================================ */

test('the 3-D plant model is data driven, tagged and bound to the twin', async () => {
  const mock = await import('../js/api/mock.js');
  for (const pid of PLANTS) {
    const m = await mock.respond('p3d_model', {plant_id: pid}, {plant_id: pid});
    const eq = m.nodes.filter(n => n.kind === 'equipment');
    assert.ok(eq.length >= 30, `${pid} equipment count`);
    assert.ok(eq.every(n => n.tag), `${pid} every asset has a plant tag`);
    assert.equal(new Set(eq.map(n => n.tag)).size, eq.length, `${pid} tags unique`);
    assert.ok(m.counts.bound_to_twin >= 15, `${pid} assets bound to twin units`);
    assert.ok(m.routes.length >= 25, `${pid} material routes`);
    // every route must join two nodes that are actually in the scene
    const ids = new Set(m.nodes.map(n => n.node_id));
    for (const r of m.routes) {
      assert.ok(ids.has(r.from_asset) && ids.has(r.to_asset), `${pid} route ${r.route_id}`);
      assert.ok(r.path.length >= 2 && r.path.every(p => p.length === 3), `${pid} route path`);
    }
    // geometry has to be buildable: a primitive the viewer knows and finite dimensions
    for (const n of m.nodes) {
      assert.ok(n.primitive, `${pid} ${n.node_id} primitive`);
      assert.ok(Number.isFinite(n.position.x) && Number.isFinite(n.position.y), `${pid} position`);
      assert.ok(Object.values(n.dims).every(v => typeof v !== 'number' || Number.isFinite(v)),
        `${pid} ${n.node_id} dims`);
    }
    assert.ok(m.bounds.size[0] > 100 && m.bounds.size[1] > 10, `${pid} plant extents`);
    assert.ok(m.levels.length >= 4 && m.bookmarks.length >= 6, `${pid} levels and bookmarks`);
  }
});

test('the 3-D state frame follows the process and every overlay produces values', async () => {
  const mock = await import('../js/api/mock.js');
  for (const ov of ['status', 'duty', 'power', 'throughput', 'fe', 'solids']) {
    const f = await mock.respond('p3d_state', {plant_id: 'IX-OB-01'},
      {plant_id: 'IX-OB-01', overlay: ov});
    assert.equal(f.overlay, ov);
    assert.ok(f.assets.length >= 30, `${ov} assets`);
    assert.ok(f.routes.length >= 25, `${ov} routes`);
    const vals = f.assets.map(a => a.overlay_value).filter(v => typeof v === 'number');
    assert.ok(vals.length > 0, `overlay '${ov}' coloured nothing`);
    assert.ok(f.summary.total_power_kw > 0, `${ov} summary power`);
  }
  const s = await mock.respond('p3d_state', {plant_id: 'IX-OB-01'},
    {plant_id: 'IX-OB-01', overlay: 'status'});
  const scrub = s.assets.find(a => a.asset_id === 'scrubber');
  assert.ok(scrub.throughput_tph > 0 && scrub.power_kw > 0, 'scrubber carries live state');
  assert.ok(['normal', 'caution', 'alarm', 'offline'].includes(scrub.status));
});

test('clash check is clean and the tag manifest is complete', async () => {
  const mock = await import('../js/api/mock.js');
  const c = await mock.respond('p3d_clash', {}, {});
  assert.equal(c.clean, true, `layout clashes: ${JSON.stringify(c.clashes)}`);
  assert.ok(c.pairs_tested > 300);
  const g = await mock.respond('p3d_gltf', {}, {});
  assert.equal(g.asset.version, '2.0');
  assert.ok(g.nodes.length >= 30 && g.nodes.every(n => n.extras.tag));
  const spec = await mock.respond('p3d_import_spec', {}, {});
  assert.ok(spec.formats.length >= 6 && spec.limits.length >= 3 && spec.workflow.length >= 5);
});

test('the hybrid model is composed, bounded and gated', async () => {
  const mock = await import('../js/api/mock.js');
  for (const t of ['lump_al2o3_pct', 'lump_fe_pct', 'fines_fe_pct', 'fe_recovery_pct']) {
    const cfg = await mock.respond('hyb_config', {}, {target: t});
    assert.equal(cfg.target, t);
    assert.equal(cfg.mode, 'gated_residual', 'the safe composition is the one in service');
    assert.ok(cfg.modes.length >= 5, 'every composition is listed, not just the chosen one');
    assert.ok(cfg.bounds.max_correction_sigma > 0 && cfg.bounds.max_correction_frac > 0);
    assert.ok(cfg.gate.cutoff > cfg.gate.taper_from, 'the gate tapers before it closes');
    assert.ok(cfg.envelope.length > 10, 'the trained envelope is published');
    assert.ok(cfg.architecture.mechanistic && cfg.architecture.data_driven);
  }
});

test('outside its domain the hybrid falls back to physics and the data-driven model does not',
  async () => {
    const mock = await import('../js/api/mock.js');
    const e = await mock.respond('hyb_extrapolation', {}, {target: 'lump_al2o3_pct'});
    assert.equal(e.conclusion.gated_converges_to_mechanistic, true);
    assert.equal(e.rows[0].gate, 1, 'full correction at the centre of the training data');
    assert.equal(e.rows[e.rows.length - 1].gate, 0, 'no correction far outside it');
    const last = e.rows[e.rows.length - 1];
    assert.ok(Math.abs(last.gated_hybrid - last.mechanistic) < 1e-6,
      'the gated hybrid equals the mechanistic prediction off-domain');
    assert.ok(e.conclusion.data_only_departure > e.conclusion.ungated_departure,
      'the data-only model departs furthest, which is the whole argument');
    // confidence must fall monotonically as the point walks out
    const conf = e.rows.map(r => r.confidence);
    assert.deepEqual(conf, [...conf].sort((a, b) => b - a), 'domain confidence decreases');
  });

test('the hybrid beats the mechanistic model inside its domain', async () => {
  const mock = await import('../js/api/mock.js');
  const c = await mock.respond('hyb_compare', {}, {target: 'lump_al2o3_pct'});
  assert.ok(c.results.gated_residual.rmse < c.results.mechanistic_only.rmse);
  assert.ok(c.improvement_vs_mechanistic_pct > 0);
  assert.ok(c.samples.length > 20 && c.unmodelled_effect.name);
});

test('acceptance criteria are measurable, graded and never tighter than the instrument',
  async () => {
    const mock = await import('../js/api/mock.js');
    const c = await mock.respond('val_criteria', {}, {});
    assert.ok(c.kpi_criteria.length >= 12 && c.system_criteria.length >= 10);
    for (const k of c.kpi_criteria) {
      assert.ok(k.reference_sigma > 0, `${k.kpi} declares its measurement repeatability`);
      assert.ok(k.limits.max_rmse >= k.reference_sigma,
        `${k.kpi}: RMSE limit is tighter than the measurement itself`);
      assert.ok(k.limits.max_abs_bias <= k.limits.max_mae, `${k.kpi} bias <= MAE`);
      assert.ok(k.limits.max_mae <= k.limits.max_rmse, `${k.kpi} MAE <= RMSE`);
      assert.ok(k.measurement_basis && k.window && k.n_min >= 10, `${k.kpi} is evaluable`);
      assert.ok(['A', 'B', 'C'].includes(k.class));
    }
    assert.equal(c.tolerance_classes.A.gates_acceptance, true);
    assert.equal(c.tolerance_classes.C.gates_acceptance, false);
    assert.ok(c.amendment.includes('frozen'), 'criteria are frozen before the model is built');
  });

test('the scenario catalogue covers accuracy, behaviour, faults, fail-safe and exclusions',
  async () => {
    const mock = await import('../js/api/mock.js');
    const s = await mock.respond('val_scenarios', {}, {});
    const kinds = new Set(s.scenarios.map(x => x.kind));
    for (const k of ['accuracy', 'behaviour', 'fault', 'fail_safe', 'excluded']) {
      assert.ok(kinds.has(k), `scenario kind '${k}' is covered`);
    }
    assert.ok(s.scenarios.length >= 15);
    for (const sc of s.scenarios) {
      assert.ok(sc.expected_behaviour && sc.purpose && sc.numerical_criteria, sc.scenario_id);
    }
    assert.ok(s.envelope.length >= 8 && s.envelope.every(e => e.hi > e.lo && e.basis));
    // the start-up transient must be declared out of scope rather than quietly failed
    const excl = s.scenarios.find(x => x.kind === 'excluded');
    assert.ok(/not modelled|not valid/i.test(excl.expected_behaviour));
  });

test('the acceptance procedure has gates, signatories and a stated consequence of failure',
  async () => {
    const mock = await import('../js/api/mock.js');
    const p = await mock.respond('val_protocol', {}, {});
    assert.ok(p.gates.length >= 6);
    for (const g of p.gates) {
      assert.ok(g.objective && g.exit && g.on_failure, `${g.gate} is complete`);
      assert.ok(g.signatories.length >= 1 && g.evidence.length >= 1, `${g.gate} evidence`);
      assert.ok(g.signatories.every(r => r in p.roles), `${g.gate} signatories are defined roles`);
    }
    assert.ok(p.exclusion_rules.length >= 5, 'exclusions are defined in advance');
    assert.ok(/Class A criteria cannot be conceded/.test(p.concession_rule));
  });

test('a validation run produces a verdict for every criterion', async () => {
  const mock = await import('../js/api/mock.js');
  for (const pid of PLANTS) {
    const r = await mock.respond('val_run', {plant_id: pid}, {plant_id: pid, section: 'all'});
    assert.ok(r.accuracy.results.length >= 12, `${pid} accuracy criteria evaluated`);
    assert.equal(r.accuracy.summary.fail, 0, `${pid} accuracy failures: ` +
      JSON.stringify(r.accuracy.summary.class_a_fail));
    assert.ok(r.behaviour.rows.length >= 6, `${pid} step tests run`);
    assert.equal(r.behaviour.verdict, 'pass', `${pid} step tests`);
    assert.equal(r.fail_safe.verdict, 'pass', `${pid} fail-safe`);
    assert.equal(r.gate_readiness.G1_FAT, 'ready', `${pid} factory acceptance`);
    assert.deepEqual(r.gate_readiness.blocking, [], `${pid} nothing blocking`);
    // site-only measures must be flagged as outstanding, never silently assumed
    assert.ok(r.gate_readiness.evidence_outstanding.length > 0,
      `${pid} site evidence is reported as outstanding`);
    for (const x of r.accuracy.results) {
      assert.ok(['pass', 'marginal', 'fail', 'insufficient_data'].includes(x.verdict), x.kpi);
      if (x.statistics) assert.ok(Number.isFinite(x.statistics.rmse), x.kpi);
    }
  }
});

test('the acceptance report is a complete, signable document', async () => {
  const mock = await import('../js/api/mock.js');
  const r = await mock.respond('val_report', {plant_id: 'IX-OB-01'}, {plant_id: 'IX-OB-01'});
  assert.ok(r.markdown.length > 6000);
  for (const heading of ['Acceptance Test Report', 'Summary of verdicts',
    'Accuracy against plant data', 'System criteria', 'Acceptance procedure', 'Signatures',
    'Scenario catalogue']) {
    assert.ok(r.markdown.includes(heading), `report section '${heading}'`);
  }
  assert.ok(/RMSE \/ sigma/.test(r.markdown), 'errors are reported in units of the measurement');
  const cert = await mock.respond('val_certificate', {plant_id: 'IX-OB-01'},
    {plant_id: 'IX-OB-01'});
  assert.ok(cert.statement && cert.accuracy.criteria_evaluated > 0);
});

test('the v5 charts build from real payloads', async () => {
  const mock = await import('../js/api/mock.js');
  const P = await import('../js/charts/plots.js');
  const run = await mock.respond('val_run', {plant_id: 'IX-OB-01'},
    {plant_id: 'IX-OB-01', section: 'all'});
  const env = await mock.respond('val_envelope', {plant_id: 'IX-OB-01'}, {plant_id: 'IX-OB-01'});
  const ext = await mock.respond('hyb_extrapolation', {}, {target: 'lump_al2o3_pct'});
  const cmp = await mock.respond('hyb_compare', {}, {target: 'lump_al2o3_pct'});
  const figs = [
    P.criteriaMarginChart(run.accuracy.results),
    P.scenarioMatrixChart(run.behaviour.rows),
    P.envelopeChart(env.current_point.rows),
    P.extrapolationChart(ext.rows, 'Lump alumina'),
    P.compositionErrorChart(cmp.results),
    P.parityPlot([1, 2, 3, 4], [1.1, 1.9, 3.2, 3.8], {label: 'test', unit: '%', tol: 0.3}),
    P.blandAltmanChart([1, 2, 3, 4], [1.1, 1.9, 3.2, 3.8],
      {mean_difference: 0.05, sd_difference: 0.2, loa_lower: -0.34, loa_upper: 0.44, loa_width: 0.78},
      {label: 'test'}),
    P.residualProfileChart([{from: 1, to: 2, n: 5, bias: 0.1, rmse: 0.2},
      {from: 2, to: 3, n: 6, bias: -0.1, rmse: 0.15}], {label: 'test'}),
  ];
  for (const f of figs) {
    assert.ok(Array.isArray(f.data) && f.data.length > 0, 'figure has traces');
    assert.ok(f.layout && f.layout.height > 0, 'figure has a layout');
  }
});
