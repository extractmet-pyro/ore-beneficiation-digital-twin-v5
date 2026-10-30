// Offline mock mode. Payloads in data/mock were captured from the real backend with
// scripts/capture-mock.mjs, so the schemas are exact; ISO timestamps are shifted to "now".
// POST endpoints (simulate / optimise / MPC / ML) replay their captured responses and are marked
// so the operator always knows the numbers are not live.
const DEFAULT_PLANT = 'IX-OB-01';
const ISO_RE = /"(20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?(Z|\+00:00)"/g;
const raw = new Map();

async function defaultLoader(name) {
  const url = new URL(`../../data/mock/${name}.json.gz`, import.meta.url);
  const r = await fetch(url);
  if (!r.ok) throw new Error(`mock payload ${name} not found`);
  const buf = new Uint8Array(await r.arrayBuffer());
  if (buf[0] === 0x1f && buf[1] === 0x8b) {
    const ds = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
    return await new Response(ds).text();
  }
  return new TextDecoder().decode(buf);
}
let loader = defaultLoader;
export const setLoader = fn => { loader = fn; raw.clear(); };

async function text(name) {
  if (!raw.has(name)) raw.set(name, loader(name));
  return raw.get(name);
}
export async function exists(name) { try { await text(name); return true; } catch { raw.delete(name); return false; } }

async function load(name) {
  const txt = await text(name);
  let shift = 0;
  try { shift = Date.now() - Date.parse(JSON.parse(await text('_capture')).captured_at); } catch { shift = 0; }
  const out = JSON.parse(txt.replace(ISO_RE, (_, t) => `"${new Date(Date.parse(t + 'Z') + shift).toISOString().slice(0, 19)}Z"`));
  if (out && typeof out === 'object' && !Array.isArray(out)) out.mock = true;
  return out;
}
async function plantKey(pid, key) {
  pid = pid || DEFAULT_PLANT;
  return (await exists(`${pid}__${key}`)) ? `${pid}__${key}` : `${DEFAULT_PLANT}__${key}`;
}

/** Linear surrogate for what-if in mock mode: captured sensitivity gains around the base point. */
async function surrogate(pid, operating = {}, ore = {}, base) {
  const g = JSON.parse(await text(await plantKey(pid, 'gains')));
  const kpis = {...base.kpis};
  for (const [group, changes] of [['operating', operating], ['ore', ore]]) {
    for (const [v, val] of Object.entries(changes || {})) {
      if (!g[group][v] || typeof val !== 'number') continue;
      const d = val - Number(g.current[group][v]);
      for (const [k, dk] of Object.entries(g[group][v])) if (typeof kpis[k] === 'number' && dk !== null) kpis[k] += dk * d;
    }
  }
  kpis.fe_recovery_pct = Math.min(Math.max(kpis.fe_recovery_pct, 30), 99);
  for (const k of ['lump_al2o3_pct', 'fines_al2o3_pct', 'pellet_fines_al2o3_pct'])
    if (typeof kpis[k] === 'number') kpis[k] = Math.max(kpis[k], 0.05);
  const deltas = {};
  for (const k of Object.keys(kpis)) if (typeof kpis[k] === 'number' && typeof base.kpis[k] === 'number') deltas[k] = kpis[k] - base.kpis[k];
  return [kpis, deltas];
}

const GLOBAL = ['health', 'plants', 'metadata', 'constraints', 'objectives', 'units', 'mpc_config',
  'optimize_catalogue', 'replay_info', 'events', 'ml_status', 'ml_models',
  'p3d_levels', 'p3d_clash', 'p3d_gltf', 'p3d_import_spec', 'hyb_modes',
  'val_criteria', 'val_scenarios', 'val_protocol'];

