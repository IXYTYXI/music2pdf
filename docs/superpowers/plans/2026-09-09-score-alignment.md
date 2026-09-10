# Score alignment implementation plan

Goal: integrate MuseScore conversion/editing, explicit-tempo score timeline, audio-to-measure DTW proposals, and editable persisted alignment maps.
Architecture: score_timeline.py reads MusicXML through music21; alignment_service.py performs bounded-memory chroma DTW in a serialized background job; dataset_alignment.py exposes local APIs and protected artifacts; alignment.js owns the workbench UI. Existing source files remain unchanged. Results are estimates until manually reviewed.

- [x] Install the official macOS MuseScore binary; test command-line conversion with an existing MXL.
- [x] Parse notes in sounding pitch, explicit tempo changes, time signatures and repeated measure occurrences. Require user BPM when missing, and identify expressive timing not modeled. Unit tests: dotted tempo, tempo change, repeats, transposition.
- [x] Build duration-weighted score chroma and audio chroma; subsequence DTW produces measure ranges with raw matching costs. Bound matrix size by reducing temporal resolution. Validate time ranges and missing notes. Unit test a known stretched feature alignment.
- [x] Local API: prepare score, list suitable score/audio sources including OMR outputs, run/poll job, edit/save/export mapped ranges. Originals never overwritten; keep input hashes and automatic proposal separately from corrected result. Tests: paths, invalid/nonmonotonic edits, repeat IDs, source preservation.
- [x] UI: select files/page-derived score, open MuseScore, choose score and audio ranges, inspect theory timing, run alignment, listen per measure, adjust boundaries and save. Keep automatic output labeled unreviewed.
- [x] Run real conversion and alignment against available matching recording candidates. Do not claim accuracy or a three-piece evaluation without manual reference labels. Restart local service only when existing jobs are idle; verify live APIs and update documentation.

Verification: 128 backend tests passed. Live MuseScore conversion/PDF rendering and independent alignment worker completed on one existing recording/OMR score pair. Saved an explicitly unreviewed draft and verified JSON export. A three-work manual timing benchmark and orchestral accuracy measurement remain future validation, not claimed complete.
