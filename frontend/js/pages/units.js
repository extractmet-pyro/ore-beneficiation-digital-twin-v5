// Unit operations: operating point, feed/product streams and characteristic curves per unit.
import * as api from '../api/client.js';
import * as S from '../state.js';
import {attritionChart, captureCurveChart, chart, epBySizeChart, fluxChart, gradeRecoveryChart,
  partitionChart, psdChart, responseChart, settlingChart, sizeWindowChart, trompChart} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {grid, h, note, select, table} from '../ui/dom.js';
import {humanise} from '../utils/format.js';
import {sectionCard, unitStateTable} from './common.js';

const LABELS = {lump_fe_pct: 'Lump Fe (%)', lump_al2o3_pct: 'Lump alumina (%)', lump_yield_pct: 'Lump yield (%)',
  lump_tph: 'Lump ore (t/h)', fines_fe_pct: 'Sinter fines Fe (%)', fines_al2o3_pct: 'Fines alumina (%)',
  fines_tph: 'Sinter fines (t/h)', pellet_fines_fe_pct: 'Pellet feed Fe (%)',
  pellet_fines_tph: 'Pellet feed (t/h)', fe_recovery_pct: 'Fe recovery (%)', mass_yield_pct: 'Mass yield (%)',
  tailings_fe_pct: 'Tailings Fe (%)', energy_kwh_t: 'Specific energy (kWh/t)',
  classifier_d50_um: 'Classifier cut (µm)', slimes_to_tailings_pct: 'Slimes lost (%)',
  scrubber_clay_removal_pct: 'Clay removed (%)', fresh_water_m3_t: 'Fresh water (m³/t)',
  water_recycle_pct: 'Water recycled (%)', cost_usd_t: 'Cost (USD/t)', value: 'Set-point'};

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const {units} = await api.get('units');
  const chosen = ctx.params.unit || S.get('selectedUnit') || 'rougher';
  const unitId = units.some(u => u.id === chosen) ? chosen : units[0].id;
  S.set('selectedUnit', unitId);
  const d = await api.get('unit', {unit_id: unitId, plant_id: pid});
  root.append(pageHeader(`${d.label}`, {subtitle: `${d.area} · model: ${d.model}`}));
  root.append(h('div', {class: 'row mb'}, h('label', {}, 'Unit'),
    select(units.map(u => ({value: u.id, label: `${u.area} · ${u.label}`})), unitId,
      {onchange: v => { S.set('selectedUnit', v); ctx.go('units', {unit: v}); }})));

  root.append(grid(2,
    sectionCard('Operating point', unitStateTable(d.state)),
    sectionCard('Feed and product', table([d.feed, d.product].filter(Boolean).map((s, i) => ({
      Stream: i === 0 ? 'Feed' : 'Product', Name: s.name, 't/h': s.solids_tph, '% solids': s.solids_pct,
      '% Fe': s.fe_pct, '% SiO₂': s.sio2_pct, 'P80 µm': s.p80_um, 'Liberation %': s.liberation_pct})),
    ['Stream', 'Name', {key: 't/h', num: true, fmt: ',.1f'}, {key: '% solids', num: true, fmt: '.1f'},
      {key: '% Fe', num: true, fmt: '.2f'}, {key: '% SiO₂', num: true, fmt: '.2f'},
      {key: 'P80 µm', num: true, fmt: '.1f'}, {key: 'Liberation %', num: true, fmt: '.1f'}]),
    d.feed && d.product ? chart(psdChart({Feed: d.feed, Product: d.product}, 'Size distributions')) : null)));

  const c = d.curves || {};
  const panels = [];
  const xlab = c.x_label || 'Set-point';
  if (c.css_response) panels.push(sectionCard('Closed-side-setting response',
    chart(responseChart(c.css_response, 'value', ['energy_kwh_t', 'lump_yield_pct'], {...LABELS, value: xlab}))));
  if (c.speed_response) panels.push(sectionCard('Drum-speed response',
    chart(responseChart(c.speed_response, 'value', ['lump_al2o3_pct', 'lump_fe_pct'], {...LABELS, value: xlab}))));
  if (c.water_response) panels.push(sectionCard('Scrubber-water response',
    chart(responseChart(c.water_response, 'value', ['lump_al2o3_pct', 'scrubber_clay_removal_pct'],
      {...LABELS, value: 'Scrubber water (m³/h)'}))));
  if (c.attrition_curve) panels.push(sectionCard('Attrition kinetics',
    chart(attritionChart(c.attrition_curve, d.state.residence_time_min))));
  if (c.cut_density_response) panels.push(sectionCard('Cut-density response',
    chart(responseChart(c.cut_density_response, 'value',
      d.id === 'lump_jig' ? ['lump_fe_pct', 'lump_al2o3_pct'] : ['fines_fe_pct', 'fines_tph'],
      {...LABELS, value: 'Cut density (SG)'}))));
  if (c.partition_curve && c.partition_curve[0] && c.partition_curve[0].sg !== undefined)
    panels.push(sectionCard('Tromp partition curve',
      chart(trompChart(c.partition_curve, d.state.cut_sg_achieved ?? d.state.cut_sg_conc))));
  if (c.partition_curve && c.partition_curve[0] && c.partition_curve[0].to_underflow_pct !== undefined)
    panels.push(sectionCard('Cyclone partition curve',
      chart(partitionChart(c.partition_curve, d.state.d50c_um))));
  if (c.partition_curve && c.partition_curve[0] && c.partition_curve[0].to_oversize_pct !== undefined)
    panels.push(sectionCard('Screen partition curve',
      chart(responseChart(c.partition_curve, 'size_um', ['to_oversize_pct'],
        {size_um: 'Particle size (µm)', to_oversize_pct: 'To oversize (%)'}, 'Screen partition'))));
  if (c.ep_by_size) panels.push(sectionCard('Sharpness against particle size',
    chart(epBySizeChart(c.ep_by_size))));
  if (c.size_window) panels.push(sectionCard('Separation window', chart(sizeWindowChart(c.size_window))));
  if (c.settling_curve) panels.push(sectionCard('Hindered settling', chart(settlingChart(c.settling_curve))));
  if (c.dilution_response) panels.push(sectionCard('Dilution-water response',
    chart(responseChart(c.dilution_response, 'value', ['classifier_d50_um', 'pellet_fines_tph'],
      {...LABELS, value: xlab}))));
  if (c.splitter_response) panels.push(sectionCard('Splitter response',
    chart(responseChart(c.splitter_response, 'value', ['fines_fe_pct', 'fe_recovery_pct'],
      {...LABELS, value: xlab}))));
  if (c.cut_response) panels.push(sectionCard('Table-cut response',
    chart(responseChart(c.cut_response, 'value', ['fines_fe_pct', 'fe_recovery_pct'], {...LABELS, value: xlab}))));
  if (c.field_response) panels.push(sectionCard('Field-intensity response',
    chart(responseChart(c.field_response, 'value', ['pellet_fines_fe_pct', 'fe_recovery_pct'],
      {...LABELS, value: xlab}))));
  if (c.capture_curve) panels.push(sectionCard('Magnetic capture selectivity',
    chart(captureCurveChart(c.capture_curve))));
  if (c.size_recovery) panels.push(sectionCard('Magnetic capture window',
    chart(responseChart(c.size_recovery, 'size_um', ['recovery_pct'],
      {size_um: 'Particle size (µm)', recovery_pct: 'Recovery (%)'}, 'WHIMS size window'))));
  if (c.pressure_response) panels.push(sectionCard('Manifold-pressure response',
    chart(responseChart(c.pressure_response, 'value', ['fines_fe_pct', 'slimes_to_tailings_pct'],
      {...LABELS, value: xlab}))));
  if (c.reclaim_response) panels.push(sectionCard('Pond-reclaim response',
    chart(responseChart(c.reclaim_response, 'value', ['fresh_water_m3_t', 'water_recycle_pct'],
      {...LABELS, value: xlab}))));
  if (c.flux_curve) panels.push(sectionCard('Batch-flux curve', chart(fluxChart(c.flux_curve))));
  if (c.grade_recovery) panels.push(sectionCard('Grade-recovery envelope',
    chart(gradeRecoveryChart(c.grade_recovery))));
  if (!panels.length) panels.push(note('No characteristic curves are defined for this unit.'));
  root.append(grid(2, panels));
  root.append(note(`<b>Model:</b> ${d.model}. Feed stream <code>${d.stream_in}</code> → product stream ` +
    `<code>${d.stream_out}</code>. Curves are evaluated around the current operating point with the full twin, ` +
    'so they already include the circuit recycles.'));
}
