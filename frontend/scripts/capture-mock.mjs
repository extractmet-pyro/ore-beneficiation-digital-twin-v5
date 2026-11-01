// Refresh mock payloads from a running backend (keeps mock mode schema-exact).
//   node scripts/capture-mock.mjs http://localhost:8000            resume: skip what exists
//   node scripts/capture-mock.mjs http://localhost:8000 --force    re-capture everything
//
// The hybrid and validation endpoints train models and run the full acceptance suite, so a cold
// capture takes several minutes. Resume is the default so an interrupted run can be continued.
import {existsSync, mkdirSync, writeFileSync} from 'node:fs';
import {gzipSync} from 'node:zlib';

const args = process.argv.slice(2).filter(a => !a.startsWith('--'));
const FORCE = process.argv.includes('--force');
const base = (args[0] || 'http://localhost:8000').replace(/\/$/, '');
const out = new URL('../data/mock/', import.meta.url);
mkdirSync(out, {recursive: true});
const have = n => !FORCE && existsSync(new URL(`${n}.json.gz`, out));
const save = (n, d) => writeFileSync(new URL(`${n}.json.gz`, out), gzipSync(JSON.stringify(d)));
/** Fetch and save unless the payload is already on disk (resume). */
const keep = async (n, fn) => { if (have(n)) return; save(n, await fn()); };
const get = async (p, q = {}) => { const r = await fetch(`${base}${p}?${new URLSearchParams(q)}`); if (!r.ok) throw new Error(`${p} ${r.status}`); return r.json(); };
const post = async (p, b) => { const r = await fetch(base + p, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)}); if (!r.ok) throw new Error(`${p} ${r.status}`); return r.json(); };
const A = '/api/v1';
const OPS = ['rom_feed_tph', 'primary_css_mm', 'secondary_css_mm', 'tertiary_css_mm',
  'scrubber_speed_pct_critical', 'scrubber_water_m3_h', 'scrubber_solids_pct', 'trommel_aperture_mm',
  'lump_jig_cut_sg', 'lump_jig_stroke_mm', 'lump_jig_frequency_rpm', 'lump_jig_bed_depth_mm',
  'lump_jig_hutch_water_m3_h', 'classifier_dilution_water_m3_h', 'classifier_weir_height_m',
  'classifier_screw_rpm', 'fines_screen_aperture_mm', 'fines_jig_cut_sg', 'fines_jig_hutch_water_m3_h',
  'deslime_cyclone_pressure_kpa', 'spiral_cyclone_pressure_kpa', 'spiral_feed_solids_pct',
  'spiral_wash_water_m3_h', 'spiral_conc_splitter', 'spiral_middling_splitter', 'table_slope_deg',
  'table_wash_water_m3_h', 'table_conc_cut', 'whims_field_tesla', 'whims_wash_water_m3_h',
  'whims_feed_solids_pct', 'tails_flocculant_g_t', 'reclaim_water_fraction'];
const ORES = ['fe_head_pct', 'sio2_head_pct', 'al2o3_head_pct', 'goethite_share', 'clay_share',
  'liberation_d50_um', 'lump_friability', 'bond_wi_kwh_t', 'axb', 'f80_mm', 'moisture_pct'];
const ML_TARGETS = ['lump_al2o3_pct', 'lump_fe_pct', 'fines_fe_pct', 'fe_recovery_pct', 'margin_usd_h'];

