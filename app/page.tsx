'use client';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Check,
  Download,
  FileAudio,
  Headphones,
  LoaderCircle,
  Music2,
  Piano,
  Play,
  ShieldCheck,
  Square,
  Upload,
  X,
} from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { StaffScore, NumberedScore } from '@/components/score-view';
import { NoteEditor } from '@/components/note-editor';
import { transcribeAudio } from '@/lib/music/long-audio';
import { decodeFile, makeDemo, synthesize } from '@/lib/music/audio';
import { download, toMidi } from '@/lib/music/export';
import {
  estimateTempo,
  KEYS,
  quantizeNotes,
  toMusicXML,
  type Note,
} from '@/lib/music/score';

const formatTime = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
export default function Home() {
  const [file, setFile] = useState<File | null>(null),
    [samples, setSamples] = useState<Float32Array | null>(null),
    [wave, setWave] = useState<number[]>([]),
    [duration, setDuration] = useState(0),
    [audioURL, setAudioURL] = useState('');
  const [notes, setNotes] = useState<Note[]>([]),
    [original, setOriginal] = useState<Note[]>([]),
    [bpm, setBpm] = useState(100),
    [beats, setBeats] = useState(4),
    [key, setKey] = useState(0),
    [title, setTitle] = useState('未命名乐谱');
  const [status, setStatus] = useState<
      'empty' | 'loading' | 'ready' | 'working' | 'done'
    >('empty'),
    [progress, setProgress] = useState(0),
    [label, setLabel] = useState(''),
    [error, setError] = useState(''),
    [tab, setTab] = useState('staff'),
    [playing, setPlaying] = useState(false),
    [isDemo, setIsDemo] = useState(false),
    [scoreReady, setScoreReady] = useState(false),
    [drag, setDrag] = useState(false);
  const picker = useRef<HTMLInputElement>(null),
    task = useRef<AbortController | null>(null),
    stopAudio = useRef<(() => void) | null>(null),
    generation = useRef(0),
    audioRef = useRef<HTMLAudioElement>(null);
  const busy = status === 'loading' || status === 'working';
  const options = useMemo(
    () => ({ title, bpm, beats, key }),
    [title, bpm, beats, key],
  );
  const xml = useMemo(
    () => (notes.length ? toMusicXML(notes, options) : ''),
    [notes, options],
  );
  const setReady = useCallback((ready: boolean) => setScoreReady(ready), []);
  function stop() {
    stopAudio.current?.();
    stopAudio.current = null;
    setPlaying(false);
  }
  function killWorker() {
    task.current?.abort();
    task.current = null;
  }
  useEffect(
    () => () => {
      task.current?.abort();
      stopAudio.current?.();
    },
    [],
  );
  useEffect(
    () => () => {
      if (audioURL) URL.revokeObjectURL(audioURL);
    },
    [audioURL],
  );
  async function choose(next: File) {
    const run = ++generation.current;
    killWorker();
    stop();
    audioRef.current?.pause();
    setError('');
    setStatus('loading');
    setNotes([]);
    setOriginal([]);
    setSamples(null);
    setFile(next);
    setIsDemo(false);
    setScoreReady(false);
    setAudioURL('');
    setWave([]);
    setDuration(0);
    setTitle(next.name.replace(/\.[^.]+$/, ''));
    try {
      const decoded = await decodeFile(next);
      if (run !== generation.current) return;
      setSamples(decoded.samples);
      setDuration(decoded.duration);
      setWave(decoded.wave);
      setAudioURL(URL.createObjectURL(next));
      setStatus('ready');
    } catch (e) {
      if (run !== generation.current) return;
      setError(e instanceof Error ? e.message : '音频读取失败');
      setStatus('empty');
      setFile(null);
    }
  }
  async function demo() {
    const d = makeDemo();
    await choose(new File([d.blob], '谱间练习曲.wav', { type: 'audio/wav' }));
  }
  function exampleScore() {
    stop();
    killWorker();
    generation.current++;
    const d = makeDemo();
    setNotes(d.notes);
    setOriginal(d.notes);
    setBpm(120);
    setBeats(4);
    setKey(0);
    setTitle('谱间练习曲');
    setIsDemo(true);
    setStatus('done');
    setError('');
    setAudioURL(URL.createObjectURL(d.blob));
    setDuration(17);
    setWave([]);
    setFile(null);
    setSamples(null);
  }
  async function transcribe() {
    if (!samples) return;
    killWorker();
    const run = ++generation.current;
    const controller = new AbortController();
    task.current = controller;
    stop();
    audioRef.current?.pause();
    setError('');
    setProgress(0);
    setLabel('正在准备音频…');
    setStatus('working');
    setIsDemo(false);
    setNotes([]);
    setOriginal([]);
    setScoreReady(false);
    try {
      const result = await transcribeAudio(
        samples,
        window.location.origin,
        (p, message) => {
          if (run === generation.current) {
            setProgress(p);
            setLabel(message);
          }
        },
        controller.signal,
      );
      if (run !== generation.current) return;
      if (!result.length) {
        setStatus('ready');
        setError('没有识别到清晰音符。请尝试音量更大、背景更安静的钢琴录音。');
        return;
      }
      setNotes(result);
      setOriginal(result);
      setBpm(estimateTempo(result));
      setProgress(100);
      setStatus('done');
      setTab('staff');
    } catch (error) {
      if (run !== generation.current || controller.signal.aborted) return;
      setStatus('ready');
      setError(error instanceof Error ? error.message : '识别未完成，请重试。');
    } finally {
      if (task.current === controller) task.current = null;
    }
  }
  function cancel() {
    generation.current++;
    killWorker();
    if (!samples) setFile(null);
    setStatus(samples ? 'ready' : 'empty');
    setLabel('');
  }
  function listen() {
    if (playing) {
      stop();
      return;
    }
    audioRef.current?.pause();
    const q = quantizeNotes(notes, bpm).map((n) => ({
      ...n,
      start: (n.tick * 15) / bpm,
      duration: (n.ticks * 15) / bpm,
    }));
    stopAudio.current = synthesize(q, bpm, bpm, () => setPlaying(false));
    setPlaying(true);
  }
  function changeNotes(n: Note[]) {
    stop();
    setNotes(n);
  }
  function exportFile(kind: 'xml' | 'midi') {
    try {
      if (kind === 'xml')
        download(
          xml,
          'application/vnd.recordare.musicxml+xml',
          `${title}.musicxml`,
        );
      else {
        const data = toMidi(notes, options);
        download(new Uint8Array(data).buffer, 'audio/midi', `${title}.mid`);
      }
    } catch {
      setError('导出失败，请检查音符数据后重试。');
    }
  }
  const hasScore = status === 'done';
  return (
    <main className="studio">
      <header className="topbar">
        <Link className="brand" href="/">
          <span className="brand-icon">
            <Music2 size={24} />
          </span>
          <strong>谱间</strong>
          <span className="wordmark">MUSIC2PDF</span>
        </Link>
        <span className="edition">
          PIANO EDITION <span>01</span>
        </span>
      </header>
      <div className="workspace">
        <section className="intro">
          <div>
            <p className="eyebrow">从声音，到乐谱</p>
            <h1>把听见的，写成谱。</h1>
            <p>导入钢琴演奏，识别音符，让灵感落在纸上。</p>
          </div>
          <span className="version">
            <span /> 钢琴转谱 · 初版
          </span>
        </section>
        <div className="work-grid">
          <aside className="input-panel">
            <div className="section-label">
              <span>01</span> 音频来源
            </div>
            <input
              className="sr-only"
              ref={picker}
              type="file"
              accept=".mp3,.wav,.flac,.m4a,.ogg,.aac,.aiff,.aif"
              aria-label="选择音频文件"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void choose(f);
                e.target.value = '';
              }}
            />
            <div
              className={`dropzone ${drag ? 'dragging' : ''}`}
              onDragOver={(e) => {
                e.preventDefault();
                if (!busy) setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                if (!busy && e.dataTransfer.files[0])
                  void choose(e.dataTransfer.files[0]);
              }}
            >
              <span className="upload-icon">
                {status === 'loading' ? (
                  <LoaderCircle className="spin" />
                ) : file ? (
                  <FileAudio />
                ) : (
                  <Upload />
                )}
              </span>
              <h2>{file ? '音频已就位' : '放入你的音乐'}</h2>
              <p className="filename">
                {file?.name ?? '拖入音频文件，或点击选择'}
              </p>
              <button
                className="primary"
                disabled={busy}
                onClick={() => picker.current?.click()}
              >
                <Upload size={15} />
                {file ? '更换音频' : '选择音频文件'}
              </button>
              <small>
                MP3 / WAV / FLAC / M4A 等<br />
                最长 10 分钟 · 最大 100 MB
              </small>
            </div>
            {audioURL && (
              <div className="audio-source">
                <div className="audio-label">
                  <span>原始音频</span>
                  <span>{formatTime(duration)}</span>
                </div>
                {wave.length > 0 && (
                  <div className="waveform" aria-hidden="true">
                    {wave.map((v, i) => (
                      <i
                        key={i}
                        style={{ height: `${Math.max(4, v * 100)}%` }}
                      />
                    ))}
                  </div>
                )}
                {/* oxlint-disable-next-line jsx-a11y/media-has-caption -- User-supplied instrumental audio; the score is its accessible textual counterpart. */}
                <audio ref={audioRef} controls src={audioURL} onPlay={stop} />
              </div>
            )}
            {!busy && (
              <button
                className="text-button demo-button"
                onClick={() => void demo()}
              >
                <Headphones size={14} /> 没有音频？试试练习曲{' '}
                <ArrowRight size={14} />
              </button>
            )}
            <div className="instrument-card">
              <Piano />
              <div>
                <strong>钢琴独奏</strong>
                <p>支持同时发声的旋律与和弦</p>
              </div>
              <Check size={15} />
            </div>
            {(status === 'ready' || (hasScore && samples)) && (
              <button
                className="primary transcribe-button"
                onClick={() => void transcribe()}
              >
                {' '}
                {hasScore ? '重新识别' : '开始转谱'} <ArrowRight size={16} />
              </button>
            )}
            {busy && (
              <output className="processing">
                <div>
                  <LoaderCircle size={15} className="spin" />
                  <span>{status === 'loading' ? '正在读取音频…' : label}</span>
                </div>
                {status === 'working' && (
                  <>
                    <Progress value={progress} aria-label="识别进度" />
                    <small>
                      {progress}% · 长音频会自动分段，请保持页面打开
                    </small>
                  </>
                )}
                <button className="text-button" onClick={cancel}>
                  <X size={13} /> 取消
                </button>
              </output>
            )}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <p className="privacy">
              <ShieldCheck size={15} /> 音频仅在浏览器内处理，不会上传
            </p>
            <p className="model-note">
              Basic Pitch
              多音识别。适合清晰的独奏录音；歌曲与交响乐分轨尚未开放。
            </p>
          </aside>
          <section className="score-panel">
            <div className="score-toolbar">
              <div className="section-label">
                <span>02</span> 乐谱工作台
              </div>
              <span className="muted">
                {hasScore
                  ? `${notes.length} 个音符 · ${isDemo ? '示例乐谱' : '识别初稿'}`
                  : '等待音频'}
              </span>
            </div>
            {!hasScore ? (
              <div className="empty-score">
                <Music2 size={44} strokeWidth={1} />
                <h2>
                  {busy ? '音乐正在变成音符。' : '下一页，属于你的音乐。'}
                </h2>
                <p>
                  {busy
                    ? '完成后，可对照原音试听、校正与导出。'
                    : '五线谱保留多声部，简谱提取主旋律候选。'}
                </p>
                <button
                  className="secondary"
                  onClick={exampleScore}
                  disabled={busy}
                >
                  先看看示例乐谱 <ArrowRight size={14} />
                </button>
                <span>
                  导入音频 <ArrowRight size={12} /> 识别音符{' '}
                  <ArrowRight size={12} /> 校正与导出
                </span>
              </div>
            ) : (
              <>
                <div className="score-settings">
                  <label className="title-setting">
                    曲名
                    <input
                      aria-label="曲名"
                      maxLength={80}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    速度 · BPM
                    <input
                      aria-label="速度 BPM"
                      type="number"
                      min={30}
                      max={240}
                      value={bpm}
                      onChange={(e) => {
                        stop();
                        setBpm(
                          Math.min(
                            240,
                            Math.max(30, Number(e.target.value) || 100),
                          ),
                        );
                      }}
                    />
                  </label>
                  <div className="setting">
                    <span id="meter-label">拍号</span>
                    <Select
                      value={String(beats)}
                      onValueChange={(v) => {
                        stop();
                        setBeats(Number(v));
                      }}
                    >
                      <SelectTrigger aria-labelledby="meter-label">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[2, 3, 4].map((v) => (
                          <SelectItem value={String(v)} key={v}>
                            {v}/4
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="setting">
                    <span id="key-label">调性 · 大调</span>
                    <Select
                      value={String(key)}
                      onValueChange={(v) => setKey(Number(v))}
                    >
                      <SelectTrigger aria-labelledby="key-label">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {KEYS.map((v, i) => (
                          <SelectItem value={String(i)} key={v}>
                            {v}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="result-note">
                  {isDemo
                    ? '示例使用已知音符生成，用于体验排版。选择「试试练习曲」可运行真实识别。'
                    : '速度为粗略估计；拍号与调性默认 4/4、C 大调，请按原曲调整。按中央 C 分上下谱表，声部需校正。'}
                </div>
                <div className="view-controls">
                  <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
                    <TabsList>
                      <TabsTrigger value="staff">五线谱</TabsTrigger>
                      <TabsTrigger value="numbered">简谱</TabsTrigger>
                      <TabsTrigger value="edit">校正音符</TabsTrigger>
                    </TabsList>
                  </Tabs>
                  <button
                    className="secondary listen"
                    onClick={listen}
                    disabled={!notes.length}
                  >
                    {playing ? <Square size={14} /> : <Play size={14} />}{' '}
                    {playing ? '停止试听' : '试听乐谱'}
                  </button>
                </div>
                <div className="score-paper">
                  {!notes.length ? (
                    <p className="empty-notes">
                      还没有音符，可在「校正音符」中添加。
                    </p>
                  ) : tab === 'staff' ? (
                    <StaffScore xml={xml} onReady={setReady} />
                  ) : tab === 'numbered' ? (
                    <NumberedScore notes={notes} options={options} />
                  ) : null}
                  {tab === 'edit' && (
                    <NoteEditor
                      notes={notes}
                      onChange={changeNotes}
                      onReset={() =>
                        changeNotes(original.map((n) => ({ ...n })))
                      }
                    />
                  )}
                </div>
                <div className="export-bar">
                  <span>
                    <Check size={14} />{' '}
                    {tab === 'numbered'
                      ? '主旋律简谱'
                      : tab === 'edit'
                        ? '修改后自动更新乐谱'
                        : '完整音符 · 双谱表'}
                  </span>
                  <div>
                    <button
                      className="secondary"
                      disabled={!notes.length}
                      onClick={() => exportFile('xml')}
                    >
                      MusicXML
                    </button>
                    <button
                      className="secondary"
                      disabled={!notes.length}
                      onClick={() => exportFile('midi')}
                    >
                      MIDI
                    </button>
                    <button
                      className="primary"
                      disabled={
                        !notes.length ||
                        tab === 'edit' ||
                        (tab === 'staff' && !scoreReady)
                      }
                      onClick={() => {
                        stop();
                        window.print();
                      }}
                    >
                      <Download size={15} /> 打印 / PDF
                    </button>
                  </div>
                </div>
                <p className="export-hint">
                  PDF：在打印窗口中选择「另存为 PDF」。MIDI 与 MusicXML
                  导出全部音符；试听使用合成音色。
                </p>
              </>
            )}
          </section>
        </div>
        <footer>
          谱间 / MUSIC2PDF<span>从钢琴出发，走向更多声部。</span>
        </footer>
      </div>
    </main>
  );
}
