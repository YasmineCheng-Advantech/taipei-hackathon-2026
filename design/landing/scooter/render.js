// 把 scooter.html 算繪成透明背景的 PNG。
// 用法：npm i three@0.169.0 playwright && node render.js "scooter.html?w=1600&h=1400" scooter.png 1600 1400
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const root = __dirname;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  fs.readFile(p, (err, data) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(0, async () => {
  const port = server.address().port;
  const [,, scene, out, w = '800', h = '700'] = process.argv;
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1 });
  page.on('console', m => console.log('[page]', m.text()));
  page.on('pageerror', e => console.log('[pageerror]', e.message));
  await page.goto(`http://localhost:${port}/${scene}`);
  await page.waitForFunction(() => window.__done === true, null, { timeout: 120000 });
  await page.locator('canvas').screenshot({ path: out, omitBackground: true });
  await browser.close(); server.close();
});
