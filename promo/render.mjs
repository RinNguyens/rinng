// Render rinng-promo.html to MP4, frame by frame.
// Usage: node render.mjs [--stills 1.5,5,12] [--out rinng-promo.mp4]
// Needs: playwright-core (resolved from NODE_PATH or cwd), Google Chrome, ffmpeg.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(process.cwd(), 'x.js'));
const { chromium } = require('playwright-core');

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const stills = arg('--stills');
const out = resolve(arg('--out', join(here, 'rinng-promo.mp4')));

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
page.on('pageerror', e => console.error('page error:', e.message));
await page.goto(pathToFileURL(join(here, 'rinng-promo.html')).href + '?capture');
await page.waitForFunction('window.__ready === true');
const { duration, fps } = await page.evaluate(() => ({ duration: window.__duration, fps: window.__fps }));

if (stills) {
  const dir = resolve(arg('--dir', join(here, 'stills')));
  mkdirSync(dir, { recursive: true });
  for (const t of stills.split(',').map(Number)) {
    await page.evaluate(s => window.__seek(s), t);
    writeFileSync(join(dir, `t${t.toFixed(1).padStart(4, '0')}.jpg`), await page.screenshot({ type: 'jpeg', quality: 80 }));
  }
  console.log('stills ->', dir);
} else {
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = Math.round(duration * fps);
  for (let f = 0; f < total; f++) {
    await page.evaluate(s => window.__seek(s), f / fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 96 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 150 === 0) console.log(`frame ${f}/${total}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  console.log('video ->', out);
}
await browser.close();
