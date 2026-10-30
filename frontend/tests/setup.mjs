// Headless browser environment (jsdom) + mock-data loader for Node tests.
import {readFileSync} from 'node:fs';
import {register} from 'node:module';
import {gunzipSync} from 'node:zlib';
import {JSDOM} from 'jsdom';

register('./hooks.mjs', import.meta.url);
const html = `<!DOCTYPE html><html data-theme="dark"><body><div id="app"><aside id="sidebar"></aside><main id="main"><header id="topbar"></header>
<section id="view"></section></main></div><div id="toasts"></div><div id="modal-root"></div></body></html>`;
export const dom = new JSDOM(html, {url: 'http://localhost/', pretendToBeVisual: true});
const w = dom.window;
export const plots = [];
w.Plotly = {newPlot: (el, data, layout) => { plots.push({data, layout}); if (!Array.isArray(data)) throw new Error('bad plot data'); }, Plots: {resize() {}}};
w.OBDT_CONFIG = {BACKEND_BASE_URL: 'http://127.0.0.1:9', MOCK_MODE: 'true', APP_ENV: 'test', REQUEST_TIMEOUT_S: 5, LONG_TIMEOUT_S: 10, DEFAULT_PLANT: 'IX-OB-01'};
w.ResizeObserver = class { observe() {} disconnect() {} };
for (const k of ['window', 'document', 'localStorage', 'sessionStorage', 'location', 'Node', 'HTMLElement', 'Event', 'Blob', 'URLSearchParams', 'CustomEvent', 'getComputedStyle']) {
  try { Object.defineProperty(globalThis, k, {value: k === 'window' ? w : w[k], configurable: true, writable: true}); } catch { /* read-only global */ }
}
globalThis.requestAnimationFrame = () => 0;
globalThis.OBDT_CONFIG = w.OBDT_CONFIG;
const mock = await import('../js/api/mock.js');
mock.setLoader(async name => gunzipSync(readFileSync(new URL(`../data/mock/${name}.json.gz`, import.meta.url))).toString('utf8'));
export const errors = [];
w.addEventListener('error', e => errors.push(e.error || e.message));
