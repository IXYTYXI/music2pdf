import midiLibrary from '@tonejs/midi/build/Midi.js';
const { Midi } = midiLibrary;
import { quantizeNotes, type Note, type ScoreOptions } from './score';
export function toMidi(notes: Note[], options: ScoreOptions): Uint8Array {
  const midi = new Midi();
  midi.header.name = options.title;
  midi.header.setTempo(options.bpm);
  midi.header.timeSignatures.push({
    ticks: 0,
    timeSignature: [options.beats, 4],
    measures: 0,
  });
  for (const trackName of new Set(notes.map((n) => n.track))) {
    const track = midi.addTrack();
    track.name = trackName;
    track.instrument.number = 0;
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
