import * as tf from '@tensorflow/tfjs';
import { setWasmPaths } from '@tensorflow/tfjs-backend-wasm';
import {
  BasicPitch,
  noteFramesToTime,
  outputToNotesPoly,
} from '@spotify/basic-pitch';
import type { Note } from './score';
self.onmessage = async (
  event: MessageEvent<{ audio: Float32Array; origin: string }>,
) => {
  try {
    self.postMessage({
      type: 'progress',
      progress: 3,
      label: '正在加载识别模型…',
    });
    setWasmPaths(`${event.data.origin}/wasm/`);
    // Threaded WASM requires cross-origin isolation; the single-thread build also works on shared hosts.
    tf.env().set('WASM_HAS_MULTITHREAD_SUPPORT', false);
    try {
      if (!(await tf.setBackend('wasm'))) await tf.setBackend('cpu');
    } catch {
      await tf.setBackend('cpu');
    }
    await tf.ready();
    const model = new BasicPitch(`${event.data.origin}/model/model.json`);
    await model.model;
    const frames: number[][] = [],
      onsets: number[][] = [];
    await model.evaluateModel(
      event.data.audio,
      (f, o) => {
        frames.push(...f);
        onsets.push(...o);
      },
      (p) =>
        self.postMessage({
          type: 'progress',
          progress: Math.round(8 + p * 87),
          label: '正在识别音高与起止时间…',
        }),
    );
    const notes: Note[] = noteFramesToTime(
      outputToNotesPoly(frames, onsets, 0.3, 0.3, 8),
    )
      .map((n, i) => ({
        id: `note-${i}`,
        pitch: n.pitchMidi,
        start: Math.max(0, n.startTimeSeconds),
        duration: n.durationSeconds,
        velocity: n.amplitude,
        track: 'piano',
      }))
      .filter(
        (n) => n.duration >= 0.08 && n.start < event.data.audio.length / 22050,
      )
      .map((n) => ({
        ...n,
        duration: Math.min(
          n.duration,
          event.data.audio.length / 22050 - n.start,
        ),
      }));
    self.postMessage({ type: 'complete', notes });
  } catch (error) {
    self.postMessage({
      type: 'error',
      message: error instanceof Error ? error.message : '识别失败',
    });
  }
};
