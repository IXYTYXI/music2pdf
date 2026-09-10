import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as score from '../lib/music/score';
void test('raw playback preserves event times while score playback quantizes a copy', () => {
  const notes = [
    {
      id: 'one',
      pitch: 64,
      start: 0.337,
      duration: 0.083,
      velocity: 0.7,
      track: 'piano',
    },
  ];
  const snapshot = structuredClone(notes);
  assert.equal(typeof score.playbackNotes, 'function');
  assert.deepEqual(score.playbackNotes(notes, 75, 'raw'), snapshot);
  const quantized = score.playbackNotes(notes, 120, 'score');
  assert.equal(quantized[0].start, 0.375);
  assert.equal(quantized[0].duration, 0.125);
  assert.deepEqual(notes, snapshot);
});
