// Shared constants for the ore-beneficiation (gravity + WHIMS) operator desk.
export const SOURCE = {
  measured: {color: '#29b6f6', dash: 'solid', symbol: 'circle', icon: '●', label: 'Measured (DCS / historian)'},
  estimated: {color: '#ffb300', dash: 'dash', symbol: 'diamond', icon: '◐', label: 'Estimated (soft sensor / ML)'},
  simulated: {color: '#ab47bc', dash: 'dot', symbol: 'square', icon: '◇', label: 'Simulated (digital twin)'},
  recommended: {color: '#66bb6a', dash: 'dashdot', symbol: 'triangle-up', icon: '▲', label: 'Recommended (optimiser / MPC)'},
};
export const STATUS_COLOR = {normal: '#43a047', caution: '#fb8c00', alarm: '#e53935', offline: '#78909c',
  warning: '#fb8c00', info: '#29b6f6', good: '#43a047', suspect: '#fb8c00', bad: '#e53935', fault: '#e53935',
  watch: '#fb8c00', stable: '#43a047', shifting: '#fb8c00', drifted: '#e53935', workable: '#fb8c00', poor: '#e53935'};
export const STATUS_ICON = {normal: '🟢', caution: '🟠', alarm: '🔴', offline: '⚫', warning: '🟠', info: '🔵'};
export const PERSONAS = {
  'Control-room operator': {canAccept: true, canEditConfig: false, focus: 'Live twin, alarms, MPC moves, first actions'},
  'Process engineer': {canAccept: true, canEditConfig: true, focus: 'Gravity circuit drill-down, what-if, optimisation'},
  'Plant manager': {canAccept: false, canEditConfig: false, focus: 'Three products against contract, yield, cost'},
  'OEM / service engineer': {canAccept: false, canEditConfig: true, focus: 'Jig beds, spiral loading, WHIMS matrix, wear'},
  'Data scientist': {canAccept: false, canEditConfig: true, focus: 'Soft sensors, ML models, drift, reconciliation'},
};
export const AREA_COLORS = {A100: '#8d6e63', A200: '#00897b', A300: '#5c6bc0', A400: '#1e88e5',
  A500: '#7b1fa2', A600: '#0288d1', A700: '#f9a825', A800: '#c62828', A900: '#00acc1'};

// ---- three products, three specifications ------------------------------------------------------
export const PRODUCTS = [
  {key: 'lump', label: 'Lump ore', colour: '#8d6e63', use: 'Direct blast-furnace feed',
   fe: 'lump_fe_pct', al: 'lump_al2o3_pct', si: 'lump_sio2_pct', tph: 'lump_tph', yieldKey: 'lump_yield_pct'},
  {key: 'fines', label: 'Sinter fines', colour: '#f9a825', use: 'Sinter plant feed',
   fe: 'fines_fe_pct', al: 'fines_al2o3_pct', si: 'fines_sio2_pct', tph: 'fines_tph', yieldKey: 'fines_yield_pct'},
  {key: 'pellet', label: 'Pellet-plant feed', colour: '#c62828', use: 'Ground and balled at the pellet plant',
   fe: 'pellet_fines_fe_pct', al: 'pellet_fines_al2o3_pct', si: 'pellet_fines_sio2_pct',
   tph: 'pellet_fines_tph', yieldKey: 'pellet_yield_pct'},
];

export const KPI_FMT = {throughput_tph: ',.0f', lump_tph: ',.1f', fines_tph: ',.1f', pellet_fines_tph: ',.1f',
  saleable_tph: ',.1f', tailings_tph: ',.1f', mass_yield_pct: '.2f', lump_yield_pct: '.2f',
  fines_yield_pct: '.2f', pellet_yield_pct: '.2f', lump_fe_pct: '.2f', lump_sio2_pct: '.2f',
  lump_al2o3_pct: '.3f', lump_loi_pct: '.2f', fines_fe_pct: '.2f', fines_sio2_pct: '.2f',
  fines_al2o3_pct: '.3f', pellet_fines_fe_pct: '.2f', pellet_fines_sio2_pct: '.2f',
  pellet_fines_al2o3_pct: '.3f', product_fe_pct: '.2f', tailings_fe_pct: '.2f', fe_loss_tph: '.2f',
  fe_recovery_pct: '.2f', lump_fe_recovery_pct: '.2f', fines_fe_recovery_pct: '.2f',
  pellet_fe_recovery_pct: '.2f', slimes_to_tailings_pct: '.2f', lump_p80_mm: '.1f', fines_p80_um: '.0f',
  pellet_fines_p80_um: '.1f', scrubber_clay_removal_pct: '.1f', classifier_d50_um: '.0f',
  spiral_load_fraction: '.3f', table_load_fraction: '.3f', whims_load_fraction: '.3f',
  energy_kwh_t: '.3f', energy_per_product_kwh_t: '.3f', total_power_mw: '.3f', fresh_water_m3_t: '.4f',
  total_water_m3_t: '.3f', fresh_water_m3_h: ',.0f', water_recycle_pct: '.1f', tails_uf_solids_pct: '.1f',
  tails_overflow_tss_mg_l: '.0f', realised_lump_usd_dmt: '.2f', realised_fines_usd_dmt: '.2f',
  realised_pellet_usd_dmt: '.2f', revenue_usd_h: ',.0f', cost_usd_h: ',.0f', cost_usd_t: '.2f',
  cost_usd_product_t: '.2f', margin_usd_h: ',.0f', margin_usd_product_t: '.2f', carbon_kgco2_t: '.3f'};

