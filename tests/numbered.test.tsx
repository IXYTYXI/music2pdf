import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { NumberedScore } from '../components/score-view';
void test('tied high notes keep octave dots in both bars', () => {
  const html = renderToStaticMarkup(
    <NumberedScore
      notes={[
        {
          id: 'high',
          pitch: 72,
          start: 1.5,
          duration: 1,
          velocity: 0.7,
          track: 'piano',
        },
      ]}
      options={{ title: 'Test', bpm: 120, beats: 4, key: 0 }}
    />,
  );
  assert.equal((html.match(/class="above-dots">·/g) || []).length, 2);
  assert.equal((html.match(/class="tie-mark"/g) || []).length, 1);
});
void test('rest fragments never have ties', () => {
  const html = renderToStaticMarkup(
    <NumberedScore
      notes={[
        {
          id: 'one',
          pitch: 60,
          start: 0.625,
          duration: 0.125,
          velocity: 0.7,
          track: 'piano',
        },
      ]}
      options={{ title: 'Test', bpm: 120, beats: 4, key: 0 }}
    />,
  );
  assert.doesNotMatch(html, /class="tie-mark"/);
});
