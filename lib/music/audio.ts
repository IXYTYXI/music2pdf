import type { Note } from './score';
import { validateAudio } from './score';
import { validateRange } from './long-audio';
export function inspectFile(file: File): Promise<number> {
  validateAudio(file.name, file.size);
  return new Promise((resolve, reject) => {
    const audio = document.createElement('audio');
    const url = URL.createObjectURL(file);
    const cleanup = () => {
      clearTimeout(timer);
      audio.onloadedmetadata = null;
      audio.onerror = null;
      audio.removeAttribute('src');
      audio.load();
      URL.revokeObjectURL(url);
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error('读取音频时长超时，请转换为 MP3 或 WAV 后重试。'));
    }, 30000);
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => {
      const duration = audio.duration;
      cleanup();
      try {
        validateAudio(file.name, file.size, duration);
        resolve(duration);
      } catch (error) {
        reject(error);
      }
    };
    audio.onerror = () => {
      cleanup();
      reject(new Error('浏览器无法读取这个音频，请转换为 MP3 或 WAV 后重试。'));
    };
    audio.src = url;
  });
}
let decodeQueue: Promise<void> = Promise.resolve();
export function decodeFile(
  file: File,
  start = 0,
  end?: number,
  signal?: AbortSignal,
) {
  // Browser decoders cannot be interrupted; serialize retries to avoid overlapping full-file buffers.
  const result = decodeQueue.then(() =>
    decodeSelectedFile(file, start, end, signal),
  );
  decodeQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}
async function decodeSelectedFile(
  file: File,
  start: number,
  end?: number,
  signal?: AbortSignal,
) {
  signal?.throwIfAborted();
  validateAudio(file.name, file.size);
  const ctx = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await ctx.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw new Error('浏览器无法解码这个音频。请转换为 WAV 或 MP3 后重试。');
  } finally {
    await ctx.close();
  }
  signal?.throwIfAborted();
  validateAudio(file.name, file.size, decoded.duration);
  const stop = Math.min(end ?? decoded.duration, decoded.duration);
  validateRange(start, stop, decoded.duration);
  const selectedDuration = stop - start;
  const offline = new OfflineAudioContext(
    1,
    Math.ceil(selectedDuration * 22050),
    22050,
  );
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start(0, start, selectedDuration);
  const mono = await offline.startRendering();
  signal?.throwIfAborted();
  const samples = mono.getChannelData(0),
    wave: number[] = [];
  const stride = Math.max(1, Math.floor(samples.length / 100));
  for (let i = 0; i < 100; i++) {
    let peak = 0;
    for (
      let j = i * stride;
      j < Math.min(samples.length, (i + 1) * stride);
      j++
    )
      peak = Math.max(peak, Math.abs(samples[j]));
    wave.push(peak);
  }
  return { samples, duration: selectedDuration, wave };
}
export function synthesize(
  notes: Note[],
  bpm: number,
  sourceBpm: number,
  onEnd: () => void,
) {
  const ctx = new AudioContext(),
    master = ctx.createGain();
  master.gain.value = 0.22;
  master.connect(ctx.destination);
  const ratio = sourceBpm / bpm,
    base = ctx.currentTime + 0.06;
  for (const n of notes) {
    const osc = ctx.createOscillator(),
      gain = ctx.createGain(),
      start = base + n.start * ratio,
      end = start + Math.max(0.06, n.duration * ratio);
    osc.type = 'triangle';
    osc.frequency.value = 440 * 2 ** ((n.pitch - 69) / 12);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(
      Math.max(0.04, n.velocity) * 0.35,
      start + 0.01,
    );
    gain.gain.exponentialRampToValueAtTime(0.015, end);
    gain.gain.linearRampToValueAtTime(0, end + 0.08);
    osc.connect(gain);
    gain.connect(master);
    osc.start(start);
    osc.stop(end + 0.1);
  }
  void ctx.resume();
  const timer = setTimeout(
    () => {
      void ctx.close();
      onEnd();
    },
    (Math.max(0, ...notes.map((n) => n.start + n.duration)) * ratio + 0.3) *
      1000,
  );
  return () => {
    clearTimeout(timer);
    void ctx.close();
  };
}
export function makeDemo(): { notes: Note[]; blob: Blob } {
  // Original eight-bar exercise; synthesized locally, not a transcription result.
  const melody = [
    72, 74, 76, 79, 77, 76, 74, 72, 69, 72, 76, 74, 71, 67, 69, 71, 72, 76, 79,
    81, 79, 76, 74, 72, 77, 76, 74, 72, 71, 74, 72, 72,
  ];
  const notes: Note[] = melody.map((pitch, i) => ({
    id: `demo-${i}`,
    pitch,
    start: i * 0.5,
    duration: i === 31 ? 0.9 : 0.43,
    velocity: 0.7,
    track: 'piano',
  }));
  [48, 53, 45, 43, 48, 45, 53, 43].forEach((pitch, i) => {
    for (const offset of [0, 7])
      notes.push({
        id: `bass-${i}-${offset}`,
        pitch: pitch + offset,
        start: i * 2,
        duration: 1.75,
        velocity: 0.45,
        track: 'piano',
      });
  });
  const rate = 22050,
    length = rate * 17,
    samples = new Float32Array(length);
  for (const n of notes) {
    const f = 440 * 2 ** ((n.pitch - 69) / 12);
    for (
      let j = 0;
      j < Math.min((n.duration + 0.2) * rate, length - n.start * rate);
      j++
    ) {
      const t = j / rate,
        envelope =
          Math.min(1, t / 0.008) *
          Math.exp(-t * 3) *
          Math.max(0, Math.min(1, (n.duration + 0.2 - t) / 0.2));
      samples[Math.floor(n.start * rate) + j] +=
        (Math.sin(2 * Math.PI * f * t) +
          0.25 * Math.sin(4 * Math.PI * f * t) +
          0.1 * Math.sin(6 * Math.PI * f * t)) *
        envelope *
        0.17 *
        n.velocity;
    }
  }
  const buffer = new ArrayBuffer(44 + length * 2),
    v = new DataView(buffer);
  const str = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(offset + i, s.charCodeAt(i));
  };
  str(0, 'RIFF');
  v.setUint32(4, 36 + length * 2, true);
  str(8, 'WAVE');
  str(12, 'fmt ');
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, 'data');
  v.setUint32(40, length * 2, true);
  samples.forEach((x, i) =>
    v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, x)) * 32767, true),
  );
  return { notes, blob: new Blob([buffer], { type: 'audio/wav' }) };
}
