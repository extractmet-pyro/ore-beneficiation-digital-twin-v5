// Live process twin: flowsheet schematic, 3-D plant, tag board, soft sensors, streams and Sankey.
import * as api from '../api/client.js';
import * as S from '../state.js';
import {STATUS_COLOR} from '../utils/constants.js';
import {chart, constraintChart, densityHistogram, liberationChart, productSplitChart, psdChart,
  sankeyChart, trend} from '../charts/plots.js';
import {alarmPanel, pageHeader, sourceLegend} from '../ui/components.js';
import {grid, h, note, select, table, tabs} from '../ui/dom.js';
import {fmt} from '../utils/format.js';
import {mountFlowsheet} from '../viz/flowsheet.js';
import {constraintTable, kpiCardsFromDict, sectionCard, streamTable} from './common.js';

function unitStatusMap(constraints) {
  const map = {};
  const link = {primary_power: 'primary_crusher', secondary_power: 'secondary_crusher',
    tertiary_power: 'tertiary_crusher', recrush_circulating_load: 'tertiary_crusher',
    scrubber_power: 'scrubber', scrubber_residence: 'scrubber', clay_removal: 'scrubber',
    screen_loading: 'sizing_screen', lump_fe: 'lump_jig', lump_al2o3: 'lump_jig', lump_sio2: 'lump_jig',
    lump_yield: 'lump_jig', jig_bed_looseness: 'lump_jig', lump_jig_loading: 'lump_jig',
    fines_jig_loading: 'fines_jig', classifier_loading: 'spiral_classifier',
    spiral_cyclone_pressure: 'spiral_cyclone', deslime_cyclone_pressure: 'deslime_cyclone',
    spiral_load: 'spirals', fines_fe: 'spirals', table_load: 'shaking_tables',
    whims_load: 'whims', pellet_fe: 'whims', slimes_loss: 'deslime_cyclone',
    tails_rake_torque: 'tails_thickener', tails_overflow_tss: 'tails_thickener',
    tails_uf_solids: 'tails_thickener', fresh_water: 'water_recovery', tailings_fe: 'spirals'};
  for (const c of constraints) {
    const u = link[c.key];
    if (!u) continue;
    const rank = {normal: 0, caution: 1, alarm: 2};
    if ((rank[c.status] ?? 0) > (rank[map[u]] ?? 0)) map[u] = c.status;
  }
  return map;
}

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const [live, fs] = await Promise.all([api.get('live', {plant_id: pid}), api.get('flowsheet', {plant_id: pid})]);
  const status = unitStatusMap(live.constraints);
  root.append(pageHeader('Live process twin', {subtitle: 'Measured tags, twin model view and the residual between them',
    timestamp: live.timestamp, event: (live.events || []).map(e => e.label).join(', ') || null}));
  root.append(kpiCardsFromDict(live.kpis, ['lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct', 'pellet_fines_fe_pct',
    'throughput_tph', 'mass_yield_pct', 'fe_recovery_pct', 'total_power_mw'], {source: 'measured'}));
  let dispose = null;

  root.append(tabs([
    {label: '🗺️ Flowsheet', render: pane => {
      const holder = h('div', {class: 'canvas-wrap', style: {height: '640px'}});
      pane.append(holder);
      mountFlowsheet(holder, fs, status, S.get('theme') !== 'light', live.kpis, u => ctx.go('units', {unit: u}));
      pane.append(note('Click any parameter box to open that unit in <b>Unit operations</b>. Scroll to zoom, drag to pan.'));
    }},
    {label: '🧊 3-D plant', render: async pane => {
      const holder = h('div', {style: {height: '620px'}});
      pane.append(holder);
      try {
        const {mountScene} = await import('../viz/scene3d.js');
        const units = (await api.get('units')).units.map(u => ({unit_id: u.id, label: u.label,
          status: status[u.id] || 'normal', info: `${u.area} · ${u.model}`}));
        dispose = mountScene(holder, {units, dark: S.get('theme') !== 'light'});
      } catch (e) {
        pane.append(note(`3-D scene unavailable: ${e.message}`, 'warn'));
      }
    }},
    {label: '🏷️ Tag board', render: async pane => {
      const areas = [...new Set(live.tags.map(t => t.area))];
      let filter = 'all';
      const body = h('div', {});
      const draw = () => {
        body.innerHTML = '';
        const rows = live.tags.filter(t => filter === 'all' || t.area === filter);
        body.append(table(rows.map(t => ({Tag: t.tag, Description: t.label, Area: t.area, Type: t.type,
          Value: t.value, Unit: t.unit, 'Twin model': t.model_value, 'Residual %': t.residual_pct, Quality: t.quality})),
        ['Tag', 'Description', 'Area', 'Type', {key: 'Value', num: true, fmt: '.4g'}, 'Unit',
          {key: 'Twin model', num: true, fmt: '.4g'}, {key: 'Residual %', num: true, fmt: '.2f'},
          {key: 'Quality', render: v => h('span', {class: 'badge', style: {background: STATUS_COLOR[v] || '#78909c'}}, v)}],
        {height: 560, cellClass: (k, v) => (k === 'Residual %' && typeof v === 'number' && Math.abs(v) > 10 ? 'bad' : '')}));
      };
      pane.append(h('div', {class: 'row mb'}, h('label', {}, 'Area'),
        select([{value: 'all', label: 'All areas'}, ...areas.map(a => ({value: a, label: a}))], 'all',
          {onchange: v => { filter = v; draw(); }})), body);
      draw();
      // step_h matches the pre-computed replay grid (REPLAY_STEPS_PER_HOUR); off-grid steps
      // make the backend re-solve every sample instead of serving it from the cache.
      const tt = await api.get('tag_trend', {plant_id: pid, hours: 24, step_h: 0.5,
        tags: '302_AIC_025,302_AIC_024,301_DIC_020,201_SIC_010,601_DIC_051,801_JIC_071'});
      const series = {};
      for (const k of Object.keys(tt)) if (!['timestamps', 'hours', 'plant_id', 'view', 'mock'].includes(k))
        series[k] = {y: tt[k], source: 'measured'};
      pane.append(sectionCard('Key instruments — last 24 h', chart(trend(tt.timestamps, series, '', 320))));
    }},
    {label: '🧠 Soft sensors', render: pane => {
      pane.append(table(live.soft_sensors.map(s => ({Sensor: s.label, Unit: s.unit, Estimate: s.value,
        'Twin value': s.measured, Error: s.error, 'σ': s.sigma,
        '95 % interval': s.interval_95 ? `${s.interval_95[0]} – ${s.interval_95[1]}` : '—',
        Basis: s.basis, 'Valid (min)': s.valid_window_min, Drives: s.drives})),
      ['Sensor', 'Unit', {key: 'Estimate', num: true, fmt: '.3f'}, {key: 'Twin value', num: true, fmt: '.3f'},
        {key: 'Error', num: true, fmt: '+.3f'}, {key: 'σ', num: true, fmt: '.3f'}, '95 % interval', 'Basis',
        {key: 'Valid (min)', num: true}, 'Drives'], {height: 420}));
      pane.append(note('A gravity plant carries very few analysers, so most of what an operator needs to know ' +
        'here is inferred rather than measured. Each soft sensor carries its own uncertainty and a validity ' +
        'window, and the machine-learning layer can correct its bias (see the <b>Machine learning</b> page).'));
    }},
    {label: '🔬 Streams & size', render: pane => {
      pane.append(sectionCard('Stream table', streamTable(fs.streams)));
      const keyStreams = ['S01_rom', 'S06_lumps', 'S08_lump_ore', 'S11_classifier_sand',
        'S14_spiral_cyclone_uf', 'S19_ore_fines', 'S27_pellet_fines'];
      const sel = Object.fromEntries(keyStreams.filter(k => fs.streams[k]).map(k => [k.replace(/^S\d+_/, '').replace(/_/g, ' '), fs.streams[k]]));
      pane.append(grid(2, chart(psdChart(sel)), chart(liberationChart(sel))));
    }},
    {label: '🔀 Mass flow', render: pane => {
      pane.append(chart(sankeyChart(fs.sankey)));
      pane.append(chart(productSplitChart(live.kpis)));
      pane.append(sectionCard('Water balance (m³/h)', table(Object.entries(live.water).map(([k, v]) =>
        ({Item: k.replace(/_/g, ' '), Value: v})), ['Item', {key: 'Value', num: true, fmt: ',.1f'}])));
    }},
    {label: '🚨 Alarms & constraints', render: pane => {
      pane.append(alarmPanel(live.alarms.map(a => ({severity: a.severity, unit_id: a.group,
        message: `${a.label}${a.value !== null && a.value !== undefined ? `: ${fmt(a.value, '.4g')} ${a.unit} (limit ${fmt(a.limit, '.4g')})` : ''}`,
        hint: `priority ${a.priority}`})), {title: 'Active alarms'}));
      pane.append(chart(constraintChart(live.constraints)));
      pane.append(sectionCard('All constraints', constraintTable(live.constraints)));
    }},
  ], 'live'));
  root.append(sourceLegend());
  return () => { if (dispose) dispose(); };
}
