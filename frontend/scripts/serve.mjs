// Zero-dependency static server for local use:  node scripts/serve.mjs [port]   → http://localhost:8080
import {createReadStream, existsSync, statSync} from 'node:fs';
import {createServer} from 'node:http';
import {extname, join, normalize} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const port = Number(process.argv[2] || process.env.PORT || 8080);
const MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.json': 'application/json', '.gz': 'application/octet-stream', '.png': 'image/png', '.ico': 'image/x-icon', '.txt': 'text/plain'};
createServer((req, res) => {
  let p = normalize(decodeURIComponent(req.url.split('?')[0])).replace(/^(\.\.[/\\])+/, '');
  let f = join(root, p);
  if (!f.startsWith(root)) { res.writeHead(403).end(); return; }
  if (existsSync(f) && statSync(f).isDirectory()) f = join(f, 'index.html');
  if (!existsSync(f)) { res.writeHead(404, {'Content-Type': 'text/plain'}).end('not found'); return; }
  res.writeHead(200, {'Content-Type': MIME[extname(f)] || 'application/octet-stream', 'Cache-Control': 'no-cache'});
  createReadStream(f).pipe(res);
}).listen(port, () => console.log(`Operator desk v2 on http://localhost:${port}`));
