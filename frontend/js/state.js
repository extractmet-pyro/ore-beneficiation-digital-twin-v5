// Application state: single store, persisted to localStorage, with change subscription.
import {PERSONAS} from './utils/constants.js';

const KEY = 'obdt-state';
const cfg = () => window.OBDT_CONFIG || {};
const DEFAULTS = () => ({plantId: cfg().DEFAULT_PLANT || 'IX-OB-01', persona: 'Process engineer', theme: 'dark', unitSystem: 'metric',
  window: '8h', mockOverride: null, backendUrl: cfg().BACKEND_BASE_URL || 'http://localhost:8000', apiKey: cfg().API_KEY || '',
  scenarios: [], operatorLog: [], lastOptimization: null, lastSimulation: null, selectedUnit: null, autoRefresh: false, refreshS: 60,
  collapsed: false, acked: []});
const PERSIST = ['plantId', 'persona', 'theme', 'unitSystem', 'window', 'mockOverride', 'backendUrl', 'apiKey', 'scenarios', 'operatorLog',
  'selectedUnit', 'autoRefresh', 'refreshS', 'collapsed', 'acked'];

let state = DEFAULTS();
try { Object.assign(state, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch { /* corrupted storage ignored */ }
const subs = new Set();

export const get = k => state[k];
export function set(k, v) {
  state[k] = v;
  if (PERSIST.includes(k)) {
    try { localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(PERSIST.map(p => [p, state[p]])))); } catch { /* quota */ }
  }
  subs.forEach(f => f(k, v));
}
export const subscribe = f => { subs.add(f); return () => subs.delete(f); };
export const all = () => state;
export function reset() { state = DEFAULTS(); localStorage.removeItem(KEY); subs.forEach(f => f('*')); }
export function can(cap) { return !!(PERSONAS[state.persona] || {})[cap]; }
export function logAction(action, detail, outcome = 'logged') {
  const log = [{time_utc: new Date().toISOString().slice(0, 19).replace('T', ' '), persona: state.persona, plant: state.plantId, action, detail, outcome},
    ...state.operatorLog].slice(0, 200);
  set('operatorLog', log);
}
