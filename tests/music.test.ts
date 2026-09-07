import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  quantizeNotes,
  toMusicXML,
  extractMelody,
  numberedPitch,
  splitDuration,
  validateAudio,
  type Note,
} from '../lib/music/score.ts';
const n = (pitch: number, start: number, duration: number): Note => ({
  id: `${pitch}-${start}`,
  pitch,
  start,
  duration,
  velocity: 0.7,
  track: 'piano',
});
void test('quantization preserves simultaneous chord and clamps short notes to a sixteenth', () => {
  const q = quantizeNotes(
    [n(60, 0.01, 0.5), n(64, 0.02, 0.5), n(67, 0.02, 0.03)],
    120,
  );
  assert.deepEqual(
    q.map((x) => [x.tick, x.ticks]),
    [
      [0, 4],
      [0, 4],
      [0, 1],
    ],
  );
});
void test('cross-bar notes use ties and escape user-supplied titles', () => {
  const xml = toMusicXML([n(60, 1.5, 1)], {
    title: 'A & <B>',
    bpm: 120,
    beats: 4,
    key: 0,
  });
  assert.match(xml, /A &amp; &lt;B&gt;/);
  assert.match(xml, /<tie type="start"/);
  assert.match(xml, /<tie type="stop"/);
  assert.match(xml, /<measure number="2"/);
});
void test('independent overlapping notes retain different durations in separate voices', () => {
  const xml = toMusicXML([n(60, 0, 2), n(64, 0.5, 0.5)], {
    title: 'Test',
    bpm: 120,
    beats: 4,
    key: 0,
  });
  assert.match(xml, /<backup>/);
  assert.match(xml, /<voice>2<\/voice>/);
  assert.match(xml, /<staves>2<\/staves>/);
});
void test('notation durations sum exactly including irregular lengths', () => {
  for (let d = 1; d < 40; d++)
    assert.equal(
      splitDuration(d).reduce((s, x) => s + x.ticks, 0),
      d,
    );
});
void test('melody selection follows a continuous line rather than an isolated highest note', () => {
  const notes = [
    n(72, 0, 0.5),
    n(74, 0.5, 0.5),
    n(96, 0.5, 0.05),
    n(76, 1, 0.5),
  ];
  assert.deepEqual(
    extractMelody(notes).map((x) => x.pitch),
    [72, 74, 76],
  );
});
void test('numbered notation represents key, accidentals and octaves', () => {
  assert.deepEqual(numberedPitch(60, 0), {
    digit: '1',
    accidental: '',
    octave: 0,
  });
  assert.deepEqual(numberedPitch(73, 0), {
    digit: '1',
    accidental: '♯',
    octave: 1,
  });
  assert.deepEqual(numberedPitch(62, 2), {
    digit: '1',
    accidental: '',
    octave: 0,
  });
});
void test('audio guard rejects empty, oversized, long, and unsupported files', () => {
  assert.throws(() => validateAudio('x.wav', 0));
  assert.throws(() => validateAudio('x.wav', 201 * 1024 * 1024));
  assert.throws(() => validateAudio('x.exe', 100));
  assert.throws(() => validateAudio('x.wav', 100, 3601));
  assert.doesNotThrow(() => validateAudio('x.MP3', 100, 20));
});
