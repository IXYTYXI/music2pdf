import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decodeFile } from '../lib/music/audio';

void test('selected audio is offset correctly and cancelled decodes do not resample', async () => {
  const previousAudio = globalThis.AudioContext;
  const previousOffline = globalThis.OfflineAudioContext;
  let finishDecode: ((v: unknown) => void) | undefined;
  let renders = 0;
  let started: number[] = [];
  class Audio {
    async decodeAudioData() {
      return new Promise((resolve) => {
        finishDecode = resolve;
      });
    }
    async close() {}
  }
  class Offline {
    destination = {};
    constructor(
      public channels: number,
      public length: number,
      public rate: number,
    ) {}
    createBufferSource() {
      return {
        buffer: null,
        connect() {},
        start(...values: number[]) {
          started = values;
        },
      };
    }
    async startRendering() {
      renders++;
      return { getChannelData: () => new Float32Array(this.length) };
    }
  }
  globalThis.AudioContext = Audio as unknown as typeof AudioContext;
  globalThis.OfflineAudioContext =
    Offline as unknown as typeof OfflineAudioContext;
  try {
    const file = new File(['test'], 'song.mp3');
    const controller = new AbortController();
    const first = decodeFile(file, 180, 240, controller.signal);
    const rejected = assert.rejects(first, { name: 'AbortError' });
    await new Promise((r) => setTimeout(r, 0));
    controller.abort();
    finishDecode!({ duration: 999 });
    await rejected;
    assert.equal(renders, 0);
    const second = decodeFile(file, 180, 240);
    await new Promise((r) => setTimeout(r, 0));
    finishDecode!({ duration: 999 });
    const result = await second;
    assert.equal(result.duration, 60);
    assert.equal(result.samples.length, 60 * 22050);
    assert.deepEqual(started, [0, 180, 60]);
  } finally {
    globalThis.AudioContext = previousAudio;
    globalThis.OfflineAudioContext = previousOffline;
  }
});
