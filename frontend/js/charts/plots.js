// Plotly figure factory for the ore-beneficiation desk: lazy rendering, theme-aware styling,
// one builder per chart. The gravity-specific builders — Tromp partition, washability, Ep-by-size
// and separation windows — are what make this desk readable to a gravity metallurgist.
import * as S from '../state.js';
import {SOURCE, STATUS_COLOR} from '../utils/constants.js';
import {h} from '../ui/dom.js';

export const PALETTE = ['#29b6f6', '#ffb300', '#ab47bc', '#66bb6a', '#ef5350', '#26c6da', '#ff7043', '#8d6e63', '#d4e157', '#5c6bc0'];
const line = (src, w = 2) => ({color: (SOURCE[src] || SOURCE.measured).color, dash: (SOURCE[src] || SOURCE.measured).dash, width: w});

function themed(layout, height, title, legend = true) {
  const dark = S.get('theme') !== 'light';
  const fg = dark ? '#cfd8dc' : '#263238', grid = dark ? 'rgba(144,164,174,0.18)' : 'rgba(38,50,56,0.10)';
  const ax = a => ({gridcolor: grid, zeroline: false, linecolor: grid, automargin: true, ...a});
  const L = {height, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: {family: 'Inter, Segoe UI, Roboto, sans-serif', size: 12, color: fg},
    margin: {l: 58, r: 20, t: title ? 44 : 18, b: 46}, showlegend: legend, colorway: PALETTE,
    legend: {orientation: 'h', yanchor: 'bottom', y: 1.02, x: 0, bgcolor: 'rgba(0,0,0,0)', font: {size: 11}},
    title: title ? {text: title, x: 0.01, font: {size: 14}} : undefined, hoverlabel: {font: {size: 12}}, ...layout};
  for (const k of Object.keys(L)) if (/^[xy]axis\d*$/.test(k)) L[k] = ax(L[k]);
  if (!L.xaxis) L.xaxis = ax({});
  if (!L.yaxis) L.yaxis = ax({});
  return L;
}
export const fig = (data, layout = {}, height = 320, title = null, legend = true) => ({data, layout: themed(layout, height, title, legend)});

/** Resolves once the deferred chart library has finished loading.
 *
 * Plotly is 4.4 MB and is loaded with `defer`, so it is not on the page when the first module
 * runs. Every draw goes through here; when the library is already present (a warm navigation,
 * or the test harness) this costs one microtask. */
let plotlyWait = null;
export function plotlyReady() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (!plotlyWait) {
    plotlyWait = new Promise(resolve => {
      const tick = () => (window.Plotly ? resolve(window.Plotly) : setTimeout(tick, 30));
      tick();
    });
  }
  return plotlyWait;
}

/** Div that draws the figure when it first becomes visible and follows container resizes. */
export function chart(f, cls = 'plot') {
  const el = h('div', {class: cls, style: {height: `${f.layout.height + 8}px`}});
  const draw = () => plotlyReady().then(P => {
    P.newPlot(el, f.data, f.layout, {responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ['lasso2d', 'select2d'],
      toImageButtonOptions: {format: 'png', scale: 2}});
    return P;                       // the resize observer below needs Plotly, not the graph div
  });
  if (typeof IntersectionObserver === 'undefined') { queueMicrotask(draw); return el; }
  const io = new IntersectionObserver(es => {
    if (es.some(e => e.isIntersecting)) {
      io.disconnect();
      draw().then(P => new ResizeObserver(() => el.offsetWidth && P.Plots.resize(el)).observe(el));
    }
  });
  io.observe(el);
  return el;
}

// ---------------------------------------------------------------- trends
export function trend(x, series, title = '', height = 300, lo = null, hi = null, events = []) {
  const data = Object.entries(series).map(([n, s], i) => ({x: s.x || x, y: s.y, name: n, mode: 'lines', type: 'scatter',
    yaxis: s.axis || 'y', line: s.source ? line(s.source, 1.9) : {width: 1.9, color: PALETTE[i % 10]},
    hovertemplate: `%{y:.4g} ${s.unit || ''}<extra>${n}</extra>`}));
  const shapes = [], ann = [];
  for (const [v, lab] of [[lo, 'LO'], [hi, 'HI']]) if (v !== null && v !== undefined) {
    shapes.push({type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v, line: {color: STATUS_COLOR.alarm, dash: 'dot', width: 1}});
    ann.push({xref: 'paper', x: 0, y: v, text: lab, showarrow: false, font: {size: 9, color: STATUS_COLOR.alarm}, yshift: 7});
  }
  for (const e of events || []) {
    shapes.push({type: 'rect', xref: 'x', yref: 'paper', x0: e.start, x1: e.end, y0: 0, y1: 1,
      fillcolor: e.type === 'process' ? '#e53935' : '#fb8c00', opacity: 0.12, line: {width: 0}});
    ann.push({xref: 'x', yref: 'paper', x: e.start, y: 1, text: (e.label || '').slice(0, 26), showarrow: false, font: {size: 9}, xanchor: 'left'});
  }
  return fig(data, {shapes, annotations: ann}, height, title);
}
export function smallMultiples(x, panels, cols = 3, per = 190) {
  const rows = Math.ceil(panels.length / cols);
  const data = [], layout = {grid: {rows, columns: cols, pattern: 'independent', ygap: 0.38, xgap: 0.09}, annotations: [], shapes: []};
  panels.forEach((p, i) => {
    const ax = i === 0 ? '' : String(i + 1);
    Object.entries(p.series).forEach(([n, s], j) => data.push({x: s.x || x, y: s.y, name: n, mode: 'lines', type: 'scatter',
      xaxis: `x${ax}`, yaxis: `y${ax}`, line: s.source ? line(s.source, 1.6) : {width: 1.6, color: PALETTE[j % 10]},
      showlegend: i === 0, legendgroup: n}));
    layout[`xaxis${ax}`] = {};
    layout[`yaxis${ax}`] = {title: {text: p.title, font: {size: 11}}};
    if (p.target !== null && p.target !== undefined)
      layout.shapes.push({type: 'line', xref: `x${ax} domain`, yref: `y${ax}`, x0: 0, x1: 1, y0: p.target, y1: p.target,
        line: {color: '#66bb6a', dash: 'dot', width: 1}});
    for (const [lim, col] of [[p.lo, '#e53935'], [p.hi, '#e53935']]) if (lim !== null && lim !== undefined)
      layout.shapes.push({type: 'line', xref: `x${ax} domain`, yref: `y${ax}`, x0: 0, x1: 1, y0: lim, y1: lim,
        line: {color: col, dash: 'dash', width: 1}});
  });
  return fig(data, layout, per * rows + 60);
}

