import type { Note } from './score';
export const MAX_AUDIO_SECONDS = 600;
export const MAX_AUDIO_BYTES = 100 * 1024 * 1024;
const SAMPLE_RATE = 22050;
export interface AudioChunk {
  start: number;
  end: number;
  inputStart: number;
  inputEnd: number;
}
export function audioChunks(duration: number): AudioChunk[] {
  const chunks: AudioChunk[] = [];
  for (let start = 0; start < duration; start += 30)
    chunks.push({
      start,
      end: Math.min(duration, start + 30),
      inputStart: Math.max(0, start - 2),
      inputEnd: Math.min(duration, start + 32),
    });
  return chunks;
}
export function mergeChunkNotes(
  previous: Note[],
  local: Note[],
  chunk: AudioChunk,
): Note[] {
  const result = previous.map((n) => ({ ...n }));
  for (const note of local) {
    const start = note.start + chunk.inputStart,
      end = Math.min(chunk.inputEnd, start + note.duration);
    if (start >= chunk.end || end <= start) continue;
    // Reconcile the overlap before applying ownership, including notes extending past the prior input window.
    const duplicate = result.findLast(
      (n) =>
        n.pitch === note.pitch &&
        Math.abs(n.start - start) < 0.06 &&
        n.start + n.duration > start,
    );
    if (duplicate) {
      duplicate.duration = Math.max(duplicate.duration, end - duplicate.start);
      continue;
    }
    if (start < chunk.start) {
      // A note detected at the input edge can be a continuation with its real onset outside this window.
      if (note.start <= 0.15) {
        const held = result.findLast(
          (n) =>
            n.pitch === note.pitch &&
            n.start < chunk.inputStart &&
            n.start + n.duration >= chunk.start - 0.12,
        );
        if (held) {
          held.duration = Math.max(held.duration, end - held.start);
          continue;
        }
      }
      // Allow unmatched onsets just before the seam: model timing can shift across the ownership cutoff.
      if (start < chunk.start - 0.06) continue;
    }
    result.push({
      ...note,
      id: `chunk-${chunk.start}-${result.length}`,
      start,
      duration: end - start,
    });
  }
  return result.sort((a, b) => a.start - b.start || a.pitch - b.pitch);
}
interface WorkerResult {
  type: string;
  progress?: number;
  label?: string;
  notes?: Note[];
  message?: string;
}
export interface WorkerPort {
  onmessage: ((event: { data: WorkerResult }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  postMessage(
    data: { audio: Float32Array; origin: string },
    transfer: ArrayBuffer[],
  ): void;
  terminate(): void;
}
export function recommendedParallelism(
  cores = typeof navigator === 'undefined' ? 2 : navigator.hardwareConcurrency,
  memoryGB = typeof navigator === 'undefined'
    ? undefined
    : (navigator as Navigator & { deviceMemory?: number }).deviceMemory,
): number {
  return cores >= 4 && (memoryGB === undefined || memoryGB >= 4) ? 2 : 1;
}
export async function transcribeAudio(
  samples: Float32Array,
  origin: string,
  onProgress: (progress: number, label: string) => void,
  signal: AbortSignal,
  createWorker: () => WorkerPort = () =>
    new Worker(new URL('./transcribe.worker.ts', import.meta.url), {
      type: 'module',
    }) as unknown as WorkerPort,
  concurrency = 1,
): Promise<Note[]> {
  signal.throwIfAborted();
  const chunks = audioChunks(samples.length / SAMPLE_RATE);
  const parallelism = Math.min(
    chunks.length,
    Math.max(1, Math.min(4, Math.floor(concurrency) || 1)),
  );
  const results: Note[][] = Array.from({ length: chunks.length }, () => []);
  const progress = chunks.map(() => 0);
  const group = new AbortController();
  const abortGroup = () => group.abort();
  signal.addEventListener('abort', abortGroup, { once: true });
  let next = 0,
    completed = 0;
  let failure: unknown;
  const report = (i: number, value: number) => {
    progress[i] = Math.max(progress[i], Math.min(100, Math.max(0, value)));
    onProgress(
      Math.min(
        99,
        Math.round(progress.reduce((sum, p) => sum + p, 0) / chunks.length),
      ),
      `${parallelism} 路并行 · 已完成 ${completed}/${chunks.length} 段`,
    );
  };
  const infer = (i: number) =>
    new Promise<Note[]>((resolve, reject) => {
      const chunk = chunks[i],
        worker = createWorker();
      let finished = false;
      let timer: ReturnType<typeof setTimeout>;
      const finish = (error?: Error, result?: Note[]) => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        group.signal.removeEventListener('abort', abort);
        worker.onmessage = null;
        worker.onerror = null;
        worker.terminate();
        if (error) reject(error);
        else resolve(result ?? []);
      };
      const abort = () => finish(new DOMException('识别已取消', 'AbortError'));
      const touch = () => {
        clearTimeout(timer);
        timer = setTimeout(
          () =>
            finish(new Error(`第 ${i + 1} 段连续 5 分钟没有进展，请重试。`)),
          300000,
        );
      };
      group.signal.addEventListener('abort', abort, { once: true });
      worker.onmessage = ({ data }) => {
        if (finished) return;
        touch();
        if (data.type === 'complete') finish(undefined, data.notes);
        else if (data.type === 'error')
          finish(
            new Error(
              `第 ${i + 1} 段识别失败：${data.message ?? '未知错误'}。可降低并行数量后重试。`,
            ),
          );
        else if (data.type === 'progress') report(i, data.progress ?? 0);
      };
      worker.onerror = () =>
        finish(new Error('识别引擎运行失败，请降低并行数量或检查网络后重试。'));
      touch();
      try {
        group.signal.throwIfAborted();
        const audio = samples.slice(
          Math.round(chunk.inputStart * SAMPLE_RATE),
          Math.round(chunk.inputEnd * SAMPLE_RATE),
        );
        report(i, 0);
        worker.postMessage({ audio, origin }, [audio.buffer]);
      } catch (error) {
        finish(error instanceof Error ? error : new Error('音频分段失败'));
      }
    });
  const lane = async () => {
    try {
      while (next < chunks.length && !group.signal.aborted) {
        const i = next++;
        results[i] = await infer(i);
        group.signal.throwIfAborted();
        completed++;
        report(i, 100);
      }
    } catch (error) {
      if (!group.signal.aborted) {
        failure = error;
        group.abort();
      }
    }
  };
  try {
    await Promise.all(Array.from({ length: parallelism }, () => lane()));
    signal.throwIfAborted();
    if (failure) throw failure;
    // Stitch in source order even when workers finish in a different order.
    let notes: Note[] = [];
    for (let i = 0; i < chunks.length; i++)
      notes = mergeChunkNotes(notes, results[i], chunks[i]);
    onProgress(100, '识别完成');
    return notes;
  } finally {
    signal.removeEventListener('abort', abortGroup);
    group.abort();
  }
}
