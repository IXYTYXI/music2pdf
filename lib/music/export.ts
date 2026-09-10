import midiLibrary from '@tonejs/midi/build/Midi.js';
const { Midi } = midiLibrary;
import {
  quantizeNotes,
  type Note,
  type ScoreOptions,
  type TimingMode,
} from './score';
export function toMidi(
  notes: Note[],
  options: ScoreOptions,
  mode: TimingMode = 'score',
): Uint8Array {
  const midi = new Midi();
  midi.header.name = options.title;
  // Raw export uses a fixed serialization clock, not the estimated score tempo.
  midi.header.setTempo(mode === 'raw' ? 120 : options.bpm);
  if (mode === 'score')
    midi.header.timeSignatures.push({
      ticks: 0,
      timeSignature: [options.beats, 4],
      measures: 0,
    });
  for (const trackName of new Set(notes.map((n) => n.track))) {
    const track = midi.addTrack();
    track.name = trackName;
    track.instrument.number = 0;
    if (mode === 'raw') {
      for (const n of notes.filter((n) => n.track === trackName))
        track.addNote({
          midi: n.pitch,
          time: n.start,
          duration: n.duration,
          velocity: Math.max(0.01, Math.min(1, n.velocity)),
        });
      continue;
    }
    for (const n of quantizeNotes(
      notes.filter((n) => n.track === trackName),
      options.bpm,
    ))
      track.addNote({
        midi: n.pitch,
        ticks: (n.tick * midi.header.ppq) / 4,
        durationTicks: (n.ticks * midi.header.ppq) / 4,
        velocity: Math.max(0.01, Math.min(1, n.velocity)),
      });
  }
  return midi.toArray();
}
export function download(content: BlobPart, type: string, name: string) {
  const url = URL.createObjectURL(new Blob([content], { type })),
    a = document.createElement('a');
  a.href = url;
  a.download = name.replace(/[\\/:*?"<>|]/g, '_');
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
