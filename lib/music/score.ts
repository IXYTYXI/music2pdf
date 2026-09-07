import { MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS } from './long-audio';
export interface Note {
  id: string;
  pitch: number;
  start: number;
  duration: number;
  velocity: number;
  track: string;
}
export interface ScoreOptions {
  title: string;
  bpm: number;
  beats: number;
  key: number;
}
export interface QuantizedNote extends Note {
  tick: number;
  ticks: number;
}
export const KEYS = [
  'C',
  'D♭',
  'D',
  'E♭',
  'E',
  'F',
  'F♯',
  'G',
  'A♭',
  'A',
  'B♭',
  'B',
];
export function validateAudio(name: string, size: number, duration?: number) {
  if (!/\.(wav|mp3|flac|m4a|ogg|aac|aiff|aif)$/i.test(name))
    throw new Error('请选择 WAV、MP3、FLAC、M4A 或 OGG 音频文件。');
  if (size <= 0) throw new Error('这个文件是空的，请重新选择。');
  if (size > MAX_AUDIO_BYTES)
    throw new Error('文件超过 100 MB，请先截取一段音频。');
  if (
    duration !== undefined &&
    (!Number.isFinite(duration) ||
      duration <= 0 ||
      duration > MAX_AUDIO_SECONDS)
  )
    throw new Error('当前支持最长 10 分钟，请截取片段后重试。');
}
export function quantizeNotes(notes: Note[], bpm: number): QuantizedNote[] {
  const rate = Math.min(240, Math.max(30, bpm)) / 15;
  return notes
    .filter(
      (n) =>
        Number.isFinite(n.start) &&
        Number.isFinite(n.duration) &&
        Number.isFinite(n.pitch) &&
        n.duration > 0,
    )
    .map((n) => ({
      ...n,
      pitch: Math.min(108, Math.max(21, Math.round(n.pitch))),
      tick: Math.max(0, Math.round(n.start * rate)),
      ticks: Math.max(
        1,
        Math.round((n.start + n.duration) * rate) -
          Math.max(0, Math.round(n.start * rate)),
      ),
    }))
    .sort((a, b) => a.tick - b.tick || a.pitch - b.pitch);
}
export function splitDuration(
  ticks: number,
): { ticks: number; type: string; dot: boolean }[] {
  const values: [number, string, boolean][] = [
    [16, 'whole', false],
    [12, 'half', true],
    [8, 'half', false],
    [6, 'quarter', true],
    [4, 'quarter', false],
    [3, 'eighth', true],
    [2, 'eighth', false],
    [1, '16th', false],
  ];
  const out: { ticks: number; type: string; dot: boolean }[] = [];
  let remaining = Math.max(0, Math.round(ticks));
  for (const [n, type, dot] of values)
    while (remaining >= n) {
      out.push({ ticks: n, type, dot });
      remaining -= n;
    }
  return out;
}
const escapeXML = (s: string) =>
  s.replace(
    /[<>&"']/g,
    (c) =>
      ({
        '<': '&lt;',
        '>': '&gt;',
        '&': '&amp;',
        '"': '&quot;',
        "'": '&apos;',
      })[c]!,
  );
function pitchXML(p: number, key: number) {
  const flat = [1, 3, 5, 8, 10].includes(key);
  const names = flat
    ? ['C', 'D', 'D', 'E', 'E', 'F', 'G', 'G', 'A', 'A', 'B', 'B']
    : ['C', 'C', 'D', 'D', 'E', 'F', 'F', 'G', 'G', 'A', 'A', 'B'];
  const pc = ((p % 12) + 12) % 12,
    alter = [1, 3, 6, 8, 10].includes(pc) ? (flat ? -1 : 1) : 0;
  return `<pitch><step>${names[pc]}</step>${alter ? `<alter>${alter}</alter>` : ''}<octave>${Math.floor(p / 12) - 1}</octave></pitch>`;
}
export function toMusicXML(notes: Note[], options: ScoreOptions) {
  const q = quantizeNotes(notes, options.bpm),
    bar = options.beats * 4;
  const measures = Math.max(
    1,
    Math.ceil(Math.max(0, ...q.map((n) => n.tick + n.ticks)) / bar),
  );
  // Interval coloring preserves independent note lengths; each staff has at least one voice.
  const lanes: { staff: number; notes: QuantizedNote[] }[] = [];
  for (const staff of [1, 2]) {
    const staffLanes: { staff: number; notes: QuantizedNote[] }[] = [
      { staff, notes: [] },
    ];
    for (const n of q.filter((n) => (n.pitch >= 60 ? 1 : 2) === staff)) {
      let lane = staffLanes.find(
        (l) =>
          !l.notes.length ||
          l.notes.at(-1)!.tick + l.notes.at(-1)!.ticks <= n.tick,
      );
      if (!lane) {
        lane = { staff, notes: [] };
        staffLanes.push(lane);
      }
      lane.notes.push(n);
    }
    lanes.push(...staffLanes);
  }
  const fifths = [0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5][options.key] ?? 0;
  let xml = `<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><work><work-title>${escapeXML(options.title)}</work-title></work><identification><creator type="composer">Music2PDF · 转谱初稿</creator></identification><defaults><scaling><millimeters>7</millimeters><tenths>40</tenths></scaling></defaults><part-list><score-part id="P1"><part-name>Piano</part-name><part-abbreviation>Pno.</part-abbreviation><score-instrument id="I1"><instrument-name>Piano</instrument-name></score-instrument><midi-instrument id="I1"><midi-channel>1</midi-channel><midi-program>1</midi-program></midi-instrument></score-part></part-list><part id="P1">`;
  for (let m = 0; m < measures; m++) {
    const start = m * bar,
      end = start + bar;
    xml += `<measure number="${m + 1}">`;
    if (m === 0)
      xml += `<attributes><divisions>4</divisions><key><fifths>${fifths}</fifths></key><time><beats>${options.beats}</beats><beat-type>4</beat-type></time><staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef><clef number="2"><sign>F</sign><line>4</line></clef></attributes><direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>${options.bpm}</per-minute></metronome></direction-type><sound tempo="${options.bpm}"/></direction>`;
    lanes.forEach((lane, index) => {
      if (index) xml += `<backup><duration>${bar}</duration></backup>`;
      let cursor = start;
      const rest = (ticks: number) =>
        splitDuration(ticks)
          .map(
            (d) =>
              `<note><rest/><duration>${d.ticks}</duration><voice>${index + 1}</voice><type>${d.type}</type>${d.dot ? '<dot/>' : ''}<staff>${lane.staff}</staff></note>`,
          )
          .join('');
      for (const n of lane.notes.filter(
        (n) => n.tick < end && n.tick + n.ticks > start,
      )) {
        const a = Math.max(start, n.tick),
          b = Math.min(end, n.tick + n.ticks);
        xml += rest(a - cursor);
        let at = a;
        for (const d of splitDuration(b - a)) {
          const prev = at > n.tick,
            next = at + d.ticks < n.tick + n.ticks;
          xml += `<note>${pitchXML(n.pitch, options.key)}<duration>${d.ticks}</duration>${prev ? '<tie type="stop"/>' : ''}${next ? '<tie type="start"/>' : ''}<voice>${index + 1}</voice><type>${d.type}</type>${d.dot ? '<dot/>' : ''}<staff>${lane.staff}</staff>${prev || next ? `<notations>${prev ? '<tied type="stop"/>' : ''}${next ? '<tied type="start"/>' : ''}</notations>` : ''}</note>`;
          at += d.ticks;
        }
        cursor = b;
      }
      xml += rest(end - cursor);
    });
    xml += '</measure>';
  }
  return xml + '</part></score-partwise>';
}
export function extractMelody(notes: Note[]): Note[] {
  if (!notes.length) return [];
  const groups: Note[][] = [];
  for (const n of [...notes].sort((a, b) => a.start - b.start)) {
    if (groups.length && Math.abs(n.start - groups.at(-1)![0].start) < 0.06)
      groups.at(-1)!.push(n);
    else groups.push([n]);
  }
  const scores: number[][] = [],
    previous: number[][] = [];
  groups.forEach((g, i) => {
    scores[i] = [];
    previous[i] = [];
    g.forEach((n, j) => {
      const local =
        Math.min(n.duration, 1) * 2 +
        Math.min(1, Math.max(0, (n.pitch - 48) / 24)) +
        n.velocity * 0.3;
      let best = -Infinity,
        from = 0;
      if (i === 0) best = 0;
      else
        groups[i - 1].forEach((p, k) => {
          const value = scores[i - 1][k] - 0.15 * Math.abs(n.pitch - p.pitch);
          if (value > best) {
            best = value;
            from = k;
          }
        });
      scores[i][j] = best + local;
      previous[i][j] = from;
    });
  });
  let k = scores.at(-1)!.indexOf(Math.max(...scores.at(-1)!));
  const result: Note[] = [];
  for (let i = groups.length - 1; i >= 0; i--) {
    result.unshift({ ...groups[i][k] });
    k = previous[i][k];
  }
  return result.map((n, i) => ({
    ...n,
    duration:
      i < result.length - 1
        ? Math.min(n.duration, Math.max(0.01, result[i + 1].start - n.start))
        : n.duration,
  }));
}
export function numberedPitch(pitch: number, key: number) {
  const relative = pitch - (60 + key),
    pc = ((relative % 12) + 12) % 12;
  const scale = [0, 2, 4, 5, 7, 9, 11];
  let i = scale.indexOf(pc),
    accidental = '';
  if (i < 0) {
    i = scale.indexOf(pc - 1);
    accidental = '♯';
  }
  return {
    digit: String(i + 1),
    accidental,
    octave: Math.floor(relative / 12),
  };
}
export function pitchName(p: number) {
  return (
    ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'][p % 12] +
    (Math.floor(p / 12) - 1)
  );
}
export function estimateTempo(notes: Note[]): number {
  const starts = [
    ...new Set(notes.map((n) => Math.round(n.start * 20) / 20)),
  ].sort((a, b) => a - b);
  const gaps = starts
    .slice(1)
    .map((s, i) => s - starts[i])
    .filter((x) => x >= 0.2 && x < 1.5)
    .sort((a, b) => a - b);
  if (!gaps.length) return 100;
  let bpm = 60 / gaps[Math.floor(gaps.length / 2)];
  while (bpm > 160) bpm /= 2;
  while (bpm < 65) bpm *= 2;
  return Math.round(bpm);
}
