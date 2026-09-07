import * as tf from '@tensorflow/tfjs';
import {
  BasicPitch,
  noteFramesToTime,
  outputToNotesPoly,
} from '@spotify/basic-pitch';
import { readFileSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const metadata = JSON.parse(readFileSync('public/model/model.json', 'utf8'));
const bytes = readFileSync('public/model/group1-shard1of1.bin');
await tf.setBackend('cpu');
await tf.ready();
const graph = await tf.loadGraphModel(
  tf.io.fromMemory({
    modelTopology: metadata.modelTopology,
    weightSpecs: metadata.weightsManifest.flatMap((g) => g.weights),
    weightData: bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ),
  }),
);
const model = new BasicPitch(Promise.resolve(graph));
const rate = 22050,
  samples = new Float32Array(rate * 3);
for (const pitch of [60, 64, 67])
  for (let i = 0; i < rate * 2; i++) {
    const t = i / rate,
      f = 440 * 2 ** ((pitch - 69) / 12);
    samples[i] +=
      Math.sin(2 * Math.PI * f * t) *
      0.15 *
      Math.min(1, t / 0.01) *
      Math.exp(-t * 1.4);
  }
const frames = [],
  onsets = [];
await model.evaluateModel(
  samples,
  (f, o) => {
    frames.push(...f);
    onsets.push(...o);
  },
  () => {},
);
const notes = noteFramesToTime(outputToNotesPoly(frames, onsets, 0.3, 0.3, 8));
const pitches = [...new Set(notes.map((n) => n.pitchMidi))];
console.log('Recognized C-major chord:', pitches);
assert.ok(
  [60, 64, 67].every((p) => pitches.includes(p)),
  'Expected C4, E4 and G4 simultaneously',
);
assert.ok(
  notes.every(
    (n) => Number.isFinite(n.startTimeSeconds) && n.durationSeconds > 0,
  ),
);
writeFileSync('/tmp/music2pdf-inference-result.json', JSON.stringify(notes));
graph.dispose();
console.log(
  'Real model inference passed. Synthetic chord only; not an accuracy benchmark.',
);