// ---------------------------------------------------------------- size, liberation, separation
export function psdChart(streams, title = 'Particle size distributions') {
  const data = Object.entries(streams).map(([name, s], i) => ({x: s.psd.size_um, y: s.psd.passing_pct, name,
    mode: 'lines', line: {width: i === 0 ? 2.6 : 1.7, color: PALETTE[i % 10]}}));
  return fig(data, {xaxis: {type: 'log', title: 'Size (µm)'}, yaxis: {title: 'Cumulative % passing', range: [0, 101]},
    shapes: [{type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 80, y1: 80, line: {color: '#90a4ae', dash: 'dot', width: 1}}]},
  360, title);
}
export function liberationChart(streams, title = 'Liberation spectrum (mass by particle iron content)') {
  const g = Array.from({length: 15}, (_, i) => (i / 14 * 100).toFixed(0));
  const data = Object.entries(streams).map(([name, s], i) => ({x: g, y: s.liberation_spectrum, name, type: 'bar',
    marker: {color: PALETTE[i % 10], opacity: 0.85}}));
  return fig(data, {barmode: 'group', xaxis: {title: 'Particle iron-mineral content (%)'}, yaxis: {title: 'Mass (%)'}},
    330, title);
}
export function gradeRecoveryChart(curve, current = null) {
  const data = [
    {x: curve.map(r => r.fe_recovery_pct), y: curve.map(r => r.lump_fe_pct), mode: 'lines+markers',
      name: 'Lump ore', line: {width: 2.6, color: '#8d6e63'},
      text: curve.map(r => `cut ${r.cut_sg.toFixed(2)} SG · ${r.lump_tph.toFixed(0)} t/h · ${r.lump_al2o3_pct.toFixed(2)} % Al₂O₃`),
      hovertemplate: '%{text}<br>%{x:.2f} % rec · %{y:.2f} % Fe<extra></extra>'},
    {x: curve.map(r => r.fe_recovery_pct), y: curve.map(r => r.fines_fe_pct), mode: 'lines+markers',
      name: 'Sinter fines', line: {width: 2.2, color: '#f9a825', dash: 'dash'},
      text: curve.map(r => `cut ${r.cut_sg.toFixed(2)} SG · ${r.fines_tph.toFixed(0)} t/h`),
      hovertemplate: '%{text}<br>%{x:.2f} % rec · %{y:.2f} % Fe<extra></extra>'},
  ];
  if (current) data.push({x: [current.fe_recovery_pct], y: [current.lump_fe_pct], mode: 'markers',
    name: 'Current', marker: {size: 14, color: '#66bb6a', symbol: 'star'}});
  return fig(data, {xaxis: {title: 'Plant Fe recovery (%)'}, yaxis: {title: 'Product Fe grade (%)'}}, 350,
    'Grade-recovery envelope traced by the lump jig cut density');
}

// ---------------------------------------------------------------- gravity separation
export function trompChart(curve, cutSg = null, label = 'Tromp partition curve') {
  const shapes = [{type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 50, y1: 50,
    line: {color: '#90a4ae', dash: 'dot', width: 1}}];
  if (cutSg) shapes.push({type: 'line', yref: 'paper', x0: cutSg, x1: cutSg, y0: 0, y1: 1,
    line: {color: '#66bb6a', dash: 'dash', width: 1.6}});
  return fig([{x: curve.map(r => r.sg), y: curve.map(r => r.to_sinks_pct), mode: 'lines',
    line: {width: 2.8, color: '#5c6bc0'}, name: 'To sinks',
    hovertemplate: '%{x:.2f} SG → %{y:.1f} % to sinks<extra></extra>'}],
  {xaxis: {title: 'Particle density (SG)'}, yaxis: {title: 'Reporting to the sinks (%)', range: [0, 101]}, shapes},
  330, label + (cutSg ? ` — cut ${Number(cutSg).toFixed(2)} SG` : ''), false);
}

export function washabilityChart(streams) {
  const data = [];
  Object.entries(streams).forEach(([name, d], i) => {
    data.push({x: d.cum_float_mass_pct, y: d.cum_float_fe_pct, mode: 'lines+markers', name,
      line: {width: 2.2, color: PALETTE[i % 10]},
      hovertemplate: `${name}<br>%{x:.1f} % cumulative float · %{y:.2f} % Fe<extra></extra>`});
  });
  return fig(data, {xaxis: {title: 'Cumulative mass floating (%)'}, yaxis: {title: 'Cumulative Fe grade (%)'}},
    360, 'Washability — what density separation could achieve');
}

