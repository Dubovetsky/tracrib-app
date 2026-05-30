# Evaluation Summary

Date: 2026-05-21

## Scores

These are engineering-readiness scores, not marketing scores.

| Dimension | Score | Verdict |
| --- | ---: | --- |
| ASR Accuracy | 5/10 | Architecture improved, but no golden WER/CER yet. |
| Speaker Diarization Quality | 4/10 | Real diarization path exists, but old outputs show invalid speaker labels. |
| Content Fidelity | 4/10 | Cannot prove fidelity without human reference; LLM polishing must not touch canonical transcript. |
| Reliability / Operability | 6/10 | Backend/frontend start and tests pass, but warnings/logs/smoke tests are weak. |
| Throughput / Cost / UX | 6/10 | ASR on GPU is fast; diarization throughput and degraded-result UX still need proof. |

## Hard Truth

The app is better than a raw MVP now, but it is not yet a quality-controlled transcription product. The biggest risk is not that Whisper makes mistakes. The biggest risk is that the system can produce a confident-looking transcript with broken speaker structure and no visible warning.

## Highest-Leverage Improvements

1. Add `diarization_status`, `speaker_count`, `warnings`, and phase timings to every job result.
2. Stop accepting arbitrary `Text:` patterns as speaker labels unless they came from diarization or an approved participant map.
3. Fill human references in `eval/reference/*` and compute WER/CER on every candidate change.
4. Add a small upload E2E smoke test with the eval audio clips.
5. Keep raw transcript immutable; put LLM cleanup/summaries in separate artifacts.
6. Add participant metadata in UI: expected speaker count and optional names before upload.

## Files Created

- `eval/audio/sample_01.m4a`
- `eval/audio/sample_02.m4a`
- `eval/reference/sample_01_reference.txt`
- `eval/reference/sample_02_reference.txt`
- `eval/reference/sample_01_speakers.json`
- `eval/reference/sample_02_speakers.json`
- `eval/tools/evaluate_transcripts.py`
- `eval/reports/metrics.json`
- `eval/reports/asr_quality.md`
- `eval/reports/diarization_quality.md`
- `eval/reports/operability_quality.md`
