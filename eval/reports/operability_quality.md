# Reliability / Operability Evaluation

Date: 2026-05-21

## Checks Run

| Area | Result |
| --- | --- |
| Python compile | PASS |
| Backend health | PASS: `GET /api/health` returned `ok` |
| Frontend build | PASS: `npm run build` completed |
| Unit tests | PASS outside sandbox: 36 passed |
| Unit tests inside sandbox | FAIL: Windows ACL blocks pytest temp cleanup |
| Upload/result E2E | NOT RUN in this pass |
| Logs | Weak: `backend/data/logs/backend.log` exists but is empty |

Commands used:

```powershell
python -m py_compile backend\app\exports.py backend\app\settings.py backend\app\transcriber.py backend\app\services.py backend\app\diarization.py eval\tools\evaluate_transcripts.py
python -m pytest tests\test_db.py tests\test_exports.py tests\test_postprocess.py tests\test_text_polish.py tests\test_diarization.py tests\test_transcriber_fallback.py tests\test_diarization_audio.py -p no:cacheprovider --basetemp=backend\data\pytest-tmp-eval
npm.cmd run build
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health
```

## Production Failure Modes

1. Silent quality degradation.
   The backend intentionally does not fail the job when diarization fails. That is good for availability, bad for correctness. The result must carry a visible warning such as `diarization_status=failed|fallback|ok`.

2. No quality metadata in API result.
   `/api/jobs/{id}` should expose model, device, compute type, diarization status, speaker count, timings, warnings, and export paths. Otherwise the operator cannot distinguish a good transcript from a fallback transcript.

3. Logs are not yet useful.
   An empty log file after real work means operability is weak. Need structured logs with job id, phase, duration, device, model, error, and fallback reason.

4. Tests depend on environment permissions.
   The sandbox failure is not an app logic failure, but it proves the test command is not robust. Put pytest temp/cache paths into project config so a developer does not have to remember Windows-specific flags.

5. Upload/result E2E is not automated.
   The app has endpoint tests for internals, but no smoke test that starts backend, uploads a small audio file, polls status, downloads TXT/SRT/VTT, and verifies non-empty output.

## Minimum Quality Standard

For a local production-like transcription product, the next bar is not more features. The bar is observability and repeatability:

- One command for backend smoke test.
- One command for frontend build.
- One command for ASR/diarization eval.
- Visible warnings on degraded output.
- Structured job timings.
- Small golden audio fixtures.
- Human references for WER/CER and speaker turns.
- Clear separation of raw transcript, diarized transcript, and optional cleaned summary.
