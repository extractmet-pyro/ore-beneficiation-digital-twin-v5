// Data quality: instrument coverage, noise, calibration bias and the gate on closed-loop control.
import * as api from '../api/client.js';
import {STATUS_COLOR} from '../utils/constants.js';
import {chart, qualityChart} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {grid, h, note, numberInput, table, tabs} from '../ui/dom.js';
import {fmt} from '../utils/format.js';
import {sectionCard} from './common.js';

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const hrs = numberInput(24, {min: 6, max: 168, step: 6});
  const box = h('div', {});
  root.append(pageHeader('Data quality', {subtitle: 'Nothing downstream is better than the instruments feeding it'}));
  root.append(h('div', {class: 'row mb'}, h('label', {}, 'Window (h)'), hrs), box);

  const draw = async () => {
    box.innerHTML = '';
    box.append(h('div', {class: 'loading'}, h('span', {class: 'spinner'}), 'Scoring the instrument set…'));
    const [rep, miss] = await Promise.all([api.get('data_quality', {plant_id: pid, hours: hrs.getValue(), step_h: 0.5}),
      api.get('data_missing', {plant_id: pid, hours: 48})]);
    box.innerHTML = '';
    box.append(note(`Quality score <b>${fmt(rep.quality_score_pct, '.1f')} %</b> — ` +
      `${rep.counts.good} good · ${rep.counts.suspect} suspect · ${rep.counts.bad} bad. Gate: <b>${rep.gate}</b>.`,
    rep.counts.bad ? 'err' : (rep.counts.suspect ? 'warn' : 'ok')));
    box.append(tabs([
      {label: '🏷️ Instruments', render: pane => {
        pane.append(table(rep.tags.map(t => ({Tag: t.tag, Instrument: t.label, Area: t.area, Type: t.type,
          'Coverage %': t.coverage_pct, 'Noise %': t.noise_pct, 'Bias vs twin %': t.bias_pct, Frozen: t.frozen ? 'yes' : '—',
          Mean: t.mean, 'σ': t.std, 'Sample (s)': t.sample_s, Status: t.status})),
        ['Tag', 'Instrument', 'Area', 'Type', {key: 'Coverage %', num: true, fmt: '.1f'},
          {key: 'Noise %', num: true, fmt: '.2f'}, {key: 'Bias vs twin %', num: true, fmt: '+.2f'}, 'Frozen',
          {key: 'Mean', num: true, fmt: '.4g'}, {key: 'σ', num: true, fmt: '.4g'}, {key: 'Sample (s)', num: true},
          {key: 'Status', render: v => h('span', {class: 'badge', style: {background: STATUS_COLOR[v] || '#78909c'}}, v)}],
        {height: 520}));
      }},
      {label: '🗺️ Health map', render: pane => {
        pane.append(chart(qualityChart(rep.tags)));
        pane.append(sectionCard('Recommended repairs', rep.recommendations.length
          ? table(rep.recommendations.map(r => ({Action: r})), ['Action'])
          : note('No instrument repairs outstanding.', 'ok')));
      }},
      {label: '🕳️ Availability', render: pane => {
        pane.append(table(miss.tags.map(t => ({Tag: t.tag, Instrument: t.label, 'Gaps (h)': t.gaps_h,
          'Availability %': t.availability_pct})),
        ['Tag', 'Instrument', {key: 'Gaps (h)', num: true, fmt: '.0f'}, {key: 'Availability %', num: true, fmt: '.2f'}],
        {height: 460, cellClass: (k, v) => (k === 'Availability %' && typeof v === 'number' && v < 95 ? 'bad' : '')}));
      }},
    ], 'quality'));
  };
  hrs.addEventListener('change', draw);
  await draw();
}
