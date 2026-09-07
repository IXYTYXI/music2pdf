import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateAudio, type Note } from '../lib/music/score';
import {
  audioChunks,
  validateRange,
  initialRange,
  recommendedParallelism,
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
void test('accepts the supplied orchestral duration and rejects more than one hour', () => {
  assert.doesNotThrow(() =>
    validateAudio('song.mp3', 40 * 1024 * 1024, 999.027),
  );
  assert.throws(() => validateAudio('song.mp3', 100, 3601));
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
void test('parallel workers finish out of order but merge in timeline order with monotonic progress', async () => {
  const pending: WorkerPort[] = [];
  let active = 0,
    maxActive = 0,
    terminated = 0;
  const progress: number[] = [];
  const factory = (): WorkerPort => {
    active++;
    maxActive = Math.max(maxActive, active);
    const w: WorkerPort = {
      onmessage: null,
      onerror: null,
      terminate() {
        active--;
        terminated++;
      },
      postMessage() {
        pending.push(w);
      },
    };
    return w;
  };
  const job = transcribeAudio(
    new Float32Array(61 * 22050),
    'https://example.com',
    (p) => progress.push(p),
    new AbortController().signal,
    factory,
    2,
  );
  assert.equal(pending.length, 2);
  pending[1].onmessage?.({ data: { type: 'progress', progress: 80 } });
  pending[0].onmessage?.({ data: { type: 'progress', progress: 10 } });
  pending[1].onmessage?.({ data: { type: 'complete', notes: [note(1, 6)] } });
  await new Promise<void>((resolve) => queueMicrotask(resolve));
  assert.equal(pending.length, 3);
  pending[2].onmessage?.({
    data: { type: 'complete', notes: [note(2, 0.5, 67)] },
  });
  pending[0].onmessage?.({ data: { type: 'complete', notes: [note(29, 3)] } });
  const result = await job;
  assert.deepEqual(
    result.map((n) => [n.pitch, n.start, n.duration]),
    [
      [60, 29, 6],
      [67, 60, 0.5],
    ],
  );
  assert.equal(maxActive, 2);
  assert.equal(terminated, 3);
  assert.ok(progress.every((p, i) => i === 0 || p >= progress[i - 1]));
  assert.equal(progress.at(-1), 100);
});
void test('parallel cancellation terminates all active workers without launching queued chunks', async () => {
  const c = new AbortController();
  let created = 0,
    terminated = 0;
  const factory = (): WorkerPort => {
    created++;
    return {
      onmessage: null,
      onerror: null,
      postMessage() {},
      terminate() {
        terminated++;
      },
    };
  };
  const job = transcribeAudio(
    new Float32Array(131 * 22050),
    'https://example.com',
    () => {},
    c.signal,
    factory,
    2,
  );
  c.abort();
  await assert.rejects(job, { name: 'AbortError' });
  assert.equal(created, 2);
  assert.equal(terminated, 2);
});
void test('one worker failure aborts its peers and rejects the entire result', async () => {
  const pending: WorkerPort[] = [];
  let terminated = 0;
  const factory = (): WorkerPort => {
    const w: WorkerPort = {
      onmessage: null,
      onerror: null,
      postMessage() {
        pending.push(w);
      },
      terminate() {
        terminated++;
      },
    };
    return w;
  };
  const job = transcribeAudio(
    new Float32Array(131 * 22050),
    'https://example.com',
    () => {},
    new AbortController().signal,
    factory,
    2,
  );
  pending[1].onmessage?.({
    data: { type: 'error', message: 'model unavailable' },
  });
  await assert.rejects(job, /model unavailable/);
  assert.equal(pending.length, 2);
  assert.equal(terminated, 2);
});

void test('automatic parallelism stays conservative on low-core or low-memory devices', () => {
  assert.equal(recommendedParallelism(2, 8), 1);
  assert.equal(recommendedParallelism(8, 2), 1);
  assert.equal(recommendedParallelism(8, 8), 2);
  assert.equal(recommendedParallelism(4, undefined), 2);
});
void test('concurrency is capped at four and at the number of chunks', async () => {
  let active = 0,
    maxActive = 0;
  const factory = (): WorkerPort => {
    active++;
    maxActive = Math.max(maxActive, active);
    const w: WorkerPort = {
      onmessage: null,
      onerror: null,
      terminate() {
        active--;
      },
      postMessage() {
        queueMicrotask(() =>
          w.onmessage?.({ data: { type: 'complete', notes: [] } }),
        );
      },
    };
    return w;
  };
  await transcribeAudio(
    new Float32Array(151 * 22050),
    'https://example.com',
    () => {},
    new AbortController().signal,
    factory,
    99,
  );
  assert.equal(maxActive, 4);
  assert.equal(active, 0);
  maxActive = 0;
  await transcribeAudio(
    new Float32Array(5 * 22050),
    'https://example.com',
    () => {},
    new AbortController().signal,
    factory,
    4,
  );
  assert.equal(maxActive, 1);
});

void test('long recordings start with a visible one-minute trial range', () => {
  assert.deepEqual(initialRange(999), { start: 0, end: 60 });
  assert.deepEqual(initialRange(120), { start: 0, end: 120 });
});
void test('range validation rejects invalid boundaries and allows the full recording', () => {
  assert.doesNotThrow(() => validateRange(0, 999.027, 999.027));
  for (const [start, end] of [
    [-1, 60],
    [60, 60],
    [90, 60],
    [0, 1000],
    [NaN, 60],
  ])
    assert.throws(() => validateRange(start, end, 999.027));
});
