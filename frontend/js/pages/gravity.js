// Gravity analysis: the page a gravity metallurgist opens first.
//
// Washability says what density separation *could* achieve on this ore; the Tromp curves say what
// each machine actually achieves; the Ep-by-size and window charts say why the plant needs three
// different gravity machines instead of one. Reading them together is how you tell an ore problem
// from a machine problem.
import * as api from '../api/client.js';
import {chart, densityHistogram, epBySizeChart, gradeRecoveryChart, sizeWindowChart, trompChart,
  washabilityChart} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {grid, h, note, select, table, tabs} from '../ui/dom.js';
import {fmt} from '../utils/format.js';
import {sectionCard} from './common.js';

const GRAVITY_UNITS = [
  {id: 'lump_jig', label: 'Lump jig', epKey: 'ep_at_10mm', cutKey: 'cut_sg_achieved',
   blurb: 'Sharp on lumps, useless below about 1 mm — which is why the fines never see it.'},
  {id: 'fines_jig', label: 'Fines jig', epKey: 'ep_at_1mm', cutKey: 'cut_sg_achieved',
   blurb: 'Takes the +2 mm sand, where a jig is still workable but no longer sharp.'},
  {id: 'spirals', label: 'Spiral concentrators', epKey: 'ep_at_500um', cutKey: 'cut_sg_conc',
   blurb: 'The workhorse from about 2 mm down to 75 µm, and the only unit making three products.'},
  {id: 'shaking_tables', label: 'Shaking tables', epKey: 'ep_at_200um', cutKey: 'cut_sg_conc',
   blurb: 'The sharpest cut in the plant, but only on a narrow, closely sized, deslimed feed.'},
];

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const [wash, sim] = await Promise.all([api.get('washability', {plant_id: pid}),
    api.post('simulate', {plant_id: pid, include_streams: false})]);
  root.append(pageHeader('Gravity analysis', {
    subtitle: 'Washability, partition curves and the size limits of each separator'}));
  root.append(note(`Concentration criterion <b>${fmt(wash.concentration_criterion, '.2f')}</b> — ` +
    `(ρ<sub>hematite</sub> − 1) / (ρ<sub>quartz</sub> − 1). Above 2.5 a density separation is easy down to ` +
    'about 75 µm; between 1.5 and 2.5 it works only above roughly 1 mm. That single number is why this ' +
    'flowsheet can be built out of jigs, spirals and tables at all, and why the material finer than the ' +
    'gravity window is sent to the WHIMS instead.'));

  root.append(tabs([
    {label: '⚖️ Washability', render: pane => {
      pane.append(chart(washabilityChart(wash.streams)));
      pane.append(note('Each curve is a float-and-sink analysis: cut anywhere along it and you read off the ' +
        'mass you would recover and the grade it would carry. The gap between the ROM curve and the lump-ore ' +
        'curve is what the jig actually delivered; the gap between the lump-ore curve and the ideal is what ' +
        'a sharper cut could still win.'));
      pane.append(chart(densityHistogram(wash.streams)));
      pane.append(sectionCard('Density fractions', tabs(Object.entries(wash.streams).map(([name, d]) => ({
        label: name,
        render: q => q.append(table(d.sg_mid.map((sg, i) => ({
          'Density (SG)': sg, 'Mass %': d.mass_pct[i], '% Fe': d.fe_pct[i],
          'Cumulative float mass %': d.cum_float_mass_pct[i], 'Cumulative float % Fe': d.cum_float_fe_pct[i]})),
        [{key: 'Density (SG)', num: true, fmt: '.2f'}, {key: 'Mass %', num: true, fmt: '.2f'},
          {key: '% Fe', num: true, fmt: '.2f'}, {key: 'Cumulative float mass %', num: true, fmt: '.2f'},
          {key: 'Cumulative float % Fe', num: true, fmt: '.2f'}]))})), 'wash-frac')));
    }},
    {label: '✂️ Partition curves', render: async pane => {
      pane.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Evaluating each separator…'));
      const details = await Promise.all(GRAVITY_UNITS.map(u => api.get('unit', {unit_id: u.id, plant_id: pid})));
      pane.innerHTML = '';
      pane.append(grid(2, details.map((d, i) => {
        const u = GRAVITY_UNITS[i];
        const pc = (d.curves || {}).partition_curve;
        return sectionCard(u.label,
          h('div', {class: 'subtitle'}, u.blurb),
          pc && pc[0] && pc[0].sg !== undefined
            ? chart(trompChart(pc, d.state[u.cutKey], `${u.label} — Tromp curve`))
            : note('No density partition curve for this unit.'));
      })));
      pane.append(sectionCard('Cut densities and sharpness', table(details.map((d, i) => {
        const u = GRAVITY_UNITS[i];
        return {Unit: u.label, 'Cut density (SG)': d.state[u.cutKey], 'Ep (SG)': d.state[u.epKey],
          'Measured at': u.epKey.replace('ep_at_', ''),
          'Feed t/h': d.state.feed_tph, 'Conc. % Fe': d.state.conc_fe_pct,
          'Fe recovery %': d.state.fe_recovery_pct};
      }), ['Unit', {key: 'Cut density (SG)', num: true, fmt: '.3f'}, {key: 'Ep (SG)', num: true, fmt: '.3f'},
        'Measured at', {key: 'Feed t/h', num: true, fmt: ',.1f'}, {key: 'Conc. % Fe', num: true, fmt: '.2f'},
        {key: 'Fe recovery %', num: true, fmt: '.2f'}])));
      pane.append(note('A lower Ep is a sharper separation. Read these against the size each is quoted at: ' +
        'the jig Ep at 10 mm is excellent, the same jig at 1 mm is not, and that is the whole argument for ' +
        'splitting the circuit by size before separating by density.'));
    }},
    {label: '📏 Size limits', render: async pane => {
      pane.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Loading separator windows…'));
      const [jig, spiral, tbl] = await Promise.all([
        api.get('unit', {unit_id: 'lump_jig', plant_id: pid}),
        api.get('unit', {unit_id: 'spirals', plant_id: pid}),
        api.get('unit', {unit_id: 'shaking_tables', plant_id: pid})]);
      pane.innerHTML = '';
      pane.append(grid(2,
        sectionCard('Jig sharpness against size',
          (jig.curves || {}).ep_by_size ? chart(epBySizeChart(jig.curves.ep_by_size,
            'Lump jig — Ep rises steeply below 3 mm')) : note('No curve available.')),
        sectionCard('Spiral working window',
          (spiral.curves || {}).size_window ? chart(sizeWindowChart(spiral.curves.size_window,
            'Spiral concentrator — 2 mm to 75 µm')) : note('No curve available.')),
        sectionCard('Table working window',
          (tbl.curves || {}).size_window ? chart(sizeWindowChart(tbl.curves.size_window,
            'Shaking table — 1.8 mm to 40 µm')) : note('No curve available.')),
        sectionCard('What the windows mean',
          note('Material coarser than a machine\'s window short-circuits it; material finer is swept out ' +
            'hydraulically whatever its density. The three windows overlap deliberately, so every size ' +
            'fraction in the plant is treated by the machine that is sharp at that size — and the fraction ' +
            'below every window goes to the desliming cyclones and the WHIMS, which separate magnetically ' +
            'and do not care about size in the same way.'))));
    }},
    {label: '📈 Grade-recovery', render: async pane => {
      pane.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Tracing the envelope…'));
      const gr = await api.get('grade_recovery', {plant_id: pid, points: 9});
      pane.innerHTML = '';
      pane.append(chart(gradeRecoveryChart(gr.curve, sim.kpis)));
      pane.append(note(gr.note));
      pane.append(table(gr.curve.map(r => ({'Cut (SG)': r.cut_sg, 'Lump t/h': r.lump_tph,
        'Lump % Fe': r.lump_fe_pct, 'Lump % Al₂O₃': r.lump_al2o3_pct, 'Fines t/h': r.fines_tph,
        'Fines % Fe': r.fines_fe_pct, 'Yield %': r.mass_yield_pct, 'Fe recovery %': r.fe_recovery_pct,
        'Tailings % Fe': r.tailings_fe_pct, 'Margin USD/h': r.margin_usd_h})),
      [{key: 'Cut (SG)', num: true, fmt: '.3f'}, {key: 'Lump t/h', num: true, fmt: ',.1f'},
        {key: 'Lump % Fe', num: true, fmt: '.2f'}, {key: 'Lump % Al₂O₃', num: true, fmt: '.3f'},
        {key: 'Fines t/h', num: true, fmt: ',.1f'}, {key: 'Fines % Fe', num: true, fmt: '.2f'},
        {key: 'Yield %', num: true, fmt: '.2f'}, {key: 'Fe recovery %', num: true, fmt: '.2f'},
        {key: 'Tailings % Fe', num: true, fmt: '.2f'}, {key: 'Margin USD/h', num: true, fmt: ',.0f'}]));
    }},
  ], 'gravity'));
}
