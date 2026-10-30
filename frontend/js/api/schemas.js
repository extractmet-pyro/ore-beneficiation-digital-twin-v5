// Lightweight contract checks: required top-level fields (and their JS types) the UI depends on.
const S = {
  health: {status: 'string', version: 'string'},
  plants: {plants: 'array'},
  plant: {plant_id: 'string', flowsheet: 'object', ore: 'object', operating: 'object'},
  tags: {tags: 'array'},
  config_schema: {flowsheet: 'object', ore: 'object', operating: 'object', defaults: 'object'},
  metadata: {model_version: 'string', unit_models: 'array', assumptions: 'array'},
  overview: {kpis: 'object', areas: 'array', power: 'object', water: 'object'},
  flowsheet: {nodes: 'array', edges: 'array', kpis: 'object', sankey: 'object'},
  live: {kpis: 'object', tags: 'array', constraints: 'array', alarms: 'array'},
  unit: {id: 'string', state: 'object', curves: 'object'},
  simulate: {kpis: 'object', units: 'object', constraints: 'array'},
  sensitivity: {variable: 'string', rows: 'array'},
  optimize: {objective: 'object', setpoints: 'object', optimised_kpis: 'object'},
  identification: {gain_matrix: 'array', mv_keys: 'array', cv_keys: 'array', models: 'object'},
  mpc_solve: {moves: 'object', predicted: 'object', u_next: 'object', handover: 'object'},
  advisory: {pairing: 'object', readiness: 'object', gain_matrix: 'array'},
  data_quality: {tags: 'array', counts: 'object'},
  p3d_model: {nodes: 'array', routes: 'array', levels: 'array', bounds: 'object', counts: 'object'},
  p3d_state: {assets: 'array', routes: 'array', summary: 'object'},
  hyb_config: {target: 'string', mode: 'string', modes: 'array', bounds: 'object', envelope: 'array'},
  hyb_attribution: {rows: 'array', domain: 'object', modes: 'array'},
  val_criteria: {kpi_criteria: 'array', system_criteria: 'array', tolerance_classes: 'object'},
  val_run: {accuracy: 'object', behaviour: 'object', system: 'object', gate_readiness: 'object'},
};
export function validate(schema, payload) {
  const req = S[schema];
  if (!req || !payload || typeof payload !== 'object') return [];
  const issues = [];
  for (const [k, t] of Object.entries(req)) {
    const v = payload[k];
    const ok = t === 'array' ? Array.isArray(v) : (t === 'object' ? v && typeof v === 'object' && !Array.isArray(v) : typeof v === t);
    if (!ok) issues.push(`${k}: expected ${t}`);
  }
  return issues;
}