save('_capture', {captured_at: new Date().toISOString(), backend: base});
save('health', await get('/health'));
const plants = await get(`${A}/plants`); save('plants', plants);
save('metadata', await get(`${A}/metadata`));
save('constraints', await get(`${A}/metadata/constraints`));
save('objectives', await get(`${A}/metadata/objectives`));
save('units', await get(`${A}/units`));
save('mpc_config', await get(`${A}/mpc/config`));
save('optimize_catalogue', await get(`${A}/optimization/objectives`));
save('replay_info', await get(`${A}/timeseries/replay-info`));
save('events', await get(`${A}/diagnostics/events`));
save('ml_status', await get(`${A}/ml/status`));
save('ml_models', await get(`${A}/ml/models`));
// ---- v5: plant 3-D model, hybrid model, validation and acceptance ----
await keep('p3d_levels', () => get(`${A}/plant3d/levels`));
await keep('p3d_clash', () => get(`${A}/plant3d/clash`));
await keep('p3d_gltf', () => get(`${A}/plant3d/gltf-manifest`));
await keep('p3d_import_spec', () => get(`${A}/plant3d/import-spec`));
await keep('hyb_modes', () => get(`${A}/hybrid/modes`));
await keep('val_criteria', () => get(`${A}/validation/criteria`));
await keep('val_scenarios', () => get(`${A}/validation/scenarios`));
await keep('val_protocol', () => get(`${A}/validation/protocol`));
const HYB_TARGETS = ['lump_al2o3_pct', 'lump_fe_pct', 'fines_fe_pct', 'fe_recovery_pct'];
for (const t of HYB_TARGETS) {
  await keep(`hyb_config__${t}`, () => get(`${A}/hybrid/config`, {target: t}));
  await keep(`hyb_compare__${t}`, () => get(`${A}/hybrid/compare`, {target: t}));
  await keep(`hyb_extrapolation__${t}`, () => get(`${A}/hybrid/extrapolation`, {target: t}));
}
for (const t of ML_TARGETS) {
  save(`ml_importance__${t}`, await get(`${A}/ml/importance`, {target: t}));
  save(`ml_learning_curve__${t}`, await get(`${A}/ml/learning-curve`, {target: t}));
  save(`ml_pdp__${t}`, await get(`${A}/ml/partial-dependence`, {target: t, feature: 'lump_jig_cut_sg'}));
  save(`ml_hybrid__${t}`, await get(`${A}/ml/hybrid`, {target: t}));
  save(`ml_scan__${t}`, await get(`${A}/ml/scan`, {target: t, feature: 'lump_jig_cut_sg'}));
}
const units = (await get(`${A}/units`)).units.map(u => u.id);
for (const {plant_id: pid} of plants.plants) {
  console.log('capturing', pid);
  save(`${pid}__plant`, await get(`${A}/plants/${pid}`));
  save(`${pid}__plant_tags`, await get(`${A}/plants/${pid}/tags`));
  save(`${pid}__config_schema`, await get(`${A}/plants/${pid}/config-schema`));
  save(`${pid}__overview`, await get(`${A}/overview`, {plant_id: pid}));
  save(`${pid}__flowsheet`, await get(`${A}/overview/flowsheet`, {plant_id: pid}));
  save(`${pid}__shifts`, await get(`${A}/overview/shifts`, {plant_id: pid, shifts: 6}));
  save(`${pid}__live`, await get(`${A}/live/snapshot`, {plant_id: pid}));
  save(`${pid}__soft_sensors`, await get(`${A}/live/soft-sensors`, {plant_id: pid}));
  save(`${pid}__trend`, await get(`${A}/live/trend`, {plant_id: pid, hours: 24,
    keys: 'lump_fe_pct,lump_al2o3_pct,fines_fe_pct,fe_recovery_pct,mass_yield_pct,throughput_tph,energy_kwh_t'}));
  // same parameters the Live page asks for, so the captured trace and the live one match
  save(`${pid}__tag_trend`, await get(`${A}/live/tag-trend`, {plant_id: pid, hours: 24, step_h: 0.5,
    tags: '302_AIC_025,302_AIC_024,301_DIC_020,201_SIC_010,601_DIC_051,801_JIC_071'}));
  save(`${pid}__ts_kpis`, await get(`${A}/timeseries/kpis`, {plant_id: pid, end_h: 168, step_h: 2,
    keys: 'lump_fe_pct,lump_al2o3_pct,fines_fe_pct,fe_recovery_pct,mass_yield_pct,margin_usd_h'}));
  save(`${pid}__balance`, await get(`${A}/diagnostics/balance`, {plant_id: pid}));
  save(`${pid}__reconcile`, await get(`${A}/diagnostics/reconcile`, {plant_id: pid}));
  save(`${pid}__residuals`, await get(`${A}/diagnostics/residuals`, {plant_id: pid, hours: 48}));
  save(`${pid}__data_quality`, await get(`${A}/data-quality/report`, {plant_id: pid, hours: 24}));
  save(`${pid}__data_missing`, await get(`${A}/data-quality/missing`, {plant_id: pid}));
  save(`${pid}__grade_recovery`, await get(`${A}/simulation/grade-recovery`, {plant_id: pid, points: 9}));
  save(`${pid}__washability`, await get(`${A}/simulation/washability`, {plant_id: pid}));
  save(`${pid}__tornado`, await get(`${A}/simulation/tornado`, {plant_id: pid}));
  save(`${pid}__mpc_identification`, await get(`${A}/mpc/identification`, {plant_id: pid}));
  save(`${pid}__mpc_step`, await get(`${A}/mpc/step-response`, {plant_id: pid, cv: 'lump_al2o3_pct'}));
  save(`${pid}__mpc_advisory`, await get(`${A}/mpc/advisory`, {plant_id: pid}));
  save(`${pid}__mpc_solve`, await post(`${A}/mpc/solve`, {plant_id: pid}));
  save(`${pid}__mpc_simulate`, await post(`${A}/mpc/simulate`, {plant_id: pid, steps: 36}));
  save(`${pid}__ml_predict`, await post(`${A}/ml/predict`, {plant_id: pid}));
  save(`${pid}__ml_anomaly`, await get(`${A}/ml/anomaly`, {plant_id: pid, hours: 48}));
  save(`${pid}__ml_drift`, await get(`${A}/ml/drift`, {plant_id: pid}));
  for (const ov of ['status', 'duty', 'power', 'throughput', 'fe', 'solids', 'none'])
    await keep(`${pid}__p3d_state_${ov}`, () => get(`${A}/plant3d/state`, {plant_id: pid, overlay: ov}));
  await keep(`${pid}__p3d_model`, () => get(`${A}/plant3d/model`, {plant_id: pid}));
  for (const a of ['scrubber', 'lump_jig', 'spiral_classifier', 'spirals', 'shaking_tables',
    'whims', 'tails_thickener', 'primary_crusher'])
    await keep(`${pid}__p3d_asset_${a}`, () => get(`${A}/plant3d/asset/${a}`, {plant_id: pid}));
  await keep(`${pid}__val_envelope`, () => get(`${A}/validation/envelope`, {plant_id: pid}));
  await keep(`${pid}__val_certificate`, () => get(`${A}/validation/certificate`, {plant_id: pid}));
  await keep(`${pid}__val_report`, () => get(`${A}/validation/report`, {plant_id: pid, tests_pass: true}));
  // one full run per plant; the mock resolver falls back to it for the single-section views
  await keep(`${pid}__val_run_all`, () => get(`${A}/validation/run`,
    {plant_id: pid, section: 'all', tests_pass: true}));
  for (const t of HYB_TARGETS) {
    await keep(`hyb_predict__${t}`, () => get(`${A}/hybrid/predict`, {plant_id: pid, target: t}));
    await keep(`hyb_attribution__${t}`, () => get(`${A}/hybrid/attribution`, {plant_id: pid, target: t}));
    await keep(`hyb_domain__${t}`, () => get(`${A}/hybrid/domain-check`, {plant_id: pid, target: t}));
  }
  for (const u of units) save(`${pid}__unit_${u}`, await get(`${A}/units/${u}`, {plant_id: pid}));
  const b = await post(`${A}/simulation/run`, {plant_id: pid, include_streams: true});
  save(`${pid}__simulate`, b);
  const keys = Object.keys(b.kpis).filter(k => typeof b.kpis[k] === 'number');
  const cfg = await get(`${A}/plants/${pid}`);
  const gains = {current: {operating: cfg.operating, ore: cfg.ore}, operating: {}, ore: {}};
  for (const [grp, names] of [['operating', OPS], ['ore', ORES]]) for (const v of names) {
    const cur = cfg[grp][v];
    if (typeof cur !== 'number' || !cur) continue;
    try {
      const s = await post(`${A}/simulation/sensitivity`, {plant_id: pid, group: grp, variable: v,
        values: [cur * 0.95, cur, cur * 1.05], kpis: keys});
      const dx = s.rows[2].value - s.rows[0].value;
      if (!dx) continue;
      gains[grp][v] = Object.fromEntries(keys.filter(k => s.rows[0][k] !== null && s.rows[2][k] !== null)
        .map(k => [k, (s.rows[2][k] - s.rows[0][k]) / dx]));
    } catch { /* not applicable */ }
  }
  save(`${pid}__gains`, gains);
  for (const o of (pid === 'IX-OB-01' ? ['margin', 'fe_recovery', 'lump_yield', 'lump_quality'] : ['margin'])) {
    save(`${pid}__optimize_${o}`, await post(`${A}/optimization/run`, {plant_id: pid, objective: o, max_evals: 160}));
  }
  save(`${pid}__monte_carlo`, await post(`${A}/optimization/monte-carlo`, {plant_id: pid, samples: 14}));
  save(`${pid}__pareto`, await post(`${A}/optimization/pareto`, {plant_id: pid, samples: 40}));
}
console.log('done →', out.pathname);
