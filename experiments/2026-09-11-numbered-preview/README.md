# Direct numbered-note preview

Reads raw event fields from the existing cross-validation JSON, without MusicXML,
PDF, quantization, filtering, or score-reference input. Fixed display convention:
1=C, C4 is unmarked 1; octave displacement uses dots, chromatic notes use sharps.
This is a timestamped polyphonic preview, not standard rhythmic jianpu.

Onsets spanning at most 60ms share a display card, without moving events or
asserting a chord. Original starts/durations and all 832 four-model events are
preserved. AnthemScore's 91 arranged events are shown separately and labeled as
covering only the first 30 seconds. Orange marks indicate cross-model disagreement,
including duration differences; they are not error judgments.

Run from repository root:

```sh
python experiments/2026-09-11-numbered-preview/build.py
python -m unittest discover -s experiments/2026-09-11-numbered-preview
```

Output: `outputs/查看识谱结果/20-直接数字音符预览/先看这里.html`.
Runtime requires the previous local comparison artifacts. Source audio is copied
unchanged for playback. Browser QA checked model/segment switches, octave labels,
coverage messaging, and a real click seeking/playing at 26.8 seconds. Three
conversion/grouping tests passed. This does not establish transcription accuracy.
