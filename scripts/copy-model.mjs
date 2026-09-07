import { cpSync, mkdirSync, readdirSync } from 'node:fs';
mkdirSync('public/model', { recursive: true });
cpSync('node_modules/@spotify/basic-pitch/model', 'public/model', {
  recursive: true,
});
mkdirSync('public/wasm', { recursive: true });
for (const f of readdirSync('node_modules/@tensorflow/tfjs-backend-wasm/dist'))
  if (f.endsWith('.wasm'))
    cpSync(
      `node_modules/@tensorflow/tfjs-backend-wasm/dist/${f}`,
      `public/wasm/${f}`,
    );
