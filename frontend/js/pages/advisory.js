// Control advisory: gain matrix, RGA pairing, instrument readiness and plain-language operator guidance.
import * as api from '../api/client.js';
import {STATUS_COLOR} from '../utils/constants.js';
import {chart, gainHeatmap} from '../charts/plots.js';
import {pageHeader} from '../ui/components.js';
import {grid, h, note, table, tabs} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {sectionCard} from './common.js';

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const adv = await api.get('mpc_advisory', {plant_id: pid});
  const rd = adv.readiness;
  root.append(pageHeader('Control advisory', {subtitle: 'What the twin recommends before any loop is closed'}));
  root.append(note(`Readiness for closed loop: <b>${rd.ready_for_closed_loop ? 'YES' : 'NO'}</b> ` +
    `(${fmt(rd.readiness_score_pct, '.0f')} % of the required instruments healthy). ${rd.recommendation}`,
  rd.ready_for_closed_loop ? 'ok' : 'warn'));

  root.append(tabs([
    {label: '🧭 Guidance', render: pane => {
      if (!adv.guidance.length) pane.append(note('No advisories — the operating point sits inside the recommended envelope.', 'ok'));
      pane.append(h('div', {}, adv.guidance.map(g => h('div', {class: `adv ${g.status || ''}`},
        h('b', {}, g.action),
        h('small', {}, `${g.constraint}: ${fmt(g.value, '.4g')} ${g.unit} against a limit of ` +
          `${fmt(g.limit, '.4g')} ${g.unit} · priority ${g.priority} · status ${g.status}`)))));
    }},
    {label: '🔗 Pairing (RGA)', render: pane => {
      pane.append(chart(gainHeatmap(adv.gain_matrix, adv.mv_keys, adv.cv_keys)));
      pane.append(sectionCard('Recommended pairings', table(adv.pairing.pairings.map(p => ({
        'Controlled variable': p.cv_label || humanise(p.cv), 'Manipulated variable': p.mv_label || humanise(p.mv),
        'RGA λ': p.relative_gain, Gain: p.gain, 'Interaction index': p.interaction_index, Quality: p.pairing_quality})),
      ['Controlled variable', 'Manipulated variable', {key: 'RGA λ', num: true, fmt: '.3f'},
        {key: 'Gain', num: true, fmt: '.4g'}, {key: 'Interaction index', num: true, fmt: '.3f'},
        {key: 'Quality', render: v => h('span', {class: 'badge',
          style: {background: STATUS_COLOR[{good: 'normal', fair: 'caution', poor: 'alarm'}[v] || 'offline']}}, v)}])));
      pane.append(note(`Interaction summary: condition number <b>${fmt(adv.pairing.condition_number, '.0f')}</b> ` +
        `(${adv.pairing.conditioning}). ${adv.pairing.note} Loops with λ far from 1 interact strongly and belong in ` +
        'the multivariable controller rather than in single PID loops.'));
    }},
    {label: '📟 Readiness', render: pane => {
      pane.append(table(rd.instruments.map(i => ({Tag: i.tag, Instrument: i.label, Status: i.status,
        Ready: i.ready ? '✔' : '✘', Impact: i.impact})),
      ['Tag', 'Instrument', {key: 'Status', render: v => h('span', {class: 'badge',
        style: {background: STATUS_COLOR[v] || '#78909c'}}, v)}, 'Ready', 'Impact'], {height: 420}));
      pane.append(note(`Model conditioning for control: <b>${fmt(rd.model_condition_number, ',.0f')}</b>. ` +
        'A very large condition number means some directions in the gain matrix are nearly unobservable — ' +
        'move those variables slowly and lean on the twin rather than on the identified model alone.'));
    }},
  ], 'advisory'));
}
