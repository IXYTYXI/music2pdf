import { test } from 'node:test';
import assert from 'node:assert/strict';
import { synthesize } from '../lib/music/audio';

void test('playback cleanup is safe after natural completion and repeated cancellation', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext');
  let closes = 0;
  class Context {
    currentTime = 0;
    destination = {};
    state = 'running';
    createGain() {
      return {
        gain: {
          value: 0,
          setValueAtTime() {},
          linearRampToValueAtTime() {},
          exponentialRampToValueAtTime() {},
        },
        connect() {},
      };
    }
    createOscillator() {
      return {
        frequency: { value: 0 },
        type: '',
        connect() {},
        start() {},
        stop() {},
      };
    }
    resume() {
      return Promise.resolve();
    }
    close() {
      closes++;
      this.state = 'closed';
      return Promise.resolve();
    }
  }
  Object.defineProperty(globalThis, 'AudioContext', {
    configurable: true,
    value: Context,
  });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'AudioContext', previous);
    else Reflect.deleteProperty(globalThis, 'AudioContext');
  });
  let ended = 0;
  const notes = [
    {
      id: 'n',
      pitch: 60,
      start: 0,
      duration: 0.1,
      velocity: 0.7,
      track: 'piano',
    },
  ];
  const stop = synthesize(notes, 120, 120, () => ended++);
  t.mock.timers.tick(1000);
  stop();
  stop();
  assert.equal(ended, 1);
  assert.equal(closes, 1);
  const cancel = synthesize(notes, 120, 120, () => ended++);
  cancel();
  cancel();
  t.mock.timers.tick(1000);
  assert.equal(ended, 1);
  assert.equal(closes, 2);
});