export const KPI_LABEL = {throughput_tph: ['ROM throughput', 't/h'], lump_tph: ['Lump ore', 't/h'],
  fines_tph: ['Sinter fines', 't/h'], pellet_fines_tph: ['Pellet-plant feed', 't/h'],
  saleable_tph: ['Saleable product', 't/h'], tailings_tph: ['Tailings', 't/h'],
  mass_yield_pct: ['Mass yield', '%'], lump_yield_pct: ['Lump yield', '%'],
  fines_yield_pct: ['Fines yield', '%'], pellet_yield_pct: ['Pellet-feed yield', '%'],
  lump_fe_pct: ['Lump Fe', '% Fe'], lump_sio2_pct: ['Lump silica', '% SiO₂'],
  lump_al2o3_pct: ['Lump alumina', '% Al₂O₃'], lump_loi_pct: ['Lump LOI', '%'],
  fines_fe_pct: ['Fines Fe', '% Fe'], fines_sio2_pct: ['Fines silica', '% SiO₂'],
  fines_al2o3_pct: ['Fines alumina', '% Al₂O₃'], pellet_fines_fe_pct: ['Pellet feed Fe', '% Fe'],
  pellet_fines_sio2_pct: ['Pellet feed silica', '% SiO₂'],
  pellet_fines_al2o3_pct: ['Pellet feed alumina', '% Al₂O₃'],
  product_fe_pct: ['Weighted product Fe', '% Fe'], tailings_fe_pct: ['Tailings Fe', '% Fe'],
  fe_loss_tph: ['Fe lost', 't/h'], fe_recovery_pct: ['Fe recovery', '%'],
  lump_fe_recovery_pct: ['Fe to lump', '%'], fines_fe_recovery_pct: ['Fe to fines', '%'],
  pellet_fe_recovery_pct: ['Fe to pellet feed', '%'], slimes_to_tailings_pct: ['Slimes lost', '% of feed'],
  lump_p80_mm: ['Lump P80', 'mm'], fines_p80_um: ['Fines P80', 'µm'],
  pellet_fines_p80_um: ['Pellet feed P80', 'µm'], scrubber_clay_removal_pct: ['Clay removed', '%'],
  classifier_d50_um: ['Classifier cut', 'µm'], spiral_load_fraction: ['Spiral loading', '×'],
  table_load_fraction: ['Table loading', '×'], whims_load_fraction: ['WHIMS loading', '×'],
  energy_kwh_t: ['Specific energy', 'kWh/t'], energy_per_product_kwh_t: ['Energy per product', 'kWh/t'],
  total_power_mw: ['Total power', 'MW'], fresh_water_m3_t: ['Fresh water', 'm³/t'],
  total_water_m3_t: ['Circulating water', 'm³/t'], fresh_water_m3_h: ['Fresh water', 'm³/h'],
  water_recycle_pct: ['Water recycled', '%'], tails_uf_solids_pct: ['Tails U/F', '% solids'],
  tails_overflow_tss_mg_l: ['Recycle water TSS', 'mg/L'],
  realised_lump_usd_dmt: ['Lump price', 'USD/dmt'], realised_fines_usd_dmt: ['Fines price', 'USD/dmt'],
  realised_pellet_usd_dmt: ['Pellet feed price', 'USD/dmt'], revenue_usd_h: ['Revenue', 'USD/h'],
  cost_usd_h: ['Cost', 'USD/h'], cost_usd_t: ['Cost per ROM t', 'USD/t'],
  cost_usd_product_t: ['Cost per product t', 'USD/t'], margin_usd_h: ['Operating margin', 'USD/h'],
  margin_usd_product_t: ['Margin per product t', 'USD/t'], carbon_kgco2_t: ['Carbon', 'kg CO₂/t']};

