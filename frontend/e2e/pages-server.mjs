// Minimal static server that behaves like GitHub Pages for a project site:
// files under /<prefix>/, unknown paths get 404.html with status 404. No dependencies.
// Usage: node e2e/pages-server.mjs <dir> [port] [prefix]
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve, sep } from 'node:path';

const [dir = 'dist/frontend/browser', port = '8095', prefix = '/bondMIND/'] = process.argv.slice(2);
const root = resolve(dir);
const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.ico': 'image/x-icon', '.svg': 'image/svg+xml', '.png': 'image/png',
};

createServer(async (req, res) => {
  const url = decodeURIComponent((req.url ?? '/').split('?')[0]);
  if (!url.startsWith(prefix)) {
    res.writeHead(302, { Location: prefix }).end();
    return;
  }
  let file = normalize(join(root, url.slice(prefix.length)));
  if (!file.startsWith(root + sep) && file !== root) return res.writeHead(403).end();
  try {
    if ((await stat(file)).isDirectory()) file = join(file, 'index.html');
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': types[extname(file)] ?? 'application/octet-stream' }).end(body);
  } catch {
    const body = await readFile(join(root, '404.html')).catch(() => Buffer.from('Not found'));
    res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' }).end(body);
  }
}).listen(Number(port), () => console.log(`Pages preview: http://localhost:${port}${prefix}`));