export function densityHistogram(streams) {
  const data = Object.entries(streams).map(([name, d], i) => ({x: d.sg_mid, y: d.mass_pct, type: 'bar',
    name, marker: {color: PALETTE[i % 10], opacity: 0.85}}));
  return fig(data, {barmode: 'group', xaxis: {title: 'Particle density (SG)'}, yaxis: {title: 'Mass (%)'}},
    330, 'Mass distribution by particle density');
}

export function epBySizeChart(rows, label = 'Probable error against particle size') {
  return fig([{x: rows.map(r => r.size_um), y: rows.map(r => r.ep), mode: 'lines',
    line: {width: 2.6, color: '#ef5350'}, name: 'Ep',
    hovertemplate: '%{x:.0f} µm → Ep %{y:.3f} SG<extra></extra>'}],
  {xaxis: {type: 'log', title: 'Particle size (µm)'}, yaxis: {title: 'Probable error, Ep (SG)'}},
  320, label, false);
}

export function sizeWindowChart(rows, label = 'Separation window') {
  return fig([{x: rows.map(r => r.size_um), y: rows.map(r => r.efficiency_pct), mode: 'lines',
    fill: 'tozeroy', fillcolor: 'rgba(2,136,209,0.18)', line: {width: 2.4, color: '#0288d1'},
    name: 'Machine efficiency'}],
  {xaxis: {type: 'log', title: 'Particle size (µm)'}, yaxis: {title: 'Fraction the machine can treat (%)', range: [0, 101]}},
  320, label, false);
}

export function settlingChart(rows) {
  return fig([{x: rows.map(r => r.sg), y: rows.map(r => r.d50_um), mode: 'lines+markers',
    line: {width: 2.6, color: '#1e88e5'}, name: 'Cut size'}],
  {xaxis: {title: 'Particle density (SG)'}, yaxis: {title: 'Cut size d50 (µm)'}},
  320, 'Hindered settling — a dense grain reports to the sand at a finer size', false);
}

export function attritionChart(rows, current = null) {
  const shapes = current ? [{type: 'line', yref: 'paper', x0: current, x1: current, y0: 0, y1: 1,
    line: {color: '#66bb6a', dash: 'dash', width: 1.6}}] : [];
  return fig([{x: rows.map(r => r.residence_min), y: rows.map(r => r.detached_pct), mode: 'lines',
    line: {width: 2.6, color: '#00897b'}, name: 'Clay detached'}],
  {xaxis: {title: 'Scrubber residence time (min)'}, yaxis: {title: 'Clay coating detached (%)', range: [0, 101]}, shapes},
  320, 'Scrubber attrition — first-order clay detachment', false);
}

export function productSplitChart(kpis) {
  const rows = [['Lump ore', kpis.lump_tph, '#8d6e63'], ['Sinter fines', kpis.fines_tph, '#f9a825'],
    ['Pellet-plant feed', kpis.pellet_fines_tph, '#c62828'], ['Tailings', kpis.tailings_tph, '#a1887f']];
  return fig(rows.map(([n, v, c]) => ({x: ['ROM feed'], y: [v], type: 'bar', name: n, marker: {color: c},
    hovertemplate: `${n}: %{y:,.1f} t/h<extra></extra>`})),
  {barmode: 'stack', yaxis: {title: 't/h'}, xaxis: {}}, 340, 'Where the ROM tonnes go');
}

