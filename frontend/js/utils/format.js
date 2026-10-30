// Number / time / label formatting (d3-like spec subset: [+][,].Nf | .Ng | .N%)
export function fmt(v, spec = '.2f', unit = '', none = '—') {
  if (v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v))) return none;
  if (typeof v !== 'number') { const n = Number(v); if (!Number.isFinite(n)) return String(v); v = n; }
  const m = /^(\+)?(,)?\.(\d+)([fg%])$/.exec(spec) || [null, '', '', '2', 'f'];
  const [, plus, comma, dp, typ] = m; const d = Number(dp);
  let s;
  if (typ === '%') s = (v * 100).toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: !!comma}) + '%';
  else if (typ === 'g') s = Number(v.toPrecision(Math.max(d, 1))).toLocaleString('en-US', {maximumFractionDigits: 10, useGrouping: !!comma});
  else s = v.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: !!comma});
  if (plus && v >= 0) s = '+' + s;
  return unit ? `${s} ${unit}` : s;
}
export const IMPERIAL = {'t/h': ['st/h', 1 / 0.907185], kPa: ['psi', 0.145038], 'm³/h': ['USgpm', 4.402868], kW: ['hp', 1.341022],
  'kWh/t': ['kWh/st', 0.907185], 't/d': ['st/d', 1 / 0.907185], 'm³/t': ['USgal/st', 239.65]};
export function toDisplay(v, unit, system = 'metric') {
  if (system !== 'imperial' || v === null || v === undefined || !IMPERIAL[unit]) return [v, unit];
  return [v * IMPERIAL[unit][1], IMPERIAL[unit][0]];
}
export function money(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)} M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)} k`;
  return `${s}$${a.toFixed(0)}`;
}
export function ageStr(iso) {
  if (!iso) return '—';
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (!Number.isFinite(s)) return iso;
  if (s < 90) return `${Math.max(s, 0).toFixed(0)} s ago`;
  if (s < 5400) return `${(s / 60).toFixed(0)} min ago`;
  return `${(s / 3600).toFixed(1)} h ago`;
}
export const tsShort = iso => iso ? iso.replace('T', ' ').replace('Z', ' UTC').slice(0, 20) : '—';
const REP = {pct: '%', tph: 't/h', kw: 'kW', um: 'µm', m3: 'm³', kpa: 'kPa', kwh: 'kWh', usd: 'USD', cs: 'Cs', sg: 'SG', p80: 'P80',
  d50c: 'd50c', tss: 'TSS', uf: 'U/F', jg: 'Jg', ph: 'pH'};
export function humanise(key) {
  const s = String(key).split('_').map(w => REP[w] || w).join(' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
export function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])); }
export const isNum = v => typeof v === 'number' && Number.isFinite(v);
