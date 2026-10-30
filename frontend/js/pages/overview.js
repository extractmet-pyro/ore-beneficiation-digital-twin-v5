// Executive overview: quality against contract, recovery, energy, water, cost and shift performance.
import * as api from '../api/client.js';
import {AREA_COLORS, HEADLINE_KPIS, KPI_LABEL, PRODUCTS} from '../utils/constants.js';
import {chart, constraintChart, productQualityChart, productSplitChart, smallMultiples, stackedBar,
  trend, waterfall} from '../charts/plots.js';
import {pageHeader, sourceLegend} from '../ui/components.js';
import {grid, h, note, table, tabs} from '../ui/dom.js';
import {fmt} from '../utils/format.js';
import {kpiCardsFromDict, sectionCard} from './common.js';

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const [ov, plant, shifts, live] = await Promise.all([
    api.get('overview', {plant_id: pid}), api.get('plant', {plant_id: pid}),
    api.get('shifts', {plant_id: pid, shifts: 6}), api.get('live', {plant_id: pid})]);
  const design = plant.flowsheet;
  root.append(pageHeader('Executive overview', {subtitle: `${ov.name} · ${ov.product_spec}`, timestamp: ov.timestamp,
    event: (ov.events || []).map(e => e.label).join(', ') || null}));
  root.append(kpiCardsFromDict(ov.kpis, HEADLINE_KPIS,
    {targets: {lump_fe_pct: design.design_lump_fe_pct, lump_al2o3_pct: design.design_lump_al2o3_pct,
      fines_fe_pct: design.design_fines_fe_pct, fe_recovery_pct: design.design_fe_recovery_pct},
    source: 'measured'}));
  root.append(sourceLegend());

  root.append(tabs([
    {label: '📈 Trends', render: async pane => {
      const keys = ['lump_fe_pct', 'lump_al2o3_pct', 'fines_fe_pct', 'fe_recovery_pct',
        'mass_yield_pct', 'throughput_tph'];
      const tr = await api.get('trend', {plant_id: pid, hours: 24, step_h: 0.5, keys: keys.join(',')});
      const panels = keys.map(k => ({title: (KPI_LABEL[k] || [k])[0], series: {[k]: {y: tr[k], source: 'measured'}},
        target: {lump_fe_pct: design.design_lump_fe_pct, lump_al2o3_pct: design.design_lump_al2o3_pct,
          fines_fe_pct: design.design_fines_fe_pct, fe_recovery_pct: design.design_fe_recovery_pct}[k]}));
      pane.append(chart(smallMultiples(tr.timestamps, panels, 3, 200)));
      pane.append(sectionCard('Statistics over the window', table(Object.keys(tr).filter(k => k.endsWith('_stats'))
        .map(k => ({Metric: (KPI_LABEL[k.replace('_stats', '')] || [k])[0], ...tr[k]})),
      ['Metric', {key: 'mean', num: true, fmt: '.3f'}, {key: 'min', num: true, fmt: '.3f'},
        {key: 'max', num: true, fmt: '.3f'}, {key: 'std', num: true, fmt: '.3f'}])));
    }},
    {label: '📦 Products', render: pane => {
      pane.append(grid(2, chart(productSplitChart(ov.kpis)), chart(productQualityChart(ov.kpis, design))));
      pane.append(sectionCard('Product book',
        table(PRODUCTS.map(p => ({Product: p.label, Use: p.use, 't/h': ov.kpis[p.tph],
          'Yield %': ov.kpis[p.yieldKey], '% Fe': ov.kpis[p.fe], '% SiO₂': ov.kpis[p.si],
          '% Al₂O₃': ov.kpis[p.al],
          'Price USD/dmt': ov.kpis[{lump: 'realised_lump_usd_dmt', fines: 'realised_fines_usd_dmt',
            pellet: 'realised_pellet_usd_dmt'}[p.key]]})),
        ['Product', 'Use', {key: 't/h', num: true, fmt: ',.1f'}, {key: 'Yield %', num: true, fmt: '.2f'},
          {key: '% Fe', num: true, fmt: '.2f'}, {key: '% SiO₂', num: true, fmt: '.2f'},
          {key: '% Al₂O₃', num: true, fmt: '.3f'}, {key: 'Price USD/dmt', num: true, fmt: '.2f'}])));
      pane.append(note('Alumina is the binding commercial constraint on this ore: a lump above the ' +
        'contractual free allowance is discounted whatever its iron grade, which is why scrubber duty ' +
        'and jig cut density are the two handles the controller works hardest.'));
    }},
    {label: '🏭 Areas', render: pane => {
      pane.append(grid(3, ov.areas.map(a => h('div', {class: 'tile', style: {borderLeft: `4px solid ${AREA_COLORS[a.id]}`}},
        h('b', {}, `${a.id} · ${a.name}`),
        h('small', {}, `${fmt(a.power_kw, ',.0f')} kW`),
        table(Object.entries(a.values).map(([k, v]) => ({Metric: k.replace(/_/g, ' '), Value: v})),
          ['Metric', {key: 'Value', num: true, fmt: '.4g'}])))));
      pane.append(grid(2, sectionCard('Power split', chart(stackedBar(ov.power, 'Power by area (kW)', 'kW', 380))),
        sectionCard('Operating cost', chart(stackedBar(ov.economics, 'Cost split (USD/h)', 'USD/h', 380)))));
    }},
    {label: '💰 Value', render: pane => {
      const e = ov.economics;
      pane.append(chart(waterfall(['Revenue', 'Mining', 'Power', 'Water', 'Flocculant', 'Wear parts', 'Fixed', 'Margin'],
        [e.revenue_usd_h, -e.mining_usd_h, -e.power_usd_h, -e.water_usd_h, -e.flocculant_usd_h,
          -e.wear_parts_usd_h, -e.fixed_usd_h, 0], 'Margin bridge (USD/h)')));
      pane.append(grid(2,
        sectionCard('Realised prices', table([
          {Item: 'Index (62 % Fe)', Value: plant.economics.iron_ore_index_usd_dmt, Unit: 'USD/dmt'},
          {Item: 'Lump premium', Value: plant.economics.lump_premium_usd_dmt, Unit: 'USD/dmt'},
          {Item: 'Pellet-feed premium', Value: plant.economics.pellet_feed_premium_usd_dmt, Unit: 'USD/dmt'},
          {Item: 'Alumina free allowance', Value: plant.economics.alumina_free_allowance_pct, Unit: '% Al₂O₃'},
          {Item: 'Alumina penalty', Value: plant.economics.alumina_penalty_usd_per_pct, Unit: 'USD per %'},
          {Item: 'Freight', Value: -plant.economics.freight_usd_dmt, Unit: 'USD/dmt'},
          {Item: 'Realised — lump', Value: e.lump_price_usd_dmt, Unit: 'USD/dmt'},
          {Item: 'Realised — sinter fines', Value: e.fines_price_usd_dmt, Unit: 'USD/dmt'},
          {Item: 'Realised — pellet feed', Value: e.pellet_price_usd_dmt, Unit: 'USD/dmt'}],
        ['Item', {key: 'Value', num: true, fmt: '.2f'}, 'Unit'])),
        sectionCard('Shift performance', table(shifts.shifts.map(s => ({Shift: s.shift, 't/h': s.saleable_tph,
          'Tonnes': s.tonnes, 'Lump % Fe': s.lump_fe_pct, 'Lump % Al₂O₃': s.lump_al2o3_pct,
          'Fines % Fe': s.fines_fe_pct, 'Rec %': s.fe_recovery_pct, 'USD/h': s.margin_usd_h})),
        ['Shift', {key: 't/h', num: true, fmt: ',.1f'}, {key: 'Tonnes', num: true, fmt: ',.0f'},
          {key: 'Lump % Fe', num: true, fmt: '.2f'}, {key: 'Lump % Al₂O₃', num: true, fmt: '.3f'},
          {key: 'Fines % Fe', num: true, fmt: '.2f'}, {key: 'Rec %', num: true, fmt: '.1f'},
          {key: 'USD/h', num: true, fmt: ',.0f'}]))));
    }},
    {label: '⚠️ Constraints', render: pane => {
      pane.append(chart(constraintChart(live.constraints)));
      pane.append(sectionCard('Water balance', table(Object.entries(ov.water).map(([k, v]) =>
        ({Item: k.replace(/_/g, ' '), Value: v})), ['Item', {key: 'Value', num: true, fmt: ',.1f'}])));
    }},
  ], 'overview'));
}