export function productQualityChart(kpis, design = {}) {
  const prods = [['Lump ore', 'lump_fe_pct', 'lump_sio2_pct', 'lump_al2o3_pct'],
    ['Sinter fines', 'fines_fe_pct', 'fines_sio2_pct', 'fines_al2o3_pct'],
    ['Pellet feed', 'pellet_fines_fe_pct', 'pellet_fines_sio2_pct', 'pellet_fines_al2o3_pct']];
  return fig([
    {x: prods.map(p => p[0]), y: prods.map(p => kpis[p[1]]), type: 'bar', name: '% Fe', marker: {color: '#8d6e63'}},
    {x: prods.map(p => p[0]), y: prods.map(p => kpis[p[2]]), type: 'bar', name: '% SiO₂', yaxis: 'y2',
      marker: {color: '#90a4ae'}},
    {x: prods.map(p => p[0]), y: prods.map(p => kpis[p[3]]), type: 'bar', name: '% Al₂O₃', yaxis: 'y2',
      marker: {color: '#ef5350'}},
  ], {barmode: 'group', yaxis: {title: '% Fe'},
    yaxis2: {title: '% SiO₂ / Al₂O₃', overlaying: 'y', side: 'right', showgrid: false}},
  340, 'Product quality against the three specifications');
}
export function captureCurveChart(rows) {
  return fig([{x: rows.map(r => r.particle_iron_fraction * 100), y: rows.map(r => r.capture_probability * 100),
    mode: 'lines', line: {width: 2.4, color: '#1e88e5'}, name: 'Capture probability'}],
  {xaxis: {title: 'Particle iron-mineral content (%)'}, yaxis: {title: 'Probability of reporting to the magnetic product (%)', range: [0, 101]}},
  320, 'Magnetic capture selectivity');
}
export function partitionChart(rows, d50c = null) {
  const shapes = [{type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 50, y1: 50, line: {color: '#90a4ae', dash: 'dot', width: 1}}];
  if (d50c) shapes.push({type: 'line', yref: 'paper', x0: d50c, x1: d50c, y0: 0, y1: 1, line: {color: '#66bb6a', dash: 'dash'}});
  return fig([{x: rows.map(r => r.size_um), y: rows.map(r => r.to_underflow_pct), mode: 'lines+markers',
    line: {width: 2.2, color: '#29b6f6'}, name: 'To underflow'}],
  {xaxis: {type: 'log', title: 'Size (µm)'}, yaxis: {title: 'Partition to underflow (%)', range: [0, 101]}, shapes},
  320, `Cyclone partition curve${d50c ? ` (d50c ${d50c.toFixed(0)} µm)` : ''}`);
}
export function fluxChart(rows) {
  return fig([{x: rows.map(r => r.phi), y: rows.map(r => r.flux_m_h), mode: 'lines', line: {width: 2.4, color: '#7b1fa2'},
    name: 'Batch flux'}], {xaxis: {title: 'Solids volume fraction'}, yaxis: {title: 'Solids flux (m/h × φ)'}},
  320, 'Thickener batch-flux curve');
}
// ---------------------------------------------------------------- balances and economics
export function sankeyChart(sankey, title = 'Solids flow (t/h)') {
  const nodes = sankey.nodes;
  const idx = Object.fromEntries(nodes.map((n, i) => [n, i]));
  return fig([{type: 'sankey', orientation: 'h',
    node: {label: nodes, pad: 16, thickness: 16, color: nodes.map((_, i) => PALETTE[i % 10])},
    link: {source: sankey.links.map(l => idx[l.source]), target: sankey.links.map(l => idx[l.target]),
      value: sankey.links.map(l => Math.max(l.value, 0.01)), color: 'rgba(41,182,246,0.25)'}}],
  {}, 400, title, false);
}
export function stackedBar(dict, title, unit = 'kW', height = 320) {
  const entries = Object.entries(dict).filter(([, v]) => typeof v === 'number' && v > 0).sort((a, b) => b[1] - a[1]);
  return fig([{x: entries.map(e => e[1]), y: entries.map(e => e[0].replace(/_(kw|usd_h)$/, '').replace(/_/g, ' ')),
    type: 'bar', orientation: 'h', marker: {color: PALETTE[0]}, hovertemplate: `%{x:.4g} ${unit}<extra>%{y}</extra>`}],
  {xaxis: {title: unit}, yaxis: {automargin: true}}, height, title, false);
}
export function constraintChart(rows) {
  const d = rows.filter(r => r.margin_pct !== null).sort((a, b) => a.margin_pct - b.margin_pct).slice(0, 18);
  return fig([{x: d.map(r => r.margin_pct), y: d.map(r => `P${r.priority} ${r.label}`), type: 'bar', orientation: 'h',
    marker: {color: d.map(r => STATUS_COLOR[r.status] || '#78909c')},
    hovertemplate: '%{y}<br>margin %{x:.1f} %<extra></extra>'}],
  {xaxis: {title: 'Margin to limit (%)'}, yaxis: {automargin: true},
    shapes: [{type: 'line', yref: 'paper', x0: 0, x1: 0, y0: 0, y1: 1, line: {color: '#e53935', width: 1.5}}]},
  Math.max(320, 26 * d.length), 'Constraint margins (negative = violated)', false);
}
export function responseChart(rows, xKey, yKeys, labels = {}, title = '') {
  const data = yKeys.map((k, i) => ({x: rows.map(r => r[xKey]), y: rows.map(r => r[k]), name: labels[k] || k,
    mode: 'lines+markers', yaxis: i === 0 ? 'y' : 'y2', line: {width: 2.2, color: PALETTE[i % 10]}}));
  return fig(data, {xaxis: {title: labels[xKey] || xKey}, yaxis: {title: labels[yKeys[0]] || yKeys[0]},
    yaxis2: {title: yKeys[1] ? (labels[yKeys[1]] || yKeys[1]) : '', overlaying: 'y', side: 'right', showgrid: false}},
  330, title);
}
export function tornadoChart(rows, base, kpi) {
  const d = rows.slice(0, 14).reverse();
  return fig([
    {x: d.map(r => r.low - base), y: d.map(r => r.variable), type: 'bar', orientation: 'h', name: '−8 %', marker: {color: '#ef5350'}},
    {x: d.map(r => r.high - base), y: d.map(r => r.variable), type: 'bar', orientation: 'h', name: '+8 %', marker: {color: '#66bb6a'}},
  ], {barmode: 'overlay', xaxis: {title: `Δ ${kpi}`}, yaxis: {automargin: true}}, Math.max(340, 26 * d.length),
  `Sensitivity of ${kpi}`);
}
export function paretoChart(points, frontier, xKpi, yKpi) {
  return fig([
    {x: points.filter(p => p.feasible).map(p => p.x), y: points.filter(p => p.feasible).map(p => p.y), mode: 'markers',
      name: 'Feasible', marker: {size: 7, color: '#29b6f6', opacity: 0.6}},
    {x: points.filter(p => !p.feasible).map(p => p.x), y: points.filter(p => !p.feasible).map(p => p.y), mode: 'markers',
      name: 'Infeasible', marker: {size: 6, color: '#ef5350', opacity: 0.35, symbol: 'x'}},
    {x: frontier.map(p => p.x), y: frontier.map(p => p.y), mode: 'lines+markers', name: 'Frontier',
      line: {width: 2.4, color: '#66bb6a'}},
  ], {xaxis: {title: xKpi}, yaxis: {title: yKpi}}, 380, 'Trade-off frontier');
}
export function histogram(values, title, xTitle) {
  return fig([{x: values, type: 'histogram', marker: {color: '#29b6f6', opacity: 0.8}, nbinsx: 18}],
    {xaxis: {title: xTitle}, yaxis: {title: 'Count'}}, 300, title, false);
}

