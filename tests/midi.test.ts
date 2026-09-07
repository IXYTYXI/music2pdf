import { test } from 'node:test';
import assert from 'node:assert/strict';
import midiLibrary from '@tonejs/midi/build/Midi.js';
const { Midi } = midiLibrary;
import { toMidi } from '../lib/music/export';
void test('exported MIDI round-trips simultaneous notes, tempo, and time signature', () => {
  const notes = [60, 64, 67].map((pitch, i) => ({
    id: String(i),
    pitch,
    start: 0.5,
    duration: 1,
    velocity: 0.7,
    track: 'piano',
  }));
  const midi = new Midi(
    toMidi(notes, { title: 'Chord', bpm: 120, beats: 3, key: 0 }),
  );
  assert.equal(midi.header.tempos[0].bpm, 120);
  assert.deepEqual(midi.header.timeSignatures[0].timeSignature, [3, 4]);
  assert.equal(midi.tracks[0].notes.length, 3);
  assert.deepEqual(
    midi.tracks[0].notes.map((n) => n.midi),
    [60, 64, 67],
  );
  assert.equal(midi.tracks[0].notes[0].time, 0.5);
  assert.equal(midi.tracks[0].notes[0].duration, 1);
});
