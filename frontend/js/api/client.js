// Central API service layer: fetch with timeouts & retries, per-endpoint cache TTL, schema validation,
// X-API-Key auth, automatic mock fallback when the backend is unreachable (MOCK_MODE=auto).
import * as S from '../state.js';
import {ENDPOINTS} from './endpoints.js';
export {ENDPOINTS};
import * as mock from './mock.js';
import {validate} from './schemas.js';

export class ApiError extends Error {
  constructor(message, status = null, detail = null) { super(message); this.status = status; this.detail = detail; }
}
const cache = new Map();
const statusSubs = new Set();
export let lastStatus = {mode: '—', ok: true};
function setStatus(st) {
  lastStatus = {...lastStatus, ...st, time: new Date().toISOString().slice(11, 19) + ' UTC'};
  statusSubs.forEach(f => f(lastStatus));
}
export const onStatus = f => { statusSubs.add(f); return () => statusSubs.delete(f); };
const cfg = () => window.OBDT_CONFIG || {};

export function useMock() {
  const ov = S.get('mockOverride');
  if (ov !== null && ov !== undefined) return !!ov;
  return ['true', '1', 'yes'].includes(String(cfg().MOCK_MODE || 'auto').toLowerCase());
}
const allowFallback = () => ['auto', 'true', '1', 'yes'].includes(String(cfg().MOCK_MODE || 'auto').toLowerCase());

function buildUrl(ep, pp, params) {
  let path = ep.path;
  for (const [k, v] of Object.entries(pp || {})) path = path.replace(`{${k}}`, encodeURIComponent(v));
  const base = (S.get('backendUrl') || cfg().BACKEND_BASE_URL || '').replace(/\/$/, '');
  const qs = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null)).toString();
  return base + path + (qs ? `?${qs}` : '');
}

async function http(method, url, body, timeoutS) {
  let last;
  for (let attempt = 0; attempt < (method === 'GET' ? 2 : 1); attempt++) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutS * 1000);
    try {
      const headers = {Accept: 'application/json'};
      if (body !== null && body !== undefined) headers['Content-Type'] = 'application/json';
      const key = S.get('apiKey') || cfg().API_KEY;
      if (key) headers['X-API-Key'] = key;
      const r = await fetch(url, {method, headers, body: body == null ? undefined : JSON.stringify(body), signal: ctl.signal});
      clearTimeout(timer);
      if (r.status >= 500 && attempt === 0 && method === 'GET') { await new Promise(res => setTimeout(res, 800)); continue; }
      if (!r.ok) {
        let err = {};
        try { err = (await r.json()).error || {}; } catch { err = {message: `HTTP ${r.status}`}; }
        throw new ApiError(err.message || `HTTP ${r.status}`, r.status, err.detail);
      }
      return await r.json();
    } catch (e) {
      clearTimeout(timer);
      if (e instanceof ApiError) throw e;
      last = e;   // network error, CORS rejection, abort (timeout)
      await new Promise(res => setTimeout(res, 400));
    }
  }
  throw new ApiError(`Backend unreachable: ${last && last.name === 'AbortError' ? 'timeout' : (last && last.message) || last}`);
}

export async function call(name, pp = {}, params = {}, body = null) {
  const ep = ENDPOINTS[name];
  if (!ep) throw new ApiError(`unknown endpoint ${name}`);
  if (useMock()) {
    const d = await mock.respond(name, pp, params, body);
    setStatus({mode: 'mock', ok: true, endpoint: name, latencyMs: 0, error: null});
    return d;
  }
  const t0 = performance.now();
  let data;
  try {
    data = await http(ep.method, buildUrl(ep, pp, ep.method === 'GET' ? params : {}), ep.method === 'GET' ? null : body,
      Number(ep.long ? cfg().LONG_TIMEOUT_S || 240 : cfg().REQUEST_TIMEOUT_S || 45));
  } catch (e) {
    if (e instanceof ApiError && e.status === null && allowFallback()) {
      setStatus({mode: 'mock-fallback', ok: false, endpoint: name, error: e.message, latencyMs: null});
      return mock.respond(name, pp, params, body);
    }
    setStatus({mode: 'live', ok: false, endpoint: name, error: e.message, latencyMs: null});
    throw e;
  }
  const issues = ep.schema ? validate(ep.schema, data) : [];
  setStatus({mode: 'live', ok: !issues.length, endpoint: name, latencyMs: performance.now() - t0,
    error: issues.length ? `Schema mismatch: ${issues.join('; ')}` : null});
  return data;
}

export async function get(name, kw = {}) {
  const ep = ENDPOINTS[name];
  const pp = {}, params = {};
  for (const [k, v] of Object.entries(kw)) (ep.path.includes(`{${k}}`) ? pp : params)[k] = v;
  const key = JSON.stringify([name, pp, params, S.get('backendUrl'), useMock()]);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.t < (ep.ttl || 30) * 1000) return hit.p;
  const p = call(name, pp, params);
  cache.set(key, {t: Date.now(), p});
  p.catch(() => cache.delete(key));
  return p;
}
export const post = (name, body, pp = {}) => call(name, pp, {}, body);
export const clearCache = () => cache.clear();