export const LOWER_IS_BETTER = new Set(['lump_sio2_pct', 'lump_al2o3_pct', 'lump_loi_pct', 'fines_sio2_pct',
  'fines_al2o3_pct', 'pellet_fines_sio2_pct', 'pellet_fines_al2o3_pct', 'tailings_fe_pct', 'fe_loss_tph',
  'slimes_to_tailings_pct', 'energy_kwh_t', 'energy_per_product_kwh_t', 'total_power_mw', 'fresh_water_m3_t',
  'fresh_water_m3_h', 'total_water_m3_t', 'cost_usd_t', 'cost_usd_h', 'cost_usd_product_t', 'carbon_kgco2_t',
  'tails_overflow_tss_mg_l', 'tailings_tph', 'spiral_load_fraction', 'table_load_fraction',
  'whims_load_fraction']);

export const HEADLINE_KPIS = ['lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct', 'fe_recovery_pct',
  'mass_yield_pct', 'saleable_tph', 'energy_kwh_t', 'margin_usd_h'];

export const CIRCUIT_LABEL = {
  SCRUB_JIG_SPIRAL_TABLE_WHIMS: 'Scrubbing → jigging → spirals → tables → WHIMS',
  SCRUB_JIG_ONLY: 'Scrubbing → jigging only',
  SCRUB_SPIRAL_WHIMS: 'Scrubbing → spirals → WHIMS'};

export const UNIT_ICON = {crusher: '🪨', screen: '🔲', scrubber: '🛢️', jig: '⬍', classifier: '🌀',
  cyclone: '🌀', spiral: '🍥', table: '📊', magnet: '🧲', thickener: '⭕', product: '🚚', water: '💧',
  source: '⛰️'};
export const WINDOWS = ['1h', '8h', '24h', '72h', '7d'];
export const WINDOW_HOURS = {'1h': 1, '8h': 8, '24h': 24, '72h': 72, '7d': 168};

export const PAGES = [
  {id: 'home', icon: '⛰️', label: 'Home', desc: 'Plant summary, three products, navigation'},
  {id: 'overview', icon: '📊', label: 'Executive overview', desc: 'Product quality against contract, yield, cost, shifts'},
  {id: 'live', icon: '🏭', label: 'Live process twin', desc: 'Flowsheet, 3-D plant, tag board, soft sensors, mass flow'},
  {id: 'units', icon: '⚙️', label: 'Unit operations', desc: 'Scrubber, jigs, classifier, spirals, tables, WHIMS'},
  {id: 'gravity', icon: '⚖️', label: 'Gravity analysis', desc: 'Washability, partition curves, Ep by size, separation windows'},
  {id: 'simulate', icon: '🧪', label: 'Simulation / what-if', desc: 'Ore, equipment and set-point studies with full stream results'},
  {id: 'optimize', icon: '🎯', label: 'Optimisation', desc: 'Constrained set-point search, robustness, three-product trade-offs'},
  {id: 'mpc', icon: '🎛️', label: 'Model predictive control', desc: 'Identification, move plan, closed-loop study, DCS hand-over'},
  {id: 'ml', icon: '🤖', label: 'Machine learning', desc: 'Soft sensors, hybrid twin correction, anomalies, drift'},
  {id: 'hybrid', icon: '🧬', label: 'Hybrid model', desc: 'Mechanistic plus data driven, domain of validity, attribution'},
  {id: 'plant3d', icon: '🏗️', label: 'Plant 3-D model', desc: 'Tagged plant geometry with live twin state, levels, CAD import'},
  {id: 'validation', icon: '✅', label: 'Validation & acceptance', desc: 'Acceptance criteria, envelope, scenarios, gates, report'},
  {id: 'advisory', icon: '🧭', label: 'Control advisory', desc: 'Gain matrix, RGA pairing, readiness, operator guidance'},
  {id: 'health', icon: '🩺', label: 'Diagnostics', desc: 'Balances, reconciliation, residuals, fault catalogue'},
  {id: 'quality', icon: '🧹', label: 'Data quality', desc: 'Instrument health, coverage, noise, calibration bias'},
  {id: 'admin', icon: '🛠️', label: 'Admin / config', desc: 'Backend, personas, model metadata, tag dictionary, log'},
];
