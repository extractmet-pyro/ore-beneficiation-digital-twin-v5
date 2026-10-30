// Annotated flowsheet of the gravity + WHIMS ore-beneficiation plant, drawn as SVG with live
// stream and unit data. Layout follows the plant drawing: crushing and scrubbing across the top,
// the lump-jig circuit on the right, the classifier / jig / spiral / table fines circuit through
// the middle, the desliming and WHIMS circuit on the left, and tailings and water along the base.
import {AREA_COLORS, STATUS_COLOR} from '../utils/constants.js';

export const W = 1920, H = 1120;
const ORE = '#bcaaa4', SLURRY = '#90a4ae', HEAVY = '#5d4037', CONC = '#f9a825', MAG = '#c62828',
  TAILS = '#a1887f', WATER = '#29b6f6';
const MK = {[ORE]: 0, [SLURRY]: 1, [HEAVY]: 2, [CONC]: 3, [MAG]: 4, [TAILS]: 5, [WATER]: 6};
const f = (v, spec = '0') => {
  const n = Number(v);
  if (v === null || v === undefined || !Number.isFinite(n)) return '—';
  const [comma, dp] = spec.startsWith(',') ? [true, Number(spec.slice(1))] : [false, Number(spec)];
  return n.toLocaleString('en-US', {minimumFractionDigits: dp, maximumFractionDigits: dp, useGrouping: comma});
};
const x = s => String(s).replace(/&(?!amp;|lt;|gt;|quot;|#)/g, '&amp;').replace(/</g, '&lt;');

class Canvas {
  constructor(dark) {
    this.dark = dark;
    this.fg = dark ? '#eceff1' : '#263238';
    this.sub = dark ? '#b0bec5' : '#546e7a';
    this.panel = dark ? 'rgba(20,28,36,0.88)' : 'rgba(255,255,255,0.93)';
    this.el = [];
    this.top = [];
  }

  region(X, Y, w, h, area, label) {
    const c = AREA_COLORS[area] || '#607d8b';
    this.el.push(`<rect x='${X}' y='${Y}' width='${w}' height='${h}' rx='14' fill='${c}' fill-opacity='0.08' stroke='${c}' stroke-opacity='0.7' stroke-dasharray='6 4'/>` +
      `<text x='${X + 12}' y='${Y + 22}' fill='${c}' font-size='15' font-weight='700'>${x(label)}</text>`);
  }

  stream(pts, color, label = '', {dashed = false, width = 3.2, at = 0.5, dy = -8} = {}) {
    const d = 'M ' + pts.map(p => p.join(',')).join(' L ');
    this.el.push(`<path d='${d}' fill='none' stroke='${color}' stroke-width='${width}' ${dashed ? "stroke-dasharray='8 5'" : ''} marker-end='url(#arrow${MK[color] ?? 0})'/>`);
    if (label) {
      const i = Math.min(Math.max(Math.floor(at * (pts.length - 1)), 0), pts.length - 2);
      const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const lx = (x1 + x2) / 2, ly = (y1 + y2) / 2 + dy, tw = 6 * label.length + 12;
      this.top.push(`<rect x='${lx - tw / 2}' y='${ly - 12}' width='${tw}' height='16' rx='4' fill='${this.dark ? '#0e1117' : '#ffffff'}' fill-opacity='0.86' stroke='${color}' stroke-opacity='0.5'/>` +
        `<text x='${lx}' y='${ly}' fill='${color}' font-size='11' font-weight='600' text-anchor='middle'>${x(label)}</text>`);
    }
  }

  params(X, Y, title, rows, status = 'normal', w = 215, uid = '') {
    const h = 22 + 15 * rows.length, c = STATUS_COLOR[status] || '#78909c';
    let s = `<g class='pbox' data-unit='${uid}' style='cursor:${uid ? 'pointer' : 'default'}'><rect x='${X}' y='${Y}' width='${w}' height='${h}' rx='7' fill='${this.panel}' stroke='${c}' stroke-width='${status !== 'normal' ? 2.2 : 1.2}'/>` +
      `<circle cx='${X + 11}' cy='${Y + 12}' r='5' fill='${c}'/><text x='${X + 22}' y='${Y + 16}' fill='${this.fg}' font-size='12' font-weight='700'>${x(title)}</text>`;
    rows.forEach(([k, v], i) => {
      const yy = Y + 32 + 15 * i;
      s += `<text x='${X + 8}' y='${yy}' fill='${this.sub}' font-size='11'>${x(k)}</text><text x='${X + w - 8}' y='${yy}' fill='${this.fg}' font-size='11' font-weight='600' text-anchor='end'>${x(v)}</text>`;
    });
    this.top.push(s + (uid ? `<title>Click to open ${x(title)} in Unit operations</title>` : '') + '</g>');
  }

  stockpile(X, Y, label, colour = '#8d6e63') {
    this.el.push(`<path d='M${X - 62},${Y + 25} Q${X},${Y - 42} ${X + 62},${Y + 25} Z' fill='${colour}' fill-opacity='0.8' stroke='${this.fg}'/>` +
      `<text x='${X}' y='${Y + 44}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text>`);
  }

  crusher(X, Y, label, s = 1) {
    this.el.push(`<path d='M${X - 40 * s},${Y - 30 * s} L${X + 40 * s},${Y - 30 * s} L${X + 20 * s},${Y + 26 * s} L${X - 20 * s},${Y + 26 * s} Z' fill='#6d4c41' stroke='${this.fg}' stroke-width='1.5'/>` +
      `<path d='M${X - 11 * s},${Y - 26 * s} L${X + 11 * s},${Y - 26 * s} L${X + 6 * s},${Y + 20 * s} L${X - 6 * s},${Y + 20 * s} Z' fill='#bcaaa4'/>` +
      `<text x='${X}' y='${Y + 42 * s}' fill='${this.fg}' font-size='11' font-weight='600' text-anchor='middle'>${x(label)}</text>`);
  }

  screen(X, Y, label, w = 104) {
    this.el.push(`<g><rect x='${X - w / 2}' y='${Y - 16}' width='${w}' height='30' rx='5' fill='#455a64' stroke='${this.fg}'/>` +
      `<line x1='${X - w / 2 + 8}' y1='${Y - 6}' x2='${X + w / 2 - 8}' y2='${Y + 6}' stroke='#cfd8dc' stroke-width='3' stroke-dasharray='6 4'/></g>` +
      `<text x='${X}' y='${Y + 32}' fill='${this.fg}' font-size='11' text-anchor='middle'>${x(label)}</text>`);
  }

  /** Rotary scrubber: an inclined rotating drum with internal lifters. */
  scrubber(X, Y, label) {
    let s = `<g><rect x='${X - 88}' y='${Y - 30}' width='176' height='60' rx='28' fill='#00897b' stroke='${this.fg}' stroke-width='1.8'/>`;
    s += `<path d='M${X - 88},${Y - 18} L${X - 112},${Y - 8} L${X - 112},${Y + 10} L${X - 88},${Y + 18}' fill='#00897b' stroke='${this.fg}'/>`;
    s += `<path d='M${X + 88},${Y - 18} L${X + 110},${Y - 8} L${X + 110},${Y + 10} L${X + 88},${Y + 18}' fill='#00897b' stroke='${this.fg}'/>`;
    s += `<g class='spin' style='transform-origin:${X}px ${Y}px'>`;
    for (let i = 0; i < 6; i++) {
      const cx = X - 66 + i * 26;
      s += `<line x1='${cx}' y1='${Y - 24}' x2='${cx}' y2='${Y + 24}' stroke='#b2dfdb' stroke-opacity='0.75' stroke-width='2.6'/>`;
    }
    s += `</g>`;
    for (let i = 0; i < 5; i++) s += `<circle class='bub' cx='${X - 55 + i * 28}' cy='${Y + 6}' r='2.6' fill='#e0f2f1' style='animation-delay:${i * 0.3}s'/>`;
    this.el.push(s + `<text x='${X}' y='${Y + 50}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text></g>`);
  }

  /** Jig: a pulsed bed over a hutch, with the pulsion arrow. */
  jig(X, Y, label, cells = 2, w = 62) {
    let s = '<g>';
    for (let i = 0; i < Math.min(cells, 4); i++) {
      const cx = X + i * (w + 6);
      s += `<rect x='${cx}' y='${Y}' width='${w}' height='40' rx='3' fill='#5c6bc0' fill-opacity='0.9' stroke='${this.fg}'/>`;
      // stratified bed: heavy at the bottom, light on top
      s += `<rect x='${cx + 3}' y='${Y + 24}' width='${w - 6}' height='13' fill='#3e2723' fill-opacity='0.85'/>`;
      s += `<rect x='${cx + 3}' y='${Y + 12}' width='${w - 6}' height='12' fill='#a1887f' fill-opacity='0.8'/>`;
      // hutch and pulsion
      s += `<path d='M${cx},${Y + 40} L${cx + w},${Y + 40} L${cx + w - 9},${Y + 62} L${cx + 9},${Y + 62} Z' fill='#37474f' stroke='${this.fg}'/>`;
      s += `<g class='pulse'><path d='M${cx + w / 2},${Y + 58} L${cx + w / 2},${Y + 44}' stroke='#4fc3f7' stroke-width='2.6' marker-end='url(#arrow6)'/></g>`;
    }
    this.el.push(s + `<text x='${X + Math.min(cells, 4) * (w + 6) / 2}' y='${Y + 78}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text></g>`);
    return X + Math.min(cells, 4) * (w + 6);
  }

  /** Screw classifier: an inclined trough with a rotating spiral and an overflow weir. */
  classifier(X, Y, label) {
    let s = `<g><path d='M${X - 96},${Y + 26} L${X + 96},${Y - 34} L${X + 96},${Y - 6} L${X - 96},${Y + 54} Z' fill='#1e88e5' fill-opacity='0.35' stroke='${this.fg}' stroke-width='1.6'/>`;
    s += `<path d='M${X - 108},${Y + 18} L${X - 108},${Y + 58} L${X - 88},${Y + 58} L${X - 88},${Y + 24} Z' fill='#1565c0' fill-opacity='0.5' stroke='${this.fg}'/>`;
    s += `<g class='spin-slow' style='transform-origin:${X}px ${Y + 12}px'>`;
    for (let i = 0; i < 9; i++) {
      const cx = X - 84 + i * 21, cy = Y + 38 - i * 6.6;
      s += `<ellipse cx='${cx}' cy='${cy}' rx='6' ry='13' fill='none' stroke='#e3f2fd' stroke-opacity='0.85' stroke-width='2.4'/>`;
    }
    s += `</g><line x1='${X - 108}' y1='${Y + 18}' x2='${X - 88}' y2='${Y + 18}' stroke='#4fc3f7' stroke-width='3'/>`;
    this.el.push(s + `<text x='${X}' y='${Y + 74}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text></g>`);
  }

  cyclones(X, Y, nOpen, nInst, label) {
    const k = Math.min(Math.max(Math.round(nInst / 3), 3), 5);
    for (let i = 0; i < k; i++) {
      const cx = X - (k - 1) * 16 + i * 32;
      const fill = i < Math.round(k * nOpen / Math.max(nInst, 1)) ? '#0288d1' : '#546e7a';
      this.el.push(`<rect x='${cx - 11}' y='${Y - 36}' width='22' height='16' fill='${fill}' stroke='${this.fg}'/>` +
        `<path d='M${cx - 11},${Y - 20} L${cx + 11},${Y - 20} L${cx + 3},${Y + 26} L${cx - 3},${Y + 26} Z' fill='${fill}' stroke='${this.fg}'/>`);
    }
    this.el.push(`<rect x='${X - k * 16 - 6}' y='${Y - 46}' width='${k * 32 + 12}' height='9' rx='4' fill='#455a64'/>` +
      `<text x='${X}' y='${Y + 42}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)} ${nOpen}/${nInst}</text>`);
  }

  /** Spiral concentrator: a helical trough seen from the side, with the heavy band on the inside. */
  spirals(X, Y, label, n = 3) {
    let s = '<g>';
    for (let j = 0; j < n; j++) {
      const cx = X + j * 74;
      s += `<line x1='${cx}' y1='${Y - 54}' x2='${cx}' y2='${Y + 60}' stroke='#455a64' stroke-width='4'/>`;
      for (let i = 0; i < 5; i++) {
        const cy = Y - 42 + i * 24;
        s += `<ellipse cx='${cx}' cy='${cy}' rx='27' ry='9' fill='none' stroke='#0288d1' stroke-width='3.4'/>`;
        s += `<ellipse cx='${cx}' cy='${cy - 1.5}' rx='13' ry='4' fill='none' stroke='#5d4037' stroke-width='2.6'/>`;
      }
      s += `<path d='M${cx - 16},${Y + 60} L${cx + 16},${Y + 60} L${cx + 9},${Y + 74} L${cx - 9},${Y + 74} Z' fill='#37474f' stroke='${this.fg}'/>`;
    }
    this.el.push(s + `<text x='${X + (n - 1) * 37}' y='${Y + 90}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text></g>`);
    return X + (n - 1) * 74;
  }

  /** Shaking table: a riffled deck with the fanned product band. */
  table(X, Y, label) {
    let s = `<g><path d='M${X - 92},${Y - 30} L${X + 92},${Y - 22} L${X + 92},${Y + 30} L${X - 92},${Y + 22} Z' fill='#f9a825' fill-opacity='0.35' stroke='${this.fg}' stroke-width='1.6'/>`;
    for (let i = 0; i < 11; i++) {
      const cx = X - 82 + i * 16;
      s += `<line x1='${cx}' y1='${Y - 26 + i * 0.6}' x2='${cx + 5}' y2='${Y + 24}' stroke='#8d6e63' stroke-width='2'/>`;
    }
    // the fan: heavy band at the far end, light swept off the side
    s += `<path d='M${X + 60},${Y - 20} L${X + 92},${Y - 20} L${X + 92},${Y - 2} L${X + 66},${Y - 2} Z' fill='#5d4037' fill-opacity='0.8'/>`;
    s += `<path d='M${X + 40},${Y + 2} L${X + 92},${Y + 4} L${X + 92},${Y + 28} L${X + 48},${Y + 24} Z' fill='#a1887f' fill-opacity='0.6'/>`;
    s += `<g class='shake'><rect x='${X - 104}' y='${Y - 10}' width='14' height='22' rx='3' fill='#37474f' stroke='${this.fg}'/></g>`;
    this.el.push(s + `<text x='${X}' y='${Y + 48}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text></g>`);
  }

  /** WHIMS: a rotating carousel of matrix boxes inside a field coil. */
  whims(X, Y, label, field) {
    let s = `<g><circle cx='${X}' cy='${Y}' r='46' fill='none' stroke='#ffe082' stroke-width='7' stroke-opacity='0.85'/>`;
    s += `<circle cx='${X}' cy='${Y}' r='34' fill='#c62828' fill-opacity='0.35' stroke='${this.fg}' stroke-width='1.6'/>`;
    s += `<g class='spin-slow' style='transform-origin:${X}px ${Y}px'>`;
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      s += `<rect x='${X + 24 * Math.cos(a) - 6}' y='${Y + 24 * Math.sin(a) - 6}' width='12' height='12' rx='2' fill='#ef9a9a' stroke='${this.fg}' stroke-width='0.8'/>`;
    }
    s += `</g>`;
    s += `<text x='${X}' y='${Y + 62}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text>`;
    s += `<text x='${X}' y='${Y + 76}' fill='${this.sub}' font-size='11' text-anchor='middle'>${f(field, '2')} T</text>`;
    this.el.push(s + '</g>');
  }

  thickener(X, Y, r, label) {
    this.el.push(`<path d='M${X - r},${Y - 24} L${X + r},${Y - 24} L${X + r},${Y + 8} L${X + 11},${Y + 40} L${X - 11},${Y + 40} L${X - r},${Y + 8} Z' fill='#795548' fill-opacity='0.6' stroke='${this.fg}' stroke-width='1.5'/>` +
      `<rect x='${X - r}' y='${Y - 24}' width='${2 * r}' height='12' fill='#29b6f6' fill-opacity='0.5'/>` +
      `<line x1='${X}' y1='${Y - 42}' x2='${X}' y2='${Y + 32}' stroke='${this.fg}' stroke-width='2'/>` +
      `<g class='rake' style='transform-origin:${X}px ${Y + 20}px'><line x1='${X - r + 12}' y1='${Y + 16}' x2='${X + r - 12}' y2='${Y + 16}' stroke='#ffcc80' stroke-width='3'/></g>` +
      `<text x='${X}' y='${Y + 60}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text>`);
  }

  tank(X, Y, label, color = WATER) {
    this.el.push(`<rect x='${X - 34}' y='${Y - 34}' width='68' height='68' rx='8' fill='${color}' fill-opacity='0.45' stroke='${this.fg}'/>` +
      `<ellipse cx='${X}' cy='${Y - 34}' rx='34' ry='7' fill='${color}' fill-opacity='0.6' stroke='${this.fg}'/>` +
      `<text x='${X}' y='${Y + 52}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>${x(label)}</text>`);
  }

  tsf(X, Y) {
    this.el.push(`<path d='M${X - 100},${Y + 36} L${X - 72},${Y - 34} L${X + 82},${Y - 44} L${X + 110},${Y + 36} Z' fill='#a1887f' fill-opacity='0.55' stroke='${this.fg}'/>` +
      `<ellipse cx='${X + 16}' cy='${Y - 10}' rx='54' ry='16' fill='#4fc3f7' fill-opacity='0.55'/>` +
      `<text x='${X}' y='${Y + 54}' fill='${this.fg}' font-size='12' font-weight='700' text-anchor='middle'>Tailings storage facility</text>`);
  }

  product(X, Y, label, sub, colour) {
    this.el.push(`<rect x='${X - 62}' y='${Y - 30}' width='124' height='60' rx='10' fill='${colour}' fill-opacity='0.30' stroke='${colour}' stroke-width='2.4'/>` +
      `<text x='${X}' y='${Y - 4}' fill='${this.fg}' font-size='13' font-weight='700' text-anchor='middle'>${x(label)}</text>` +
      `<text x='${X}' y='${Y + 15}' fill='${this.sub}' font-size='11' text-anchor='middle'>${x(sub)}</text>`);
  }

  svg() {
    let defs = Object.entries(MK).map(([c, i]) => `<marker id='arrow${i}' markerWidth='10' markerHeight='10' refX='8' refY='3' orient='auto'><path d='M0,0 L0,6 L9,3 z' fill='${c}'/></marker>`).join('');
    defs += `<marker id='arrow6' markerWidth='8' markerHeight='8' refX='6' refY='3' orient='auto'><path d='M0,0 L0,6 L7,3 z' fill='#4fc3f7'/></marker>`;
    return `<svg viewBox='0 0 ${W} ${H}' xmlns='http://www.w3.org/2000/svg' font-family='Inter,Segoe UI,Roboto,sans-serif'><defs>${defs}</defs>${this.el.join('')}${this.top.join('')}</svg>`;
  }
}

/** fs = payload of GET /overview/flowsheet (nodes, edges, kpis, streams). */
export function buildSVG(fs, unitStatus = {}, dark = true, kpis = null) {
  const u = Object.fromEntries((fs.nodes || []).map(n => [n.id, n.unit || {}]));
  const st = fs.streams || {};
  const k = kpis || fs.kpis || {};
  const c = new Canvas(dark);
  const ss = id => unitStatus[id] || 'normal';
  const worst = (...ids) => ids.map(ss).includes('alarm') ? 'alarm' : (ids.map(ss).includes('caution') ? 'caution' : 'normal');
  const sl = (sid, {assay = true, psd = false} = {}) => {
    const s = st[sid] || {};
    const parts = [`${f(s.solids_tph, ',0')} t/h`];
    if (s.solids_pct !== null && s.solids_pct !== undefined) parts.push(`${f(s.solids_pct)}% sol`);
    if (assay && s.fe_pct !== undefined) parts.push(`${f(s.fe_pct, '1')}% Fe`);
    if (assay && s.al2o3_pct !== undefined) parts.push(`${f(s.al2o3_pct, '2')}% Al₂O₃`);
    if (psd && s.p80_um) parts.push(s.p80_um > 3000 ? `P80 ${f(s.p80_um / 1000, '1')} mm` : `P80 ${f(s.p80_um)} µm`);
    return parts.join(' · ');
  };

  c.region(10, 46, 560, 300, 'A100', '100 · Crushing & screening');
  c.region(580, 46, 420, 300, 'A200', '200 · Rotary scrubbing & sizing');
  c.region(1010, 46, 470, 300, 'A300', '300 · Lump jigging');
  c.region(1490, 46, 420, 300, 'A500', '500 · Tertiary recrush');
  c.region(10, 360, 560, 320, 'A400', '400 · Screw classification');
  c.region(580, 360, 480, 320, 'A500', '500 · Fines jigging');
  c.region(1070, 360, 840, 320, 'A600', '600 · Cyclones & spiral concentrators');
  c.region(580, 694, 740, 240, 'A700', '700 · Shaking tables');
  c.region(10, 694, 560, 240, 'A800', '800 · Desliming and WHIMS');
  c.region(1330, 694, 580, 240, 'A900', '900 · Tailings');
  c.region(10, 948, 1900, 160, 'A900', '900 · Water recovery & recycle');

  c.el.push(`<text x='${W / 2}' y='28' fill='${c.fg}' font-size='17' font-weight='700' text-anchor='middle'>` +
    `Ore beneficiation plant — ${f(k.throughput_tph, ',0')} t/h ROM · lump ${f(k.lump_fe_pct, '2')} % Fe / ` +
    `${f(k.lump_al2o3_pct, '2')} % Al₂O₃ · sinter fines ${f(k.fines_fe_pct, '2')} % Fe · ` +
    `yield ${f(k.mass_yield_pct, '1')} % · Fe recovery ${f(k.fe_recovery_pct, '1')} % · ${f(k.energy_kwh_t, '2')} kWh/t</text>`);

  // ---- 100 crushing ---------------------------------------------------------------------------
  c.stockpile(80, 130, 'ROM ore');
  c.crusher(215, 112, 'Primary jaw');
  c.screen(360, 120, 'Sizing screen 40 mm');
  c.crusher(480, 200, 'Secondary cone', 0.85);
  c.stream([[138, 118], [178, 112]], ORE);
  c.stream([[253, 112], [310, 118]], ORE, sl('S02_primary_product', {assay: false, psd: true}), {at: 0, dy: -12});
  c.stream([[400, 132], [452, 178]], ORE, 'oversize', {width: 2.6});
  c.stream([[480, 244], [480, 276], [300, 276], [300, 146]], ORE, 'recrush recycle', {dashed: true, width: 2.4, at: 1, dy: 14});
  c.params(25, 210, 'Crushing & screening', [['ROM feed', `${f(k.throughput_tph, ',0')} t/h`],
    ['Head grade', `${f((st.S01_rom || {}).fe_pct, '2')} % Fe`],
    ['Head alumina', `${f((st.S01_rom || {}).al2o3_pct, '2')} % Al₂O₃`],
    ['Secondary CSS', `${f((u.crushing || {}).css_mm)} mm`],
    ['Screen CL', `${f((u.sizing_screen || {}).circulating_load_pct)} %`],
    ['Screen loading', `${f((u.sizing_screen || {}).screen_loading_tph_m2, '1')} t/h/m²`]],
  worst('secondary_crusher', 'sizing_screen'), 250, 'secondary_crusher');

  // ---- 200 scrubbing ---------------------------------------------------------------------------
  c.scrubber(700, 120, 'Rotary scrubber');
  c.screen(900, 126, 'Trommel 10 mm', 92);
  c.stream([[412, 120], [588, 120]], ORE, sl('S04_screen_undersize', {assay: false, psd: true}), {at: 0, dy: -12});
  c.stream([[812, 120], [852, 124]], SLURRY, '', {width: 2.6});
  c.params(596, 208, 'Rotary scrubber', [['Drum speed', `${f((u.scrubber || {}).speed_pct_critical, '1')} % Cs`],
    ['Residence', `${f((u.scrubber || {}).residence_time_min, '2')} min`],
    ['Clay detached', `${f((u.scrubber || {}).clay_detachment_pct, '1')} %`],
    ['Clay removed', `${f((u.scrubber || {}).clay_removed_pct_of_feed, '2')} % of feed`],
    ['Water added', `${f((u.scrubber || {}).water_added_m3_h)} m³/h`],
    ['Power', `${f((u.scrubber || {}).power_kw)} kW`]], ss('scrubber'), 260, 'scrubber');

  // ---- 300 lump jigging --------------------------------------------------------------------------
  c.jig(1032, 78, 'Lump jig', (u.lump_jig || {}).n_cells || 4);
  c.product(1382, 92, 'LUMP ORE', 'blast-furnace feed', '#8d6e63');
  c.stream([[946, 126], [990, 100], [1024, 90]], ORE, '+10 mm ' + sl('S06_lumps'), {at: 0, dy: -30});
  c.stream([[1300, 90], [1318, 92]], HEAVY, '', {width: 3.4});
  c.top.push(`<text x='1382' y='150' fill='${c.sub}' font-size='11' text-anchor='middle'>` +
    `${f(k.lump_tph, ',0')} t/h · ${f(k.lump_fe_pct, '2')} % Fe · ${f(k.lump_al2o3_pct, '2')} % Al₂O₃</text>`);
  c.params(1020, 214, 'Lump jig', [['Cut density', `${f((u.lump_jig || {}).cut_sg_achieved, '3')} SG`],
    ['Bed condition', `${f((u.lump_jig || {}).bed_looseness, '3')}`],
    ['Ep at 10 mm', `${f((u.lump_jig || {}).ep_at_10mm, '3')} SG`],
    ['Loading', `${f((u.lump_jig || {}).loading_tph_m2, '1')} t/h/m²`],
    ['Yield', `${f((u.lump_jig || {}).yield_pct, '1')} %`],
    ['Conc. Fe', `${f((u.lump_jig || {}).conc_fe_pct, '2')} %`]], ss('lump_jig'), 270, 'lump_jig');

  // ---- 500 recrush --------------------------------------------------------------------------------
  c.crusher(1616, 100, 'Tertiary cone', 0.9);
  c.screen(1774, 116, 'Recrush screen', 92);
  c.stream([[1300, 148], [1420, 172], [1566, 132]], SLURRY, 'floats · ' + sl('S09a_lump_jig_floats'), {at: 0, dy: 18});
  c.stream([[1662, 100], [1730, 112]], ORE, '', {width: 2.4});
  c.stream([[1800, 128], [1848, 150], [1848, 194], [1090, 194], [1090, 146]], ORE, '+10 mm back to the jig', {dashed: true, width: 2.4, at: 2, dy: 16});
  c.params(1560, 214, 'Tertiary recrush', [['CSS', `${f((u.tertiary_crusher || {}).css_mm, '1')} mm`],
    ['Feed', `${f((u.tertiary_crusher || {}).feed_tph, ',0')} t/h`],
    ['Circulating load', `${f((u.tertiary_crusher || {}).circulating_load_pct, '1')} %`],
    ['Power', `${f((u.tertiary_crusher || {}).power_kw)} kW`],
    ['Utilisation', `${f((u.tertiary_crusher || {}).power_utilisation_pct, '1')} %`]],
  ss('tertiary_crusher'), 260, 'tertiary_crusher');

  // ---- 400 classification --------------------------------------------------------------------------
  c.classifier(318, 452, 'Screw classifier');
  c.stream([[900, 150], [900, 322], [470, 322], [392, 408]], SLURRY, '-10 mm fines · ' + sl('S07_scrubber_fines'), {at: 1, dy: -12});
  c.stream([[1774, 150], [1774, 334], [268, 334], [268, 424]], ORE, '-10 mm recrush product', {dashed: true, width: 2.4, at: 1, dy: -10});
  c.params(25, 534, 'Screw classifier', [['Cut size (quartz)', `${f((u.classifier || {}).d50_quartz_um)} µm`],
    ['Cut size (hematite)', `${f((u.classifier || {}).d50_hematite_um)} µm`],
    ['Equal-settling ratio', `${f((u.classifier || {}).equal_settling_ratio, '2')} ×`],
    ['Sand loading', `${f((u.classifier || {}).sand_loading_tph_m2, '2')} t/h/m²`],
    ['Sand', `${f((u.classifier || {}).sand_tph, ',0')} t/h`],
    ['Overflow (slimes)', `${f((u.classifier || {}).overflow_tph, ',0')} t/h`]],
  ss('spiral_classifier'), 265, 'spiral_classifier');

  // ---- 500 fines jigging ----------------------------------------------------------------------------
  c.screen(660, 420, 'Fines screen 2 mm', 96);
  c.jig(790, 470, 'Fines jig', (u.fines_jig || {}).n_cells || 4, 52);
  c.stream([[428, 432], [612, 422]], SLURRY, 'sand · ' + sl('S11_classifier_sand', {psd: true}), {at: 0, dy: -12});
  c.stream([[700, 432], [750, 460]], SLURRY, '+2 mm', {width: 2.4});
  c.stream([[1000, 486], [1046, 520], [1056, 700], [1118, 760]], HEAVY, 'jig sinks', {width: 2.6, at: 2, dy: -8});
  c.stream([[830, 548], [830, 664], [1656, 664], [1656, 138]], SLURRY, 'fines-jig floats to recrush', {dashed: true, width: 2.2, at: 1, dy: -10});
  c.params(596, 568, 'Fines jig', [['Cut density', `${f((u.fines_jig || {}).cut_sg_achieved, '3')} SG`],
    ['Ep at 1 mm', `${f((u.fines_jig || {}).ep_at_1mm, '3')} SG`],
    ['Loading', `${f((u.fines_jig || {}).loading_tph_m2, '1')} t/h/m²`],
    ['Conc. Fe', `${f((u.fines_jig || {}).conc_fe_pct, '2')} %`],
    ['Fe recovery', `${f((u.fines_jig || {}).fe_recovery_pct, '1')} %`]], ss('fines_jig'), 250, 'fines_jig');

  // ---- 600 cyclones and spirals -----------------------------------------------------------------------
  c.cyclones(1166, 444, (u.spiral_cyclone || {}).cyclones_open || 9, 12, 'Spiral-feed cyclones');
  c.spirals(1432, 468, 'Spiral concentrators', 3);
  c.stream([[706, 434], [980, 476], [1110, 458]], SLURRY, '-2 mm', {width: 2.6, at: 1, dy: -10});
  c.stream([[1216, 456], [1310, 470], [1390, 462]], SLURRY, sl('S14_spiral_cyclone_uf', {psd: true}), {at: 0, dy: -14});
  c.stream([[1166, 394], [1166, 356], [190, 356], [190, 414], [140, 726]], SLURRY, 'cyclone overflow to desliming', {dashed: true, width: 2.2, at: 0.3, dy: -10});
  c.stream([[1352, 412], [1284, 360], [1268, 690], [1250, 758]], CONC, 'spiral concentrate', {width: 2.6, at: 2, dy: -10});
  c.stream([[1394, 556], [1150, 668], [890, 752]], SLURRY, 'spiral middling to tables', {width: 2.4, at: 1, dy: -14});
  c.stream([[1540, 556], [1760, 640], [1700, 756]], TAILS, 'spiral tailing', {width: 2.4, at: 0, dy: -14});
  c.params(1086, 576, 'Spiral concentrators', [['Starts', `${f((u.spirals || {}).n_starts)}`],
    ['Loading', `${f((u.spirals || {}).load_fraction, '3')} × nameplate`],
    ['Conc. cut', `${f((u.spirals || {}).cut_sg_conc, '2')} SG`],
    ['Middling cut', `${f((u.spirals || {}).cut_sg_middling, '2')} SG`],
    ['Ep at 500 µm', `${f((u.spirals || {}).ep_at_500um, '3')} SG`],
    ['Conc. Fe', `${f((u.spirals || {}).conc_fe_pct, '2')} %`],
    ['Fe recovery', `${f((u.spirals || {}).fe_recovery_pct, '1')} %`]], ss('spirals'), 280, 'spirals');

  // ---- 700 tables -------------------------------------------------------------------------------------
  c.table(790, 786, 'Shaking tables');
  c.product(1180, 786, 'SINTER FINES', 'sinter plant feed', '#f9a825');
  c.stream([[884, 782], [1110, 784]], CONC, 'table concentrate', {width: 2.6, at: 0, dy: -12});
  c.stream([[884, 816], [1000, 908], [1346, 908], [1388, 830]], TAILS, 'table tailing', {width: 2.2, at: 1, dy: 15});
  c.params(600, 846, 'Shaking tables', [['Decks', `${f((u.tables || {}).n_decks)}`],
    ['Loading', `${f((u.tables || {}).load_fraction, '3')} × nameplate`],
    ['Ep at 200 µm', `${f((u.tables || {}).ep_at_200um, '3')} SG`],
    ['Conc. Fe', `${f((u.tables || {}).conc_fe_pct, '2')} %`],
    ['Fe recovery', `${f((u.tables || {}).fe_recovery_pct, '1')} %`]], ss('shaking_tables'), 240, 'shaking_tables');
  c.top.push(`<text x='1180' y='836' fill='${c.sub}' font-size='11' text-anchor='middle'>` +
    `${f(k.fines_tph, ',0')} t/h · ${f(k.fines_fe_pct, '2')} % Fe · ${f(k.fines_al2o3_pct, '2')} % Al₂O₃</text>`);

  // ---- 800 desliming and WHIMS -------------------------------------------------------------------------
  c.cyclones(120, 780, (u.deslime_cyclone || {}).cyclones_open || 11, 14, 'Desliming cyclones');
  c.whims(320, 780, 'WHIMS', (u.whims || {}).field_tesla);
  c.product(490, 780, 'PELLET FEED', 'to the pellet plant', '#c62828');
  c.stream([[214, 420], [168, 620], [124, 730]], SLURRY, 'slimes ' + sl('S12_classifier_overflow'), {at: 0, dy: -18});
  c.stream([[160, 790], [270, 786]], SLURRY, 'U/F', {width: 2.4});
  c.stream([[368, 780], [424, 780]], MAG, 'magnetics', {width: 2.6});
  c.stream([[120, 826], [120, 940], [1376, 940], [1400, 828]], TAILS, 'ultrafine slimes', {dashed: true, width: 2.2, at: 1, dy: 15});
  c.stream([[320, 842], [400, 958], [1390, 958], [1414, 828]], TAILS, 'WHIMS non-magnetics', {width: 2.2, at: 1, dy: 16});
  c.params(20, 846, 'Desliming & WHIMS', [['Deslime cut', `${f((u.deslime_cyclone || {}).d50c_um, '1')} µm`],
    ['Field', `${f((u.whims || {}).field_tesla, '2')} T`],
    ['Matrix', `${(u.whims || {}).matrix || '—'}`],
    ['Loading', `${f((u.whims || {}).loading_fraction, '3')} ×`],
    ['Conc. Fe', `${f((u.whims || {}).conc_fe_pct, '2')} %`]], worst('deslime_cyclone', 'whims'), 250, 'whims');
  c.top.push(`<text x='490' y='826' fill='${c.sub}' font-size='11' text-anchor='middle'>` +
    `${f(k.pellet_fines_tph, ',0')} t/h · ${f(k.pellet_fines_fe_pct, '2')} % Fe</text>`);

  // ---- 900 tailings and water -----------------------------------------------------------------------------
  c.thickener(1452, 776, 80, 'Tailings thickener');
  c.tsf(1740, 800);
  c.tank(700, 1030, 'Process water tank');
  c.tank(1180, 1030, 'Fresh make-up', '#4dd0e1');
  c.stream([[1536, 808], [1620, 806]], TAILS, sl('S29_tails_underflow', {assay: false}), {at: 0, dy: -12});
  c.stream([[1452, 734], [1452, 1004], [744, 1030]], WATER, `thickener overflow · ${f(k.water_recycle_pct, '0')} % recycled`, {at: 1, dy: -10});
  c.stream([[1146, 1030], [744, 1030]], WATER, 'fresh water', {width: 2.4});
  c.stream([[666, 1004], [430, 972], [250, 700], [250, 496]], WATER, 'recycle to scrubber, jigs, spirals and tables', {dashed: true, width: 2.6, at: 0, dy: -14});
  c.params(1336, 846, 'Tailings & water', [['Tailings', `${f(k.tailings_tph, ',0')} t/h`],
    ['Tailings Fe', `${f(k.tailings_fe_pct, '2')} %`],
    ['U/F density', `${f(k.tails_uf_solids_pct, '1')} % solids`],
    ['Overflow TSS', `${f(k.tails_overflow_tss_mg_l)} mg/L`],
    ['Fresh water', `${f(k.fresh_water_m3_t, '3')} m³/t`],
    ['Recycled', `${f(k.water_recycle_pct, '1')} %`]], worst('tails_thickener', 'water_recovery'), 250, 'tails_thickener');
  c.params(20, 972, 'Plant summary', [['Saleable', `${f(k.saleable_tph, ',0')} t/h`],
    ['Mass yield', `${f(k.mass_yield_pct, '1')} %`], ['Fe recovery', `${f(k.fe_recovery_pct, '1')} %`],
    ['Energy', `${f(k.energy_kwh_t, '2')} kWh/t`], ['Margin', `$${f(k.margin_usd_h, ',0')}/h`]],
  'normal', 250, '');

  let leg = `<g transform='translate(1480,1030)'>`;
  [[ORE, 'Dry ore', false], [SLURRY, 'Slurry', false], [HEAVY, 'Heavy (sinks)', false],
    [CONC, 'Concentrate', false], [MAG, 'Magnetics', false], [TAILS, 'Tailings', false],
    [WATER, 'Water', true]].forEach(([col, lab, d], i) => {
    const row = i % 4, coln = Math.floor(i / 4);
    leg += `<line x1='${row * 104}' y1='${coln * 20}' x2='${row * 104 + 26}' y2='${coln * 20}' stroke='${col}' stroke-width='4' ${d ? "stroke-dasharray='8 5'" : ''}/>` +
      `<text x='${row * 104 + 32}' y='${coln * 20 + 4}' fill='${c.fg}' font-size='11'>${lab}</text>`;
  });
  c.el.push(leg + '</g>');
  return c.svg();
}

/** Mounts the SVG with wheel-zoom, drag-pan, reset, export and click-through to Unit operations. */
export function mountFlowsheet(container, fs, unitStatus, dark, kpis, onUnit) {
  container.innerHTML = '';
  container.classList.add('canvas-wrap');
  container.innerHTML = buildSVG(fs, unitStatus, dark, kpis);
  const svg = container.querySelector('svg');
  let vb = [0, 0, W, H];
  const set = () => svg.setAttribute('viewBox', vb.join(' '));
  const zoom = (fac, cx = vb[0] + vb[2] / 2, cy = vb[1] + vb[3] / 2) => {
    vb = [cx - (cx - vb[0]) / fac, cy - (cy - vb[1]) / fac, vb[2] / fac, vb[3] / fac];
    set();
  };
  const tools = document.createElement('div');
  tools.className = 'tools';
  [['＋', () => zoom(1.25)], ['－', () => zoom(0.8)], ['⟲', () => { vb = [0, 0, W, H]; set(); }], ['⤓ SVG', () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([svg.outerHTML], {type: 'image/svg+xml'}));
    a.download = 'ore_beneficiation_flowsheet.svg';
    a.click();
  }]].forEach(([t, fn]) => { const b = document.createElement('button'); b.className = 'btn'; b.textContent = t; b.onclick = fn; tools.append(b); });
  container.append(tools);
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, vb[0] + (e.clientX - r.left) / r.width * vb[2],
         vb[1] + (e.clientY - r.top) / r.height * vb[3]);
  }, {passive: false});
  let drag = null, moved = false;
  svg.addEventListener('mousedown', e => { drag = [e.clientX, e.clientY]; moved = false; });
  window.addEventListener('mouseup', () => { drag = null; });
  window.addEventListener('mousemove', e => {
    if (!drag) return;
    const r = svg.getBoundingClientRect();
    const dx = e.clientX - drag[0], dy = e.clientY - drag[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    vb[0] -= dx / r.width * vb[2];
    vb[1] -= dy / r.height * vb[3];
    drag = [e.clientX, e.clientY];
    set();
  });
  svg.addEventListener('click', e => {
    if (moved) return;
    const g = e.target.closest('[data-unit]');
    if (g && g.dataset.unit && onUnit) onUnit(g.dataset.unit);
  });
}