// ---------------------------------------------------------------- control
export function gainHeatmap(matrix, mvKeys, cvKeys, title = 'Steady-state gain matrix (normalised)') {
  const norm = matrix.map(row => {
    const m = Math.max(...row.map(Math.abs), 1e-9);
    return row.map(v => v / m);
  });
  return fig([{z: norm, x: mvKeys, y: cvKeys, type: 'heatmap', colorscale: 'RdBu', zmid: 0, reversescale: true,
    text: matrix.map(r => r.map(v => v.toExponential(2))), hovertemplate: 'CV %{y}<br>MV %{x}<br>gain %{text}<extra></extra>'}],
  {xaxis: {tickangle: -35, automargin: true}, yaxis: {automargin: true}}, 380, title, false);
}
export function stepResponseChart(models, cv) {
  const t = Object.values(models)[0] ? Object.values(models)[0].response.map((_, i) => i * 2) : [];
  const data = Object.entries(models).map(([mv, m], i) => ({x: t, y: m.response, name: mv, mode: 'lines',
    line: {width: 2, color: PALETTE[i % 10]}}));
  return fig(data, {xaxis: {title: 'Time (min)'}, yaxis: {title: `Δ ${cv} per unit MV move`}}, 360,
    `Identified step responses — ${cv}`);
}
export function mpcTrajectoryChart(sol, cv, dtMin) {
  const t = sol.predicted[cv].map((_, i) => (i + 1) * dtMin);
  const zone = sol.zones[cv] || [];
  return fig([
    {x: t, y: sol.no_action[cv], name: 'No action', mode: 'lines', line: {width: 2, dash: 'dot', color: '#ef5350'}},
    {x: t, y: sol.predicted[cv], name: 'MPC prediction', mode: 'lines', line: {width: 2.6, color: '#66bb6a'}},
    {x: t, y: t.map(() => sol.targets[cv]), name: 'Target', mode: 'lines', line: {width: 1.6, dash: 'dash', color: '#29b6f6'}},
  ], {xaxis: {title: 'Prediction horizon (min)'}, yaxis: {title: cv},
    shapes: zone.length === 2 ? [{type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: zone[0], y1: zone[1],
      fillcolor: 'rgba(102,187,106,0.08)', line: {width: 0}}] : []}, 330, `Predicted trajectory — ${cv}`);
}
export function closedLoopChart(run, keys, title = 'Closed-loop response') {
  const panels = keys.map(k => ({title: k, series: {[k]: {x: run.t_min, y: run.cv[k]},
    target: {x: run.t_min, y: run.target[k]}}}));
  return smallMultiples(run.t_min, panels, 2, 200);
}
export function mvTrajectoryChart(run, keys) {
  const panels = keys.map(k => ({title: k, series: {[k]: {x: run.t_min, y: run.mv[k], source: 'recommended'}}}));
  return smallMultiples(run.t_min, panels, 3, 170);
}
export function moveChart(moves, uNext, uNow) {
  const keys = Object.keys(moves).filter(k => Math.abs(moves[k]) > 1e-9);
  return fig([{x: keys.map(k => moves[k]), y: keys, type: 'bar', orientation: 'h',
    marker: {color: keys.map(k => moves[k] >= 0 ? '#66bb6a' : '#ef5350')},
    text: keys.map(k => `${uNow[k].toFixed(3)} → ${uNext[k].toFixed(3)}`), hovertemplate: '%{y}<br>%{text}<extra></extra>'}],
  {xaxis: {title: 'First move (engineering units)'}, yaxis: {automargin: true}}, Math.max(280, 30 * keys.length),
  'MPC first-move plan', false);
}

