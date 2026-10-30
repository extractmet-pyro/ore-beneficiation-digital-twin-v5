// Helpers shared by the page modules: KPI cards from a KPI dict, constraint tables, stream tables.
import {KPI_FMT, KPI_LABEL, LOWER_IS_BETTER, STATUS_COLOR} from '../utils/constants.js';
import {fmt, humanise} from '../utils/format.js';
import {kpiGrid} from '../ui/components.js';
import {grid, h, table} from '../ui/dom.js';

export function kpiCardsFromDict(kpis, keys, {targets = {}, baseline = {}, source = 'simulated', status = {}} = {}) {
  const cards = keys.filter(k => kpis[k] !== undefined && kpis[k] !== null).map(k => {
    const [label, unit] = KPI_LABEL[k] || [humanise(k), ''];
    return {key: k, label, unit, value: kpis[k], target: targets[k], baseline: baseline[k], source,
      status: status[k] || 'normal', higher_is_better: !LOWER_IS_BETTER.has(k)};
  });
  return kpiGrid(cards, Math.min(cards.length, 4));
}

export const kpiRows = kpis => Object.entries(kpis).map(([k, v]) => {
  const [label, unit] = KPI_LABEL[k] || [humanise(k), ''];
  return {Metric: label, Value: typeof v === 'number' ? Number(fmt(v, KPI_FMT[k] || '.4g').replace(/,/g, '')) : v, Unit: unit, Key: k};
});

export function constraintTable(rows) {
  return table(rows.map(r => ({Priority: r.priority, Constraint: r.label, Group: r.group, Value: r.value,
    Limit: r.limit_hi ? `${r.limit} – ${r.limit_hi}` : r.limit, Unit: r.unit, 'Margin %': r.margin_pct,
    Status: r.status, Rationale: r.rationale})),
  [{key: 'Priority', num: true}, 'Constraint', 'Group', {key: 'Value', num: true, fmt: '.4g'},
    'Limit', 'Unit', {key: 'Margin %', num: true, fmt: '.1f'},
    {key: 'Status', render: v => h('span', {class: `badge s-${v}`, style: {background: STATUS_COLOR[v] || '#78909c'}}, String(v).toUpperCase())},
    'Rationale'], {height: 460, cellClass: (k, v) => (k === 'Margin %' && typeof v === 'number' && v < 0 ? 'bad' : '')});
}

export function streamTable(streams) {
  return table(Object.entries(streams).map(([name, s]) => ({Stream: name.replace(/_/g, ' '), 't/h': s.solids_tph,
    'Water m³/h': s.water_m3_h, '% solids': s.solids_pct, '% Fe': s.fe_pct, '% SiO₂': s.sio2_pct,
    '% Al₂O₃': s.al2o3_pct, 'SG': s.sg, 'P80 µm': s.p80_um, '+10 mm %': s.plus_10mm_pct,
    '−150 µm %': s.minus_150um_pct, 'Liberation %': s.liberation_pct, 'Fe t/h': s.fe_tph})),
  ['Stream', {key: 't/h', num: true, fmt: ',.1f'}, {key: 'Water m³/h', num: true, fmt: ',.0f'},
    {key: '% solids', num: true, fmt: '.1f'}, {key: '% Fe', num: true, fmt: '.2f'},
    {key: '% SiO₂', num: true, fmt: '.2f'}, {key: '% Al₂O₃', num: true, fmt: '.2f'},
    {key: 'SG', num: true, fmt: '.2f'}, {key: 'P80 µm', num: true, fmt: ',.0f'},
    {key: '+10 mm %', num: true, fmt: '.1f'}, {key: '−150 µm %', num: true, fmt: '.1f'},
    {key: 'Liberation %', num: true, fmt: '.1f'}, {key: 'Fe t/h', num: true, fmt: '.1f'}],
  {height: 520});
}

export function unitStateTable(state) {
  return table(Object.entries(state).map(([k, v]) => ({Parameter: humanise(k), Value: v})),
    ['Parameter', {key: 'Value', num: true, fmt: '.4g'}], {height: 420});
}

export const infoNote = (text, kind = '') => h('div', {class: `note ${kind}`, html: text});

export function sectionCard(title, ...children) {
  return h('div', {class: 'card'}, h('h4', {}, title), ...children.filter(Boolean));
}

export const twoCol = (a, b) => grid(2, a, b);
