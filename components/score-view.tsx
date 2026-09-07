'use client';
import { useEffect, useRef, useState } from 'react';
import {
  extractMelody,
  KEYS,
  numberedPitch,
  quantizeNotes,
  splitDuration,
  type Note,
  type ScoreOptions,
} from '@/lib/music/score';
export function StaffScore({
  xml,
  onReady,
}: {
  xml: string;
  onReady: (ready: boolean) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let observer: ResizeObserver | undefined;
    let timer: ReturnType<typeof setTimeout>;
    queueMicrotask(() => {
      if (active) {
        onReady(false);
        setError('');
      }
    });
    async function render() {
      try {
        const { OpenSheetMusicDisplay } = await import('opensheetmusicdisplay');
        if (!active || !ref.current) return;
        ref.current.replaceChildren();
        const osmd = new OpenSheetMusicDisplay(ref.current, {
          autoResize: false,
          pageFormat: 'A4 P',
          backend: 'svg',
          drawTitle: true,
          drawComposer: false,
          drawPartNames: false,
          drawingParameters: 'compacttight',
        });
        await osmd.load(xml);
        if (!active) return;
        osmd.zoom = 0.85;
        osmd.render();
        onReady(true);
        let width = ref.current.clientWidth;
        observer = new ResizeObserver((entries) => {
          if (Math.abs(entries[0].contentRect.width - width) < 2) return;
          width = entries[0].contentRect.width;
          clearTimeout(timer);
          timer = setTimeout(() => {
            if (active) osmd.render();
          }, 150);
        });
        observer.observe(ref.current);
      } catch (e) {
        if (active) {
          setError('乐谱排版失败，可以先下载 MusicXML 在其他打谱软件中打开。');
          console.error(e);
        }
      }
    }
    void render();
    return () => {
      active = false;
      observer?.disconnect();
      clearTimeout(timer);
    };
  }, [xml, onReady]);
  return (
    <div className="staff-score">
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div ref={ref} />
    </div>
  );
}
export function NumberedScore({
  notes,
  options,
}: {
  notes: Note[];
  options: ScoreOptions;
}) {
  const q = quantizeNotes(extractMelody(notes), options.bpm),
    bar = options.beats * 4,
    total = Math.max(
      1,
      Math.ceil(Math.max(0, ...q.map((n) => n.tick + n.ticks)) / bar),
    );
  const cells: {
    pitch: number | null;
    ticks: number;
    type: string;
    dot: boolean;
    tied: boolean;
  }[][] = [];
  for (let m = 0; m < total; m++) {
    const row: (typeof cells)[number] = [];
    let cursor = m * bar;
    const add = (pitch: number | null, ticks: number, tied = false) =>
      splitDuration(ticks).forEach((d, i) =>
        row.push({ pitch, ...d, tied: pitch !== null && (tied || i > 0) }),
      );
    for (let i = 0; i < q.length; i++) {
      const n = q[i],
        noteEnd = Math.min(n.tick + n.ticks, q[i + 1]?.tick ?? Infinity);
      const a = Math.max(m * bar, n.tick),
        b = Math.min((m + 1) * bar, noteEnd);
      if (a >= b) continue;
      if (a > cursor) add(null, a - cursor);
      add(n.pitch, b - a, a > n.tick);
      cursor = b;
    }
    if (cursor < (m + 1) * bar) add(null, (m + 1) * bar - cursor);
    cells.push(row);
  }
  return (
    <div className="numbered-score">
      <h2>{options.title}</h2>
      <div className="score-meta">
        <span>
          1 = {KEYS[options.key]}　{options.beats}/4
        </span>
        <span>♩ = {options.bpm} · 主旋律候选</span>
      </div>
      <div className="numbered-bars">
        {cells.map((row, m) => (
          <div className="numbered-bar" key={m}>
            <span className="bar-number">{m + 1}</span>
            {row.map((c, i) => {
              const p =
                c.pitch !== null ? numberedPitch(c.pitch, options.key) : null;
              return (
                <span
                  className="number-cell"
                  key={i}
                  style={{ flex: Math.max(2, c.ticks) }}
                >
                  {c.tied && <span className="tie-mark">⌒</span>}
                  <span className="above-dots">
                    {p && p.octave > 0 ? '·'.repeat(p.octave) : ''}
                  </span>
                  <span
                    className={`number-glyph ${c.ticks < 4 ? 'short-note' : ''} ${c.ticks === 1 ? 'sixteenth' : ''}`}
                  >
                    <sup>{p?.accidental}</sup>
                    {p?.digit ?? '0'}
                    {c.dot && c.ticks < 8 ? '·' : ''}
                  </span>
                  {c.ticks >= 8 && (
                    <span className="dashes">
                      {' −'.repeat(Math.floor(c.ticks / 4) - 1)}
                    </span>
                  )}
                  <span className="below-dots">
                    {p && p.octave < 0 ? '·'.repeat(-p.octave) : ''}
                  </span>
                </span>
              );
            })}
          </div>
        ))}
      </div>
      <p className="score-footnote">
        旋律由音高连续性和时值推断，请对照原音校正。⌒ 表示与前一音延连。
      </p>
    </div>
  );
}
