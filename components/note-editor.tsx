'use client';
import { useState } from 'react';
import { Plus, Trash2, RotateCcw } from 'lucide-react';
import { pitchName, type Note } from '@/lib/music/score';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
export function NoteEditor({
  notes,
  onChange,
  onReset,
}: {
  notes: Note[];
  onChange: (n: Note[]) => void;
  onReset: () => void;
}) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(notes.length / 20)),
    safePage = Math.min(page, pages - 1);
  function update(
    id: string,
    field: 'pitch' | 'start' | 'duration',
    value: number,
  ) {
    if (!Number.isFinite(value)) return;
    const clamped =
      field === 'pitch'
        ? Math.min(108, Math.max(21, Math.round(value)))
        : field === 'start'
          ? Math.min(600, Math.max(0, value))
          : Math.min(600, Math.max(0.05, value));
    onChange(notes.map((n) => (n.id === id ? { ...n, [field]: clamped } : n)));
  }
  return (
    <div className="note-editor">
      <div className="editor-intro">
        <p>
          修改音高、起点或时长后，乐谱和导出会同步更新。音高使用 MIDI 编号。
        </p>
        <button className="text-button" onClick={onReset}>
          <RotateCcw size={14} /> 撤销全部修改
        </button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>音符</TableHead>
            <TableHead>音高</TableHead>
            <TableHead>起点 / 秒</TableHead>
            <TableHead>时长 / 秒</TableHead>
            <TableHead>
              <span className="sr-only">删除</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {notes.slice(safePage * 20, safePage * 20 + 20).map((n) => (
            <TableRow key={n.id}>
              <TableCell>{pitchName(n.pitch)}</TableCell>
              <TableCell>
                <input
                  aria-label={`${n.id} 音高`}
                  type="number"
                  min={21}
                  max={108}
                  value={n.pitch}
                  onChange={(e) =>
                    update(n.id, 'pitch', Number(e.target.value))
                  }
                />
              </TableCell>
              <TableCell>
                <input
                  aria-label={`${n.id} 起点`}
                  type="number"
                  min={0}
                  max={600}
                  step={0.01}
                  value={Number(n.start.toFixed(3))}
                  onChange={(e) =>
                    update(n.id, 'start', Number(e.target.value))
                  }
                />
              </TableCell>
              <TableCell>
                <input
                  aria-label={`${n.id} 时长`}
                  type="number"
                  min={0.05}
                  max={600}
                  step={0.01}
                  value={Number(n.duration.toFixed(3))}
                  onChange={(e) =>
                    update(n.id, 'duration', Number(e.target.value))
                  }
                />
              </TableCell>
              <TableCell>
                <button
                  className="icon-button"
                  aria-label={`删除 ${pitchName(n.pitch)}`}
                  onClick={() => onChange(notes.filter((x) => x.id !== n.id))}
                >
                  <Trash2 size={15} />
                </button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="editor-actions">
        <button
          className="secondary"
          onClick={() => {
            onChange([
              ...notes,
              {
                id: crypto.randomUUID(),
                pitch: 60,
                start: Math.max(0, ...notes.map((n) => n.start)),
                duration: 0.5,
                velocity: 0.7,
                track: 'piano',
              },
            ]);
            setPage(Math.floor(notes.length / 20));
          }}
        >
          <Plus size={14} /> 添加音符
        </button>
        <span>
          <button
            className="text-button"
            disabled={safePage === 0}
            onClick={() => setPage(safePage - 1)}
          >
            上一页
          </button>{' '}
          {safePage + 1} / {pages}{' '}
          <button
            className="text-button"
            disabled={safePage === pages - 1}
            onClick={() => setPage(safePage + 1)}
          >
            下一页
          </button>
        </span>
      </div>
    </div>
  );
}
