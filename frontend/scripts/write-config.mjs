// Generates config.js from environment variables (Render static-site build command, Docker entrypoint, CI).
//   BACKEND_BASE_URL=https://… MOCK_MODE=auto node scripts/write-config.mjs
//
// This script is also the last place a misconfigured deployment can be caught cheaply. The desk
// falls back to the captured payloads whenever a call fails at the network layer, which is the
// right behaviour at runtime but hides a wrong BACKEND_BASE_URL behind a working-looking page.
// So the checks below are loud, and a production build with no backend URL fails outright.
import {createHash} from 'node:crypto';
import {writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const e = process.env;
const pwHash = e.APP_PASSWORD ? createHash('sha256').update(e.APP_PASSWORD).digest('hex') : (e.APP_PASSWORD_SHA256 || '');
const cfg = {
  BACKEND_BASE_URL: (e.BACKEND_BASE_URL || 'http://localhost:8000').replace(/\/$/, ''),
  APP_ENV: e.APP_ENV || 'production',
  MOCK_MODE: e.MOCK_MODE || 'auto',
  API_KEY: e.API_KEY || '',
  AUTH_MODE: e.AUTH_MODE || 'none',
  APP_PASSWORD_SHA256: pwHash,
  REQUEST_TIMEOUT_S: Number(e.REQUEST_TIMEOUT_S || 45),
  LONG_TIMEOUT_S: Number(e.LONG_TIMEOUT_S || 240),
  DEFAULT_PLANT: e.DEFAULT_PLANT || 'IX-OB-01',
  APP_TITLE: e.APP_TITLE || 'Industry-X Ore Beneficiation Twin',
};

// ---------------------------------------------------------------- deployment sanity checks
// Only a real deployment is held to these. APP_ENV defaults to 'production' for the generated
// file, but a bare `node scripts/write-config.mjs` on a laptop must keep working, so the checks
// fire only when production was asked for explicitly or we are building on Render.
const deploying = e.APP_ENV === 'production' || !!e.RENDER || !!e.RENDER_SERVICE_ID;
const prod = deploying;
const url = cfg.BACKEND_BASE_URL;
const local = /^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|$)/i.test(url);
const banner = s => console.error(`\n${'='.repeat(78)}\n${s}\n${'='.repeat(78)}\n`);

if (prod && !e.BACKEND_BASE_URL) {
  banner(
    'BUILD FAILED — BACKEND_BASE_URL is not set.\n\n' +
    'This is a production build, so config.js would have pointed the desk at\n' +
    '  http://localhost:8000\n' +
    'which does not exist on a visitor\'s machine. Every call would fail at the network\n' +
    'layer and the desk would quietly show "MOCK fallback, backend unreachable".\n\n' +
    'Fix: set BACKEND_BASE_URL on this service to the API URL, for example\n' +
    '  https://obdt-v5-api.onrender.com\n' +
    'with https, and no trailing slash. Then redeploy.\n\n' +
    'To build a desk that is deliberately offline, set MOCK_MODE=true as well.');
  if (cfg.MOCK_MODE !== 'true') process.exit(1);
}
if (prod && local) {
  banner('WARNING — BACKEND_BASE_URL points at a local address: ' + url +
         '\nA browser on another machine cannot reach it. The desk will fall back to mock.');
}
if (prod && url.startsWith('http://') && !local) {
  banner('WARNING — BACKEND_BASE_URL uses http, not https: ' + url +
         '\nRender serves this desk over https, and browsers block mixed content, so every\n' +
         'call will be refused before it leaves the page. Use https.');
}
if (e.BACKEND_BASE_URL && /\/api(\/v1)?$/.test(url)) {
  banner('WARNING — BACKEND_BASE_URL ends in /api or /api/v1: ' + url +
         '\nGive the service root only; the desk appends /api/v1 itself. As written the calls\n' +
         'would go to /api/v1/api/v1/… and return 404.');
}

writeFileSync(join(root, 'config.js'), `/* generated ${new Date().toISOString()} by scripts/write-config.mjs — do not commit secrets */\nwindow.OBDT_CONFIG = ${JSON.stringify(cfg, null, 2)};\n`);
console.log('config.js written:', {...cfg, API_KEY: cfg.API_KEY ? '***' : '', APP_PASSWORD_SHA256: cfg.APP_PASSWORD_SHA256 ? '***' : ''});
if (prod && e.BACKEND_BASE_URL && !local) {
  console.log(`\nAfter this deploy, confirm the API allows this desk's origin:\n` +
              `  ALLOWED_ORIGINS on the API service must contain the desk URL exactly.\n` +
              `  Check with:  curl -s ${url}/health\n`);
}
