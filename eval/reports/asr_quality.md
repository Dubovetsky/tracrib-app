# ASR Quality Evaluation

Date: 2026-05-21

## Scope

Evaluation pack inputs:
- `eval/audio/sample_01.m4a`
- `eval/audio/sample_02.m4a`

Measured hypotheses used for this pass:
- `backend/data/results/60f7742e-27db-4f47-a285-e66670e751f8/transcript.txt`
- `backend/data/results/26a41da7-4a8e-472a-8f85-6fb721560e91/transcript.txt`

Important limitation: these are existing transcript outputs, not a verified fresh golden run against the trimmed `eval/audio` clips. This is still useful for defect discovery, but it is not a final ASR benchmark.

## Metrics

| Sample | WER | CER | Words | Chars | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| sample_01 | N/A | N/A | 5463 | 32395 | blocked: no human reference |
| sample_02 | N/A | N/A | 2646 | 15428 | blocked: no human reference |

WER/CER are deliberately not invented. Without a human reference transcript, any numeric WER/CER would be fake precision.

Reference files are prepared here:
- `eval/reference/sample_01_reference.txt`
- `eval/reference/sample_02_reference.txt`

After human references are filled, run:

```powershell
python eval\tools\evaluate_transcripts.py --repo . --output eval\reports\metrics.json --sample sample_01 backend\data\results\60f7742e-27db-4f47-a285-e66670e751f8\transcript.txt eval\reference\sample_01_reference.txt eval\reference\sample_01_speakers.json --sample sample_02 backend\data\results\26a41da7-4a8e-472a-8f85-6fb721560e91\transcript.txt eval\reference\sample_02_reference.txt eval\reference\sample_02_speakers.json
```

## Term Handling

Observed domain-term hits:

| Sample | EADR | ADR | Jira | AirPoint | GSM | CM | QA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sample_01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sample_02 | 0 | 0 | 6 | 1 | 9 | 1 | 3 |

Observed suspect term forms:

| Sample | Suspect forms |
| --- | --- |
| sample_01 | `Жира` x1 |
| sample_02 | `Эрпоинт` x4 |

This means the glossary/hotwords path helps only partially. It can bias Whisper, but it does not guarantee canonical spelling. For production use, domain-term normalization must be explicit and auditable.

## Hallucinations And Fidelity

No honest hallucination score is possible without human reference text. The current app also has a fidelity risk if text polishing is enabled: ASR output and LLM-cleaned output must be separated. The canonical transcript should be raw ASR plus diarization; any cleaned summary should be a secondary artifact with clear labeling.

## Assessment

Current ASR quality is not yet benchmarked. It may be operationally useful, but it is not quality-controlled. The app has the right direction now: `large-v3-turbo`, `word_timestamps=True`, `condition_on_previous_text=False`, and domain hotwords. The missing piece is a repeatable golden evaluation set.

Minimum bar before calling this good:
- 10-20 representative audio clips with human references.
- WER/CER computed in CI or a local smoke command.
- Separate tracking for terms, names, and hallucinations.
- A failed quality gate when known terms like EADR, Jira, AirPoint, GSM are mangled.
- No LLM rewrite in the canonical transcript path.