export async function respond(name, pp = {}, params = {}, body = null) {
  const pid = pp.plant_id || params.plant_id || (body && body.plant_id) || DEFAULT_PLANT;
  if (GLOBAL.includes(name)) return load(name);
  if (name === 'unit') {
    const k = await plantKey(pid, `unit_${pp.unit_id}`);
    return (await exists(k)) ? load(k) : load(`${DEFAULT_PLANT}__unit_rougher`);
  }
  if (name === 'p3d_asset') {
    const k = await plantKey(pid, `p3d_asset_${pp.asset_id}`);
    return (await exists(k)) ? load(k) : load(await plantKey(pid, 'p3d_asset_whims'));
  }
  if (name === 'p3d_state') {
    const k = await plantKey(pid, `p3d_state_${params.overlay || 'status'}`);
    return (await exists(k)) ? load(k) : load(await plantKey(pid, 'p3d_state_status'));
  }
  if (name === 'p3d_match' || name === 'p3d_register') {
    return {mock: true, matched: [], ambiguous: [], unmatched: [], coverage_pct: 0, ready: false,
      note: 'Tag matching and registration need the live backend.'};
  }
  if (name === 'val_envelope_check') {
    return {mock: true, inside_envelope: null, rows: [],
      statement: 'Envelope checks on an arbitrary point need the live backend.'};
  }
  if (['hyb_config', 'hyb_predict', 'hyb_attribution', 'hyb_domain', 'hyb_compare',
    'hyb_extrapolation'].includes(name)) {
    const t = params.target || 'lump_al2o3_pct';
    const k = `${name}__${t}`;
    return (await exists(k)) ? load(k) : load(`${name}__lump_al2o3_pct`);
  }
  if (name === 'val_run') {
    const k = await plantKey(pid, `val_run_${params.section || 'all'}`);
    return (await exists(k)) ? load(k) : load(await plantKey(pid, 'val_run_all'));
  }
  if (name === 'ml_importance' || name === 'ml_learning_curve' || name === 'ml_pdp' || name === 'ml_hybrid' || name === 'ml_scan') {
    const k = `${name}__${params.target || 'lump_al2o3_pct'}`;
    return (await exists(k)) ? load(k) : load(`${name}__lump_al2o3_pct`);
  }
  if (name === 'sensitivity') {
    const base = await load(await plantKey(pid, 'simulate'));
    const g = JSON.parse(await text(await plantKey(pid, 'gains')));
    const grp = body.group || 'operating', v = body.variable || 'lump_jig_cut_sg';
    const cur = Number(g.current[grp][v] ?? 1);
    const rows = (body.values || []).map(x => {
      const row = {value: x};
      for (const k of body.kpis || []) row[k] = (base.kpis[k] ?? 0) + ((g[grp][v] || {})[k] || 0) * (x - cur);
      return row;
    });
    return {plant_id: pid, group: grp, variable: v, kpis: body.kpis, rows, mock: true};
  }
  if (name === 'simulate') {
    const base = await load(await plantKey(pid, 'simulate'));
    if (!body || (!body.operating && !body.ore)) return base;
    const out = JSON.parse(JSON.stringify(base));
    const [kpis, deltas] = await surrogate(pid, body.operating, body.ore, base);
    Object.assign(out, {kpis, kpi_deltas: deltas, base_kpis: base.kpis, mock_surrogate: true});
    if (body.flowsheet && Object.keys(body.flowsheet).length)
      out.warnings = [...(out.warnings || []), 'Mock mode: equipment changes need the live backend (the surrogate covers operating and ore changes only).'];
    return out;
  }
  if (name === 'optimize') {
    const k = await plantKey(pid, `optimize_${(body && body.objective) || 'margin'}`);
    return (await exists(k)) ? load(k) : load(await plantKey(pid, 'optimize_margin'));
  }
  if (name === 'ml_predict') return load(await plantKey(pid, 'ml_predict'));
  if (name === 'ml_retrain') return {trained: [], n_samples: 0, mock: true,
    note: 'Retraining requires the live backend.'};
  if (name === 'mpc_solve' || name === 'mpc_handover') return load(await plantKey(pid, 'mpc_solve'));
  if (name === 'mpc_simulate') return load(await plantKey(pid, 'mpc_simulate'));
  if (name === 'monte_carlo') return load(await plantKey(pid, 'monte_carlo'));
  if (name === 'pareto') return load(await plantKey(pid, 'pareto'));
  if (name === 'compare') {
    const base = await load(await plantKey(pid, 'simulate'));
    const out = [];
    for (const sc of (body && body.scenarios) || []) {
      const [kpis] = await surrogate(pid, (sc.overrides || {}).operating, (sc.overrides || {}).ore, base);
      out.push({name: sc.name || 'scenario', overrides: sc.overrides || {}, kpis, constraint_penalty: base.constraint_penalty, violations: []});
    }
    return {plant_id: pid, scenarios: out, mock: true};
  }
  const ALIAS = {ts_tags: 'tag_trend', ts_kpis: 'ts_kpis'};
  const key = await plantKey(pid, ALIAS[name] || name);
  if (await exists(key)) return load(key);
  throw new Error(`No mock payload for endpoint ${name}`);
}