// ---------------------------------------------------------------- machine learning
export function importanceChart(rows, title = 'Permutation importance') {
  const d = rows.slice(0, 12).reverse();
  return fig([{x: d.map(r => r.importance), y: d.map(r => r.feature), type: 'bar', orientation: 'h',
    error_x: {type: 'data', array: d.map(r => r.std), visible: true, color: '#90a4ae'}, marker: {color: '#ab47bc'}}],
  {xaxis: {title: 'Increase in error when shuffled'}, yaxis: {automargin: true}}, Math.max(320, 26 * d.length), title, false);
}
export function parityChart(rows, label = 'Prediction vs plant') {
  const a = rows.map(r => r.actual), p = rows.map(r => r.value);
  const lo = Math.min(...a, ...p), hi = Math.max(...a, ...p);
  return fig([
    {x: a, y: p, mode: 'markers', name: 'Samples', marker: {size: 8, color: '#29b6f6'}},
    {x: [lo, hi], y: [lo, hi], mode: 'lines', name: 'Parity', line: {dash: 'dash', color: '#90a4ae'}},
  ], {xaxis: {title: 'Plant / twin value'}, yaxis: {title: 'Model prediction'}}, 320, label);
}
export function learningCurveChart(rows) {
  return fig([
    {x: rows.map(r => r.n_train), y: rows.map(r => r.r2_test), name: 'R² (hold-out)', mode: 'lines+markers', line: {width: 2.4, color: '#66bb6a'}},
    {x: rows.map(r => r.n_train), y: rows.map(r => r.rmse_test), name: 'RMSE', mode: 'lines+markers', yaxis: 'y2',
      line: {width: 2, color: '#ffb300'}},
  ], {xaxis: {title: 'Training samples'}, yaxis: {title: 'R²'}, yaxis2: {title: 'RMSE', overlaying: 'y', side: 'right', showgrid: false}},
  320, 'Learning curve');
}
export function pdpChart(pdp) {
  return fig([{x: pdp.x, y: pdp.y, mode: 'lines', line: {width: 2.6, color: '#ab47bc'}, name: 'Partial dependence'}],
    {xaxis: {title: pdp.feature}, yaxis: {title: pdp.target}}, 320, 'Partial dependence', false);
}
export function anomalyChart(rows) {
  const flagged = rows.filter(r => r.is_anomaly);
  return fig([
    {x: rows.map(r => r.hour), y: rows.map(r => r.anomaly_score), mode: 'lines+markers', name: 'Anomaly score',
      line: {width: 2, color: '#29b6f6'}},
    {x: rows.map(r => r.hour), y: rows.map(r => r.threshold), mode: 'lines', name: 'Threshold',
      line: {width: 1.6, dash: 'dash', color: '#ef5350'}},
    {x: flagged.map(r => r.hour), y: flagged.map(r => r.anomaly_score), mode: 'markers', name: 'Flagged',
      marker: {size: 11, color: '#ef5350', symbol: 'x'}},
  ], {xaxis: {title: 'Replay hour'}, yaxis: {title: 'Isolation-forest score'}}, 330, 'Anomaly detection');
}
export function driftChart(features) {
  const d = features.slice(0, 14).reverse();
  return fig([{x: d.map(r => r.psi), y: d.map(r => r.feature), type: 'bar', orientation: 'h',
    marker: {color: d.map(r => STATUS_COLOR[r.status] || '#78909c')}}],
  {xaxis: {title: 'Population stability index'}, yaxis: {automargin: true},
    shapes: [0.1, 0.25].map(v => ({type: 'line', yref: 'paper', x0: v, x1: v, y0: 0, y1: 1,
      line: {color: '#90a4ae', dash: 'dot', width: 1}}))}, Math.max(320, 26 * d.length), 'Feature drift (PSI)', false);
}
export function scanChart(rows, feature, target) {
  return fig([
    {x: rows.map(r => r[feature]), y: rows.map(r => r.twin), name: 'First-principles twin', mode: 'lines',
      line: {width: 2.4, color: '#ab47bc'}},
    {x: rows.map(r => r[feature]), y: rows.map(r => r.ml), name: 'ML surrogate', mode: 'lines+markers',
      line: {width: 2, dash: 'dash', color: '#29b6f6'}},
    {x: rows.map(r => r[feature]).concat([...rows].reverse().map(r => r[feature])),
      y: rows.map(r => r.interval_95[1]).concat([...rows].reverse().map(r => r.interval_95[0])),
      fill: 'toself', fillcolor: 'rgba(41,182,246,0.12)', line: {width: 0}, name: '95 % interval', hoverinfo: 'skip'},
  ], {xaxis: {title: feature}, yaxis: {title: target}}, 340, 'Surrogate vs twin');
}

// ---------------------------------------------------------------- diagnostics
export function residualChart(hours, residuals, tags) {
  const data = tags.map((t, i) => ({x: hours, y: residuals[t], name: t, mode: 'lines', line: {width: 1.8, color: PALETTE[i % 10]}}));
  return fig(data, {xaxis: {title: 'Replay hour'}, yaxis: {title: 'Measurement − model (%)'},
    shapes: [-8, 8].map(v => ({type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
      line: {color: '#ef5350', dash: 'dot', width: 1}}))}, 340, 'Instrument residuals vs the twin');
}
export function reconciliationChart(vars) {
  return fig([
    {x: vars.map(v => v.variable), y: vars.map(v => v.measured), name: 'Measured', type: 'bar', marker: {color: '#29b6f6'}},
    {x: vars.map(v => v.variable), y: vars.map(v => v.reconciled), name: 'Reconciled', type: 'bar', marker: {color: '#66bb6a'}},
  ], {barmode: 'group', xaxis: {tickangle: -25, automargin: true}, yaxis: {title: 'Value'}}, 330, 'Data reconciliation');
}
export function qualityChart(tags) {
  return fig([{x: tags.map(t => t.coverage_pct), y: tags.map(t => t.noise_pct ?? 0), mode: 'markers', text: tags.map(t => t.label),
    marker: {size: 10, color: tags.map(t => STATUS_COLOR[t.status] || '#78909c')},
    hovertemplate: '%{text}<br>coverage %{x:.1f} %<br>noise %{y:.2f} %<extra></extra>'}],
  {xaxis: {title: 'Coverage (%)'}, yaxis: {title: 'Signal noise (%)'}}, 330, 'Instrument health map', false);
}
export function waterfall(labels, values, title) {
  return fig([{type: 'waterfall', orientation: 'v', x: labels, y: values, connector: {line: {color: '#90a4ae'}},
    decreasing: {marker: {color: '#ef5350'}}, increasing: {marker: {color: '#66bb6a'}}, totals: {marker: {color: '#29b6f6'}}}],
  {xaxis: {tickangle: -20, automargin: true}, yaxis: {title: 'USD/h'}}, 340, title, false);
}

