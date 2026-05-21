# Speaker Diarization Quality Evaluation

Date: 2026-05-21

## Scope

The evaluation checks speaker structure in existing transcript outputs and prepares human speaker references:
- `eval/reference/sample_01_speakers.json`
- `eval/reference/sample_02_speakers.json`

DER/JER are not computed yet because there is no human-labeled speaker timeline. Without start/end speaker ground truth, DER would be theater.

## Observed Speaker Structure

| Sample | Apparent labels | Speaker turns | Suspicious labels |
| --- | ---: | ---: | --- |
| sample_01 | 5 | 49 | `Как`, `Pmi`, `Из` |
| sample_02 | 5 | 25 | `По`, `Кто`, `Какая` |

The apparent count of 5 speakers is false. The transcript contains invalid labels that are actually fragments of text misclassified as speakers. This is a serious defect because the UI/export presents corrupted dialogue structure as if it were valid diarization.

## Failure Modes Found

1. Speaker labels are generic, not identity-aware.
   `Спикер 1` and `Спикер 2` are acceptable as raw diarization labels, but they are not names. The system cannot infer stable human names reliably from audio alone.

2. Text fragments become speaker labels.
   Examples observed: `По:`, `Кто:`, `Какая:`, `Как:`, `Из:`. This usually comes from regex/post-processing that treats any short line ending with `:` as a speaker. That is not safe.

3. Two-speaker bias is still a risk.
   The current backend defaults to `DIARIZATION_MIN_SPEAKERS=2` and `DIARIZATION_MAX_SPEAKERS=4`, which is sane for this project. But older output still shows the app can collapse real meetings into too few useful speakers or create false labels.

4. False switches cannot be quantified yet.
   We need human speaker turns to measure missed changes, false changes, and speaker confusion.

## Current Good Decisions

- Diarization is now enabled by default.
- pyannote is used instead of text-only speaker guessing.
- ASR word timestamps are passed into diarization mapping.
- A single Whisper segment can be split by word timestamps when speakers change inside it.
- Pyannote receives preloaded audio through torchaudio, which avoids the fragile pyannote/torchcodec Windows decoder path.

These are the right engineering moves. They reduce the main cause of "one blob assigned to one speaker".

## Assessment

Diarization is improved architecturally, but it is not yet production-grade. The app still lacks a hard validation layer that says: "this speaker map is suspect; do not trust it blindly."

Minimum bar before calling this good:
- Human speaker timeline for each eval sample.
- DER/JER or at least turn-level confusion matrix.
- Reject or downgrade labels that are not from the diarization engine or an approved participant map.
- UI warning when diarization fails or falls back.
- Optional participant list before upload, so names can be mapped after diarization instead of guessed.
