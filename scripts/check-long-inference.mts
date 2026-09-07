import * as tf from '@tensorflow/tfjs';
import {
  BasicPitch,
  noteFramesToTime,
  outputToNotesPoly,
} from '@spotify/basic-pitch';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { audioChunks, mergeChunkNotes } from '../lib/music/long-audio';
import type { Note } from '../lib/music/score';
const metadata = JSON.parse(readFileSync('public/model/model.json', 'utf8'));
const bytes = readFileSync('public/model/group1-shard1of1.bin');
await tf.setBackend('cpu');
await tf.ready();
const graph = await tf.loadGraphModel(
  tf.io.fromMemory({
    modelTopology: metadata.modelTopology,
    weightSpecs: metadata.weightsManifest.flatMap(
      (g: { weights: tf.io.WeightsManifestEntry[] }) => g.weights,
    ),
    weightData: bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ),
  }),
);
const model = new BasicPitch(Promise.resolve(graph));
const rate = 22050,
  samples = new Float32Array(65 * rate);
for (const [start, pitch] of [
  [29.6, 60],
  [31.5, 64],
  [61.2, 67],
])
  for (let i = 0; i < rate; i++) {
    const t = i / rate;
    samples[Math.round(start * rate) + i] +=
      Math.sin(2 * Math.PI * 440 * 2 ** ((pitch - 69) / 12) * t) *
      0.25 *
      Math.min(1, t / 0.01) *
      Math.exp(-t * 1.4);
  }
let result: Note[] = [];
for (const chunk of audioChunks(65)) {
  tf.engine().startScope();
  try {
    const frames: number[][] = [],
      onsets: number[][] = [];
    await model.evaluateModel(
      samples.slice(chunk.inputStart * rate, chunk.inputEnd * rate),
      (f, o) => {
        frames.push(...f);
        onsets.push(...o);
      },
      () => {},
    );
    const notes = noteFramesToTime(
      outputToNotesPoly(frames, onsets, 0.3, 0.3, 8),
    ).map((n, i) => ({
      id: String(i),
      pitch: n.pitchMidi,
      start: n.startTimeSeconds,
      duration: n.durationSeconds,
      velocity: n.amplitude,
      track: 'piano',
    }));
    result = mergeChunkNotes(result, notes, chunk);
  } finally {
    tf.engine().endScope();
  }
}
for (const [start, pitch] of [
  [29.6, 60],
  [31.5, 64],
  [61.2, 67],
])
  assert.equal(
    result.filter((n) => n.pitch === pitch && Math.abs(n.start - start) < 0.15)
      .length,
    1,
    `Expected a single ${pitch} note at ${start}s`,
  );
console.log(
  'Real model: 65s segmented audio retains notes at 29.6s, 31.5s and 61.2s without boundary duplicates.',
);
graph.dispose();