/* ================================================================================================
   v5 — validation, acceptance and hybrid-model charts.
   These are the plots an acceptance review is argued over, so they are deliberately plain:
   a parity plot, a Bland-Altman plot, a residual profile and a margin bar. No decoration.
   ============================================================================================= */

/** Model against plant on a 1:1 line, with the agreed tolerance band drawn around it. */
export function parityPlot(observed, predicted, {label = '', unit = '', tol = null} = {}) {
  const all = observed.concat(predicted).filter(Number.isFinite);
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.06 || 1;
  const a = lo - pad, b = hi + pad;
  const data = [
    {x: [a, b], y: [a, b], mode: 'lines', name: '1:1', line: {color: '#90a4ae', dash: 'dash', width: 1.4},
     hoverinfo: 'skip'},
    {x: observed, y: predicted, mode: 'markers', name: 'Observations',
     marker: {size: 6, color: '#29b6f6', opacity: 0.75, line: {width: 0}},
     hovertemplate: `plant %{x:.3f} → twin %{y:.3f} ${unit}<extra></extra>`},
  ];
  if (tol) {
    data.splice(1, 0,
      {x: [a, b], y: [a + tol, b + tol], mode: 'lines', name: `± ${tol} ${unit}`,
       line: {color: '#66bb6a', width: 1, dash: 'dot'}, hoverinfo: 'skip'},
      {x: [a, b], y: [a - tol, b - tol], mode: 'lines', showlegend: false,
       line: {color: '#66bb6a', width: 1, dash: 'dot'}, fill: 'tonexty',
       fillcolor: 'rgba(102,187,106,0.08)', hoverinfo: 'skip'});
  }
  return fig(data, {xaxis: {title: `Plant measurement ${unit}`, range: [a, b]},
    yaxis: {title: `Twin prediction ${unit}`, range: [a, b], scaleanchor: 'x'}},
  360, `Parity — ${label}`);
}

/** Difference against mean, with the 95 % limits of agreement. */
export function blandAltmanChart(observed, predicted, ba, {label = '', unit = ''} = {}) {
  const mean = observed.map((v, i) => (v + predicted[i]) / 2);
  const diff = observed.map((v, i) => predicted[i] - v);
  const shapes = [
    {type: 'line', xref: 'paper', x0: 0, x1: 1, y0: ba.mean_difference, y1: ba.mean_difference,
     line: {color: '#ffb300', width: 1.6}},
    {type: 'line', xref: 'paper', x0: 0, x1: 1, y0: ba.loa_upper, y1: ba.loa_upper,
     line: {color: '#ef5350', width: 1.2, dash: 'dash'}},
    {type: 'line', xref: 'paper', x0: 0, x1: 1, y0: ba.loa_lower, y1: ba.loa_lower,
     line: {color: '#ef5350', width: 1.2, dash: 'dash'}},
  ];
  return fig([{x: mean, y: diff, mode: 'markers', name: 'Difference',
    marker: {size: 6, color: '#ab47bc', opacity: 0.72},
    hovertemplate: `mean %{x:.3f} → difference %{y:.3f} ${unit}<extra></extra>`}],
  {xaxis: {title: `Mean of plant and twin ${unit}`},
    yaxis: {title: `Twin − plant ${unit}`}, shapes},
  330, `Bland–Altman — ${label} (bias ${ba.mean_difference.toFixed(3)}, limits ` +
       `${ba.loa_lower.toFixed(3)} to ${ba.loa_upper.toFixed(3)})`, false);
}

/** Bias and RMSE banded by the observed level — where a model is wrong, not just how much. */
export function residualProfileChart(profile, {label = '', unit = ''} = {}) {
  const mid = profile.map(r => (r.from + r.to) / 2);
  return fig([
    {x: mid, y: profile.map(r => r.bias), type: 'bar', name: 'Bias',
     marker: {color: profile.map(r => (r.bias >= 0 ? '#29b6f6' : '#ef5350'))},
     hovertemplate: `%{x:.2f} ${unit}: bias %{y:.3f}<extra></extra>`},
    {x: mid, y: profile.map(r => r.rmse), mode: 'lines+markers', name: 'RMSE', yaxis: 'y2',
     line: {color: '#ffb300', width: 2}},
  ], {xaxis: {title: `Observed level ${unit}`}, yaxis: {title: `Bias ${unit}`},
    yaxis2: {title: 'RMSE', overlaying: 'y', side: 'right'}, barmode: 'relative'},
  300, `Residual profile — ${label}`);
}

/** How much headroom each acceptance criterion has, as a share of its limit. */
export function criteriaMarginChart(results) {
  const rows = results.filter(r => r.verdict !== 'insufficient_data' && r.checks)
    .map(r => ({kpi: r.kpi, cls: r.class,
      margin: r.checks.rmse && r.checks.rmse.margin_pct_of_limit != null
        ? r.checks.rmse.margin_pct_of_limit : 0,
      verdict: r.verdict}))
    .sort((a, b) => a.margin - b.margin);
  const colour = {pass: '#43a047', marginal: '#fb8c00', fail: '#e53935'};
  return fig([{y: rows.map(r => `${r.kpi} (${r.cls})`), x: rows.map(r => r.margin),
    type: 'bar', orientation: 'h',
    marker: {color: rows.map(r => colour[r.verdict] || '#78909c')},
    hovertemplate: '%{y}: %{x:.1f} % headroom on the RMSE limit<extra></extra>'}],
  {xaxis: {title: 'Headroom against the RMSE limit (% of limit)'},
    yaxis: {automargin: true}, margin: {l: 200}},
  Math.max(280, 26 * rows.length + 70), 'Acceptance margin by criterion', false);
}

