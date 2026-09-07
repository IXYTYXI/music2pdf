import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateAudio, type Note } from '../lib/music/score';
import {
  audioChunks,
  mergeChunkNotes,
  transcribeAudio,
  type WorkerPort,
} from '../lib/music/long-audio';
const note = (start: number, duration = 1, pitch = 60): Note => ({
  id: 'x',
  pitch,
  start,
  duration,
  velocity: 0.7,
  track: 'piano',
});
void test('accepts a five-minute recording but rejects more than ten minutes', () => {
  assert.doesNotThrow(() => validateAudio('song.mp3', 60 * 1024 * 1024, 300));
  assert.throws(() => validateAudio('song.mp3', 100, 601));
});
void test('chunks cover full duration, include boundary context and never exceed 34 seconds', () => {
  const chunks = audioChunks(131);
  assert.equal(chunks.length, 5);
  assert.equal(chunks[0].start, 0);
  assert.equal(chunks.at(-1)!.end, 131);
  assert.ok(chunks.every((c) => c.inputEnd - c.inputStart <= 34));
  for (let i = 1; i < chunks.length; i++)
    assert.equal(chunks[i].start, chunks[i - 1].end);
});
void test('overlap avoids duplicate notes and keeps late notes at absolute times', () => {
  const chunks = audioChunks(65);
  let result = mergeChunkNotes([], [note(29, 2)], chunks[0]);
  result = mergeChunkNotes(result, [note(1, 2), note(3, 1)], chunks[1]);
  assert.deepEqual(
    result.map((n) => [n.start, n.duration]),
    [
      [29, 2],
      [31, 1],
    ],
  );
  assert.equal(new Set(result.map((n) => n.id)).size, 2);
});
void test('extends a sustained note clipped by the preceding window', () => {
  const chunks = audioChunks(65);
  let result = mergeChunkNotes([], [note(25, 7)], chunks[0]);
  result = mergeChunkNotes(result, [note(0, 10)], chunks[1]);
  assert.equal(result.length, 1);
  assert.equal(result[0].start + result[0].duration, 38);
});
void test('orchestrator uses bounded sequential workers and includes audio beyond two minutes', async () => {
  let created = 0,
    active = 0,
    maxActive = 0,
    terminated = 0;
  const lengths: number[] = [];
  const factory = (): WorkerPort => {
    created++;
    active++;
    maxActive = Math.max(maxActive, active);
    const w: WorkerPort = {
      onmessage: null,
      onerror: null,
      terminate() {
        active--;
        terminated++;
      },
      postMessage(data) {
        lengths.push(data.audio.length);
        queueMicrotask(() =>
          w.onmessage?.({ data: { type: 'complete', notes: [note(3)] } }),
        );
      },
    };
    return w;
  };
  const notes = await transcribeAudio(
    new Float32Array(131 * 22050),
    'https://example.com',
    () => {},
    new AbortController().signal,
    factory,
  );
  assert.equal(created, 5);
  assert.equal(terminated, 5);
  assert.equal(maxActive, 1);
  assert.ok(Math.max(...lengths) <= 34 * 22050);
  assert.ok(notes.some((n) => n.start > 120));
});
void test('cancel terminates active worker and does not start the next chunk', async () => {
  let created = 0,
    terminated = 0;
  const controller = new AbortController();
  const factory = (): WorkerPort => {
    created++;
    return {
      onmessage: null,
      onerror: null,
      terminate() {
        terminated++;
      },
      postMessage() {
        queueMicrotask(() => controller.abort());
      },
    };
  };
  await assert.rejects(
    transcribeAudio(
      new Float32Array(61 * 22050),
      'https://example.com',
      () => {},
      controller.signal,
      factory,
    ),
    { name: 'AbortError' },
  );
  assert.equal(created, 1);
  assert.equal(terminated, 1);
});
void test('later window extends a known onset within the overlap', () => {
  const chunks = audioChunks(65);
  const first = mergeChunkNotes([], [note(29, 3)], chunks[0]);
  const result = mergeChunkNotes(first, [note(1, 6)], chunks[1]);
  assert.equal(result.length, 1);
  assert.equal(result[0].start + result[0].duration, 35);
});
void test('boundary onset jitter across ownership cutoff does not erase notes', () => {
  const chunks = audioChunks(65);
  const first = mergeChunkNotes([], [note(30.01)], chunks[0]);
  const result = mergeChunkNotes(first, [note(1.99)], chunks[1]);
  assert.equal(result.length, 1);
  assert.ok(Math.abs(result[0].start - 30) < 0.06);
});