/** Where the plant sits inside its validated envelope, variable by variable. */
export function envelopeChart(rows) {
  const r = rows.filter(x => x.value != null);
  const colour = {inside: '#43a047', below: '#e53935', above: '#e53935', not_supplied: '#78909c'};
  return fig([
    {y: r.map(x => x.label), x: r.map(() => 100), type: 'bar', orientation: 'h',
     marker: {color: 'rgba(120,144,156,0.18)'}, hoverinfo: 'skip', showlegend: false},
    {y: r.map(x => x.label), x: r.map(x => Math.max(0, Math.min(100, x.position_pct))),
     type: 'scatter', mode: 'markers', name: 'Current',
     marker: {size: 13, symbol: 'diamond', color: r.map(x => colour[x.state] || '#78909c'),
       line: {width: 1, color: '#263238'}},
     hovertemplate: r.map(x => `${x.label}: ${x.value} ${x.unit}<br>range ${x.lo} – ${x.hi}` +
       `<br>${x.state}<extra></extra>`)},
  ], {xaxis: {title: 'Position across the validated range (%)', range: [0, 100]},
    yaxis: {automargin: true}, barmode: 'overlay', margin: {l: 190}},
  Math.max(280, 28 * r.length + 70), 'Operating point against the validated envelope', false);
}

/** The extrapolation walk: what each composition does as it leaves the learned domain. */
export function extrapolationChart(rows, target = '') {
  const x = rows.map(r => r.distance_from_centre);
  return fig([
    {x, y: rows.map(r => r.mechanistic), mode: 'lines+markers', name: 'Mechanistic only',
     line: {color: '#29b6f6', width: 2.6}},
    {x, y: rows.map(r => r.gated_hybrid), mode: 'lines+markers', name: 'Gated hybrid (in service)',
     line: {color: '#66bb6a', width: 2.6, dash: 'dash'}},
    {x, y: rows.map(r => r.ungated_hybrid), mode: 'lines', name: 'Ungated residual',
     line: {color: '#ffb300', width: 1.8, dash: 'dot'}},
    {x, y: rows.map(r => r.data_only), mode: 'lines+markers', name: 'Data driven only',
     line: {color: '#ef5350', width: 2.2}},
    {x, y: rows.map(r => r.confidence * 100), mode: 'lines', name: 'Domain confidence',
     yaxis: 'y2', line: {color: '#90a4ae', width: 1.4}, fill: 'tozeroy',
     fillcolor: 'rgba(144,164,174,0.10)'},
  ], {xaxis: {title: 'Distance from the centre of the training data (× the trained range)'},
    yaxis: {title: target || 'Prediction'},
    yaxis2: {title: 'Domain confidence (%)', overlaying: 'y', side: 'right', range: [0, 105]}},
  360, 'Behaviour as the operating point leaves the learned domain');
}

/** Mechanistic against learned contribution for each available composition. */
export function attributionChart(rows) {
  const r = rows.filter(x => x.attribution);
  return fig([
    {x: r.map(x => x.mode), y: r.map(x => x.attribution.mechanistic_pct), type: 'bar',
     name: 'Mechanistic', marker: {color: '#29b6f6'}},
    {x: r.map(x => x.mode), y: r.map(x => x.attribution.learned_pct), type: 'bar',
     name: 'Learned', marker: {color: '#ffb300'}},
  ], {barmode: 'stack', xaxis: {automargin: true},
    yaxis: {title: 'Share of the prediction (%)', range: [0, 100]}},
  300, 'Where the number comes from');
}

/** Error of each composition on held-out data. */
export function compositionErrorChart(results) {
  const keys = Object.keys(results);
  return fig([
    {x: keys, y: keys.map(k => results[k].rmse), type: 'bar', name: 'RMSE',
     marker: {color: '#ab47bc'}},
    {x: keys, y: keys.map(k => results[k].mae), type: 'bar', name: 'MAE',
     marker: {color: '#26c6da'}},
    {x: keys, y: keys.map(k => Math.abs(results[k].bias)), type: 'bar', name: '|bias|',
     marker: {color: '#ff7043'}},
  ], {barmode: 'group', xaxis: {automargin: true}, yaxis: {title: 'Error'}},
  310, 'Error on held-out data by composition');
}

/** Scenario matrix: one row per scenario, coloured by verdict. */
export function scenarioMatrixChart(rows) {
  const colour = {pass: '#43a047', partial: '#fb8c00', fail: '#e53935', not_evaluated: '#78909c'};
  const flat = [];
  rows.forEach(r => r.checks.forEach(c => flat.push({s: r.scenario_id, k: c.kpi, v: c.verdict})));
  const ss = [...new Set(flat.map(f => f.s))];
  const ks = [...new Set(flat.map(f => f.k))];
  return fig([{x: flat.map(f => f.k), y: flat.map(f => f.s), mode: 'markers',
    marker: {size: 17, symbol: 'square',
      color: flat.map(f => colour[f.v] || '#78909c')},
    hovertemplate: '%{y} · %{x}: ' + '%{text}<extra></extra>',
    text: flat.map(f => f.v.toUpperCase())}],
  {xaxis: {automargin: true, tickangle: -35, categoryarray: ks},
    yaxis: {automargin: true, categoryarray: ss}, margin: {l: 170, b: 150}},
  Math.max(300, 30 * ss.length + 170), 'Step-test verdicts', false);
}
