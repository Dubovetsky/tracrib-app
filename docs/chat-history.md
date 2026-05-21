# Chat History

## Session 12: remove subtitle/JSON exports and stop fake speaker alternation

Date: 2026-05-21

Request: remove SRT/VTT/JSON outputs, keep separate RAW, show improved text in the app and TXT download, and fix the main quality defect: speaker assignment looked random even when raw ASR words were acceptable.

Changes:

- Removed product SRT, VTT, JSON, raw-segments, diarization-turns, and diagnostics download endpoints from the current API surface.
- Export now writes only `transcript.txt`; raw storage writes only `raw_asr.txt`.
- Frontend completed-job actions now show only TXT and RAW.
- Text-only postprocessing no longer alternates unknown speakers by question/answer heuristics by default. Without acoustic diarization or explicit safe speaker labels, it keeps one numbered speaker instead of inventing a speaker structure.
- Updated tests and docs for the current product contract: improved TXT plus separate raw ASR TXT.

Production note:

- This fixes false confidence, not speaker diarization accuracy by itself. Correct "who said each word" still depends on working acoustic diarization with expected speaker count and word-level ASR timestamps.

Follow-up:

- Added production-quality upload controls: required `expected_speakers`, `asr_quality`, `audio_profile`, participant names, and custom vocabulary.
- Added `/api/diarization/readiness` so missing HF token / cache problems are visible before a job is trusted.
- Pinned Hugging Face cache to `backend/data/huggingface` and added a writable-cache check to avoid Windows user-profile ACL failures.
- Added speech audio preprocessing profile with high-pass, low-pass, and loudness normalization, plus preprocess diagnostics in job warnings.
- Accurate ASR mode now prefers full `large-v3`; if that model is unavailable, the backend falls back to the default model and records an explicit warning instead of silently failing.
- Diarization now records a summary of acoustic speaker clusters, turn count, unassigned words, and speaker switches inside ASR segments.

## Session 11: verbatim-first transcript accuracy and Windows pytest ACL fix

Date: 2026-05-21

Request: review the project as an ASR/diarization production engineer, fix backend/quality issues, and finally fix the Windows ACL pytest failure. User also clarified that recent output had strong text distortion and the priority is maximum accuracy: every spoken word should remain as close as possible to ASR output and be assigned to the correct speaker.

Changes:

- Added `pytest.ini` so `python -m pytest tests` ignores ACL-poisoned cache/temp directories under `tests/` and disables pytest cache provider by default.
- Added root `conftest.py` with a project-local `tmp_path` fixture, avoiding broken Windows `%TEMP%` / pytest cache folders that caused `PermissionError: [WinError 5]`.
- Fixed the API smoke fake transcriber signature to match the production transcriber contract with `expected_speakers`.
- Changed production transcript defaults to verbatim-first: `PRESERVE_ASR_WORDS=1` and `TEXT_POLISH_PROVIDER=off`.
- `FasterWhisperEngine` now passes `preserve_asr_words` into postprocessing, so the default backend path does not rewrite ASR words into normalized domain terms.
- `postprocess_transcript(..., preserve_words=True)` still assigns speaker labels and can detect explicit speaker names, but it does not rewrite segment text or strip explicit labels from the displayed words.
- Added a regression test proving verbatim output can preserve words such as spoken `эй пи ай` instead of silently normalizing them to `API`.
- Updated README and project prompt to state that hidden LLM/local rewriting is a transcription quality defect unless explicitly enabled as a cleaned/polished path.

Checks:

```powershell
python -m pytest tests
npm.cmd run build
```

Result:

```text
45 passed
frontend build passed
```

Known limitations:

- This does not prove WER/CER or diarization accuracy on real audio; that still requires reference transcripts and speaker annotations.
- FastAPI still emits `on_event` deprecation warnings; migrate to lifespan later.
- For maximum speaker fidelity, users should provide expected speaker count before upload. Participant-name mapping should be a future explicit UI metadata field, not guessed from text.

Follow-up in the same session:

- Added immutable raw ASR artifacts for every completed job: `raw_asr.txt` and `raw_asr_segments.json`, written immediately after faster-whisper and before diarization/postprocessing.
- Added backend download endpoints `/api/jobs/{job_id}/download/raw-txt` and `/api/jobs/{job_id}/download/raw-segments`.
- Added RAW download in the frontend completed-job actions.
- SQLite now migrates `raw_text_path` and `raw_segments_json_path`.
- Smoke test now verifies raw TXT and raw segments downloads.

## Session 10: backend stabilization, ASR operability metadata, and speaker-label guardrails

Date: 2026-05-21

Request: stabilize the backend and improve ASR quality using `docs/project-prompt.md`, `docs/chat-history.md`, and the previous evaluation findings. Main production risk: bad speaker structure can look confident, especially when text postprocessing turns garbage prefixes into speaker labels.

Changes:

- Added SQLite job metadata columns with migration-on-start: `diarization_status`, `speaker_count`, `warnings_json`, and `timings_json`.
- `FasterWhisperEngine.transcribe()` now returns `TranscriptionResult` with text, segments, diarization status, speaker count, warnings, and timings while preserving old tuple unpack compatibility.
- Job processing now records timings for preprocess, ASR, diarization, text polish, export, and total job time where available.
- Job API responses now expose parsed `warnings` and `timings` instead of hiding JSON strings.
- UI now shows compact diagnostics for completed jobs: diarization status, speaker count, total time, ASR time, diarization time, and warning count.
- Upload flow now accepts an expected speaker count. For a known 3-speaker recording, the backend passes `num_speakers=3` into pyannote rather than relying on auto-detection between min/max bounds.
- Text-only speaker extraction now rejects obvious garbage labels such as `По:`, `Кто:`, and `Pmi:` so they remain transcript text instead of becoming false speaker names.
- Added an HTTP smoke test covering upload, polling completion, `/result`, and TXT/SRT/VTT downloads with fake ASR/preprocess.
- Added regression coverage for diarization failure visibility and persisted operability metadata.

Checks:

```powershell
python -m py_compile backend\app\db.py backend\app\services.py backend\app\transcriber.py backend\app\postprocess.py
python -m pytest tests -p no:cacheprovider --basetemp=backend\data\pytest-tmp-full-stabilize3
npm.cmd run build
```

Result:

```text
py_compile passed
40 passed
frontend build passed
```

Known limitations:

- Full pytest still needs to run outside the Codex sandbox on this Windows host because pytest temp/cache cleanup can hit `PermissionError: [WinError 5]`.
- The test run emits FastAPI `on_event` deprecation warnings; migrate to lifespan handlers in a later infra cleanup.
- These changes improve honesty and operability of ASR/diarization results, but WER/CER still require human reference transcripts.

## Сессия 9: стабилизация ASR и diarization mapping

Дата: 2026-05-20

Запрос: пользователь указал на плохое разделение спикеров, смешивание реплик разных людей, слабое определение количества голосов, ошибки по доменным аббревиатурам вроде `EADR`, и попросил найти максимально простое решение в условиях почти исчерпанного лимита разработки.

Сделано:

- В `backend/app/transcriber.py` faster-whisper теперь запускается с `word_timestamps=True`, `condition_on_previous_text=False`, `initial_prompt` и `hotwords`.
- В `backend/app/settings.py` добавлены `WHISPER_INITIAL_PROMPT`, `WHISPER_HOTWORDS` и дефолтный ASR glossary с `EADR`, `ADR`, `IDR`, `DR`, `RFC`, `Jira`, `AirPoint`, `GSM`, `CM`, `TMH`, `QA` и частыми IT/Agile терминами.
- В `backend/app/diarization.py` исправлен главный failure mode: если один ASR-сегмент содержит слова нескольких спикеров, он режется по word timestamps и pyannote speaker turns. Старый maximum-overlap на весь сегмент оставлен только fallback.
- В `backend/app/transcriber.py` ошибки diarization больше не проглатываются молча: они логируются через backend logger, но job не падает.
- В `backend/app/exports.py` `TranscriptSegment` расширен optional `words`, чтобы word-level данные доходили до diarization layer.
- В `tests/test_diarization.py` добавлен регрессионный тест на split одного ASR-сегмента на две реплики по словам.
- В `tests/test_transcriber_fallback.py` добавлен тест, что transcriber реально передает `word_timestamps`, `condition_on_previous_text`, `initial_prompt`, `hotwords`.
- README и `docs/project-prompt.md` дополнены правилами ASR quality path.
- После уточнения пользователя исправлен недоделанный дефолт: diarization больше не ручной optional flag. `DIARIZATION_ENABLED` по умолчанию `1`, `DIARIZATION_MIN_SPEAKERS=2`, `DIARIZATION_MAX_SPEAKERS=4`, а `pyannote.audio` перенесен в основной `requirements.txt`.

Проверки:

```powershell
python -m py_compile backend\app\exports.py backend\app\settings.py backend\app\transcriber.py backend\app\services.py backend\app\diarization.py
python -m pytest tests\test_diarization.py tests\test_transcriber_fallback.py tests\test_postprocess.py tests\test_text_polish.py -p no:cacheprovider
python -m pytest tests\test_db.py tests\test_exports.py tests\test_postprocess.py tests\test_text_polish.py tests\test_diarization.py tests\test_transcriber_fallback.py -p no:cacheprovider
```

Результат:

```text
py_compile passed
29 passed
34 passed
```

Ограничения:

- Реальный pyannote-прогон на новых настройках в этой сессии не выполнялся; для него нужны установленный `requirements-diarization.txt`, `DIARIZATION_ENABLED=1`, `HF_TOKEN` и доступ к модели.
- Команда `pytest tests` без явного списка файлов падает из-за мусорных ACL-закрытых каталогов `tests/pytest-cache-files-*`; это отдельный infra-долг, а не регрессия ASR.
- Текстовый слой не может надежно определить имена людей из воздуха; имена появляются только из явных фраз/контекста. Для устойчивого name mapping нужен отдельный metadata/UI layer со списком участников встречи.

Дополнение по настройке Hugging Face:

- Пользователь предоставил HF token; токен сохранен в пользовательскую переменную окружения Windows `HF_TOKEN`, сам токен в репозиторий не записывался.
- Также сохранены пользовательские env: `DIARIZATION_ENABLED=1`, `DIARIZATION_MIN_SPEAKERS=2`, `DIARIZATION_MAX_SPEAKERS=4`, `HF_HOME=backend/data/huggingface`, `HUGGINGFACE_HUB_CACHE=backend/data/huggingface/hub`, `HF_HUB_DISABLE_XET=1`.
- Проверка `HfApi.whoami` прошла, аккаунт распознан; доступ к `pyannote/speaker-diarization-3.1` подтвержден.
- Реальная загрузка pipeline вне sandbox дошла до gated dependency `pyannote/segmentation-3.0` и получила `403`; нужно принять условия доступа на странице `https://huggingface.co/pyannote/segmentation-3.0`.
- Добавлен `backend/app/hf_env.py`, который удаляет мертвый proxy `127.0.0.1:9` перед Hugging Face вызовами.
- `PyannoteDiarizationEngine.diarize()` теперь загружает WAV через `torchaudio.load()` и передает pyannote preloaded waveform, чтобы не зависеть от сломанного `torchcodec` decoder path.

Дата: 2026-05-20

Этот файл фиксирует рабочую историю проекта локального web-сервиса для транскрибации аудио в текст. Он нужен как контекст для следующих сессий разработки: что было сделано, какие решения приняты, какие проверки прошли и какие проблемы уже встречались.

## Сессия 1: MVP приложения

Пользователь попросил выступить в роли Senior Fullstack Developer, Solution Architect и Tech Lead и создать MVP локального web-сервиса для транскрибации аудио в текст.

Исходный контекст:

- Целевая машина: Ryzen 5800X, 32 GB RAM, RTX 5070 Ti 16 GB VRAM, Windows 11 Pro.
- Средняя длина аудио: около 60 минут.
- Язык: русский.
- Режим: только загрузка файлов, без real-time transcription.
- Нагрузка: 1-3 файла в день.
- Backend: Python + FastAPI.
- ASR: faster-whisper.
- GPU: CUDA.
- Model: `large-v3-turbo`.
- `compute_type`: `float16`.
- fallback `compute_type`: `int8_float16`.
- Frontend: React + Vite.
- Storage: локальная папка `backend/data`.
- DB: SQLite.
- Audio preprocessing: ffmpeg.
- Export: TXT, SRT, VTT.
- Queue: простая in-process background queue.

Ограничения:

- Не усложнять MVP микросервисами.
- Не добавлять real-time transcription.
- Не использовать облачные API без отдельного решения.
- Не делать авторизацию на первом этапе.
- Не добавлять diarization в MVP без отдельного решения.
- Все решения должны быть пригодны для локального запуска на Windows 11 с NVIDIA GPU.

### Реализованная структура

```text
backend/app/
  audio.py        # ffmpeg preprocessing
  db.py           # SQLite metadata
  exports.py      # txt/srt/vtt rendering
  main.py         # FastAPI endpoints
  services.py     # upload storage and background queue
  settings.py     # env settings
  transcriber.py  # faster-whisper integration

frontend/
  src/main.tsx    # upload/status/result UI

tests/
  test_db.py
  test_exports.py

docs/
  chat-history.md
```

### Реализованный backend

- `POST /api/upload`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/result`
- `GET /api/jobs/{job_id}/download/txt`
- `GET /api/jobs/{job_id}/download/srt`
- `GET /api/jobs/{job_id}/download/vtt`
- Локальное сохранение оригинального файла.
- ffmpeg preprocessing в mono 16 kHz WAV.
- Background transcription job.
- faster-whisper с `language="ru"`.
- SQLite-история задач.
- Статусы `queued`, `processing`, `completed`, `failed`.
- Сохранение ошибок обработки.
- TXT/SRT/VTT export.
- Startup recovery: queued jobs возвращаются в очередь, interrupted processing jobs помечаются как failed.

### Реализованный frontend

- React + Vite UI.
- Загрузка файла.
- История задач.
- Polling статуса.
- Просмотр результата.
- Ссылки на скачивание TXT/SRT/VTT.

### Документация и тесты

- `README.md` с запуском на Windows 11.
- `requirements.txt`.
- `.gitignore`.
- Базовые тесты для SQLite и exports.

### Проверки первой сессии

```powershell
python -m pytest
```

Результат:

```text
5 passed
```

```powershell
npm.cmd run build
```

Результат: успешно.

Также проверялось:

- backend health endpoint `/api/health` возвращал `ok`;
- frontend открывался на `http://127.0.0.1:5173`;
- console errors во frontend не было.

### Коммиты первой сессии

```text
9025b0a Add FastAPI transcription backend
e9ccf2b Add React transcription UI
2da2aac Add docs tests and startup recovery
135de6b Ignore local runtime logs
fe77ee9 Add chat history notes
```

## Сессия 2: реальный GPU-прогон аудио и CUDA runtime

Пользователь попросил проверить, что приложение реально работает, прогнать файл:

```text
D:\tg\ADR_установочная_встреча_с_Натальным.m4a
```

Также было условие: если транскрибация идет дольше 15-20 минут, нужно понять причину торможения и оптимизировать. В конце нужно было дать директорию, где лежит DOCX-файл с полученным текстом.

Дополнительная инструкция пользователя после прерывания установки:

- обязательно сообщать, если процесс зависает;
- явно выводить текущий процесс и статус операции;
- объяснять причины долгих операций, например при установке NVIDIA CUDA runtime.

### Начальное состояние

Проверен git status:

```text
## main...origin/main
```

Рабочее дерево было чистым.

Проверен файл:

```text
D:\tg\ADR_установочная_встреча_с_Натальным.m4a
```

Размер файла:

```text
127042990 bytes
```

Длительность через ffprobe:

```text
5143.786667 seconds
```

Это примерно 85 минут 44 секунды.

### Предварительные проверки

Frontend build:

```powershell
npm.cmd run build
```

Результат: успешно.

Первый запуск pytest без повышенных прав упал из-за Windows ACL/sandbox на временных каталогах pytest:

```text
PermissionError: [WinError 5] Отказано в доступе
```

После запуска с локальным `basetemp` и вне sandbox:

```powershell
python -m pytest --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache
```

Результат:

```text
5 passed
```

### Проверка окружения GPU

Проверено:

- `nvidia-smi` видит RTX 5070 Ti.
- Driver Version: `596.49`.
- CUDA Version по драйверу: `13.2`.
- GPU memory: `16303 MiB`.
- `ffmpeg` установлен и доступен.
- `faster-whisper` version: `1.2.1`.
- `ctranslate2` version: `4.7.1`.

### Первый реальный прогон

Для диагностики был создан временный локальный runner в `backend/data`, который использовал те же модули приложения:

- `backend.app.audio.preprocess_audio`
- `backend.app.transcriber.FasterWhisperEngine`
- `backend.app.exports.write_exports`
- `backend.app.db.Database`

Эта папка игнорируется git через `.gitignore`, поэтому runner и результаты не попали в репозиторий.

Первый запуск:

- ffmpeg preprocessing прошел за `2.6` секунды;
- транскрибация не стартовала из-за обращения к Hugging Face через proxy `127.0.0.1:9`.

Ошибка:

```text
Unable to connect to proxy 127.0.0.1:9
```

Проверка cache показала, что модель уже есть локально:

```text
C:\Users\NorthRagnarr\.cache\huggingface\hub\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```

После этого был использован offline-режим:

```powershell
$env:HF_HUB_OFFLINE='1'
$env:HF_HUB_DISABLE_XET='1'
```

### Блокер CUDA runtime

Следующий запуск дошел до загрузки модели, но упал:

```text
Library cublas64_12.dll is not found or cannot be loaded
```

Диагностика показала:

- `cublas64_12.dll` не найден в PATH;
- CUDA Toolkit в `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA` не найден;
- Python packages `nvidia-cublas-cu12` и `nvidia-cudnn-cu12` отсутствовали.

Была запущена установка:

```powershell
python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Пользователь прервал turn и уточнил, что нужно явно сообщать текущий статус долгих операций. После проверки процессов выяснилось:

- установка продолжала идти в фоне;
- PID установки: `23932`;
- команда: `python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`;
- backend uvicorn тоже был запущен отдельно на `127.0.0.1:8000`.

Сетевые соединения PID `23932`:

```text
151.101.0.223:443
151.101.64.223:443
```

Вывод: процесс не завис, он скачивал крупные CUDA/cuDNN wheels через CDN PyPI/Fastly. После ожидания установка завершилась успешно.

Установленные пакеты:

```text
nvidia-cublas-cu12 12.9.2.10
nvidia-cudnn-cu12 9.22.0.52
```

Найденные DLL:

```text
C:\Users\NorthRagnarr\AppData\Local\Programs\Python\Python312\Lib\site-packages\nvidia\cublas\bin\cublas64_12.dll
C:\Users\NorthRagnarr\AppData\Local\Programs\Python\Python312\Lib\site-packages\nvidia\cudnn\bin\cudnn64_9.dll
```

### Успешная реальная транскрибация

После добавления CUDA DLL directories в `PATH` и включения offline-режима реальный прогон завершился успешно.

Job:

```text
real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27
```

Итог:

```text
preprocess_seconds: 2.57
transcribe_seconds: 168.0
export_seconds: 0.02
segments: 3488
text_chars: 59324
```

Для аудио длительностью 85 минут 44 секунды ASR заняла около 2 минут 48 секунд, то есть проблемы с длительной обработкой на 15-20 минут не обнаружено. Основное время до успешного прогона уходило не на транскрибацию, а на исправление окружения CUDA runtime.

Файлы результата:

```text
backend\data\results\real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27\transcript.txt
backend\data\results\real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27\transcript.srt
backend\data\results\real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27\transcript.vtt
```

### DOCX с результатом

С помощью document workflow был создан DOCX:

```text
C:\Users\NorthRagnarr\Documents\transcrib-app\backend\data\results\real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27\ADR_transcript.docx
```

DOCX содержит:

- заголовок;
- техническую справку по прогону;
- текст с таймкодами;
- сплошной текст.

Структурная проверка через `python-docx`:

```text
paragraphs: 3501
chars: 227050
```

Визуальный render DOCX через LibreOffice выполнить не удалось:

- сначала мешали Windows temp/ACL ограничения;
- после запуска вне sandbox renderer дошел дальше, но `soffice` не найден;
- вывод: DOCX создан и структурно валиден, но PNG/PDF visual QA невозможен без установленного LibreOffice.

### Исправление backend для Windows CUDA runtime

Чтобы приложение работало не только при ручном `$env:Path`, в `backend/app/transcriber.py` добавлена функция автоподхвата CUDA DLL directories на Windows:

- ищет `nvidia\cublas\bin` в Python `site-packages`;
- ищет `nvidia\cudnn\bin` в Python `site-packages`;
- добавляет найденные каталоги через `os.add_dll_directory`;
- делает это перед загрузкой `WhisperModel`.

В `requirements.txt` добавлены Windows-only зависимости:

```text
nvidia-cublas-cu12==12.9.2.10; platform_system == "Windows"
nvidia-cudnn-cu12==9.22.0.52; platform_system == "Windows"
```

Проверка после фикса:

```powershell
$env:HF_HUB_OFFLINE='1'
$env:HF_HUB_DISABLE_XET='1'
python -c "from backend.app.settings import Settings; from backend.app.transcriber import FasterWhisperEngine; s=Settings(); e=FasterWhisperEngine(s.whisper_model,s.whisper_device,s.whisper_compute_type,s.whisper_fallback_compute_type); e._load_model(); print('model_loaded')"
```

Результат:

```text
model_loaded
```

Это подтвердило, что модель загружается без ручного изменения `PATH`.

### Проверки после исправления

```powershell
python -m pytest --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache
```

Результат:

```text
5 passed
```

```powershell
npm.cmd run build
```

Результат: успешно.

Backend API:

```text
GET http://127.0.0.1:8000/api/health -> {"status":"ok"}
GET /api/jobs/real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27 -> status completed
```

Backend был перезапущен, чтобы подхватить исправленный код.

Новый uvicorn PID:

```text
34792
```

### Коммит и push второй сессии

Создан commit:

```text
a4afef7 Add Windows CUDA runtime support
```

Изменения:

- `backend/app/transcriber.py`
- `requirements.txt`

Push:

```text
fe77ee9..a4afef7 main -> main
```

После push:

```text
## main...origin/main
```

## Сессия 3: сохранение истории чата в репозитории

Пользователь попросил:

```text
сохрани историю этого чата со всеми изменениями в виде доки на гитхабе
```

Действие:

- обновлен `docs/chat-history.md`;
- история переписана нормальным UTF-8 Markdown;
- добавлены сведения о MVP, реальном GPU-прогоне, диагностике CUDA runtime, DOCX-результате, проверках, commit и push.

Этот файл является проектной документацией и должен быть сохранен в GitHub отдельным commit.

## Сессия 4: постобработка транскрипта по спикерам и читаемым абзацам

Дата: 2026-05-20

Пользователь попросил:

```text
1. Разделить в процессе обработки текст по спикерам, проанализировав из контекста имя спикера, если имя не понятно, назвать просто Спикер (и номер по порядку)
2. Разделять по правилам используемого языка предложения и абзацы, чтобы текст не был монолитом, и стал читаемым
```

Контекст:

- В MVP ранее не было полноценной diarization.
- Решение должно оставаться локальным, без облачных API.
- Нужно было сделать небольшой проверяемый шаг, не переписывая ASR pipeline.

Сделано:

- Добавлен модуль `backend/app/postprocess.py`.
- `FasterWhisperEngine.transcribe()` теперь после получения raw faster-whisper сегментов вызывает `postprocess_transcript()`.
- TXT результат больше не собирается монолитной строкой; он формируется блоками по спикерам.
- Для явного определения имени поддержаны текстовые маркеры `Наталья: текст`, `Наталья - текст`, `Наталья — текст`, а также фразы самопредставления вроде `меня зовут ...`.
- Если имя не определено, используется fallback `Спикер 1`, `Спикер 2`.
- Простая смена неизвестного спикера поддержана для короткого question/answer сценария: если предыдущая реплика заканчивается `?`, следующая близкая по времени реплика считается ответом другого спикера.
- Разбиение на предложения выполняется локальным regex-правилом по знакам `.`, `!`, `?`, `…` с защитой частых русских сокращений (`т.е.`, `т.к.`, `т.д.`, `т.п.`).
- Абзацы ограничены примерно 3 предложениями или 520 символами.
- В `backend/app/exports.py` тип сегмента расширен необязательным полем `speaker`.
- SRT/VTT теперь добавляют префикс `Спикер/Имя: текст`, если поле `speaker` есть.
- В `.gitignore` добавлен `tests/.pytest-tmp*/`, чтобы локальные временные каталоги pytest не шумели в git status.

Тесты:

```powershell
python -m py_compile backend\app\exports.py backend\app\postprocess.py backend\app\transcriber.py
python -m pytest tests --basetemp=tests\.pytest-tmp -o cache_dir=.pytest_cache
```

Результат:

```text
9 passed
```

Ограничение решения:

- Это контекстная текстовая постобработка, а не акустическая diarization по голосам.
- Если в аудио нет текстовых подсказок с именами или явных question/answer переходов, точность определения спикера ограничена.
- Для точного speaker detection по голосу нужен отдельный этап diarization.

Дополнительная инструкция пользователя:

```text
Когда пользователь просит дополнить документацию, документацию нужно дополнять, а не переписывать.
```

Действие:

- В `docs/project-prompt.md` добавлен раздел `Documentation workflow`.
- В `docs/project-prompt.md` добавлен раздел `Current transcript postprocessing behavior`.
- История текущей сессии добавлена в конец `docs/chat-history.md` без переписывания предыдущего содержания.

## Сессия 5: чистка финальных подписей и IT/Agile-аббревиатуры

Дата: 2026-05-20

Пользователь попросил использовать `docs/project-prompt.md` и `docs/chat-history.md` и доработать постобработку:

```text
1. убрать в конце конечного текста фразу "Субтитры сделал DimaTorzok" и прочие ненужные подписи не относящиеся к тексту
2. научиться и определять англоязычные аббревиатуры из сферы IT и Agile
```

Сделано:

- В `backend/app/postprocess.py` добавлена чистка хвоста транскрипта перед назначением спикеров.
- Из конца результата удаляются служебные подписи и похожие финальные артефакты: `Субтитры сделал ...`, `Subtitles by ...`, `captioning by ...`, `редактор субтитров ...`, `Спасибо за просмотр`, `Продолжение следует`.
- Чистка применяется только к последним сегментам или к хвосту последнего полезного сегмента, чтобы не удалять похожие фразы из середины содержательного текста.
- Добавлена нормализация частых англоязычных IT/Agile-аббревиатур и русских фонетических записей: `эй пи ай`/`api` -> `API`, `ю ай` -> `UI`, `ю икс` -> `UX`, `эм ви пи` -> `MVP`, `си ай си ди`/`ci/cd` -> `CI/CD`, `кью эй` -> `QA`, `пи ар` -> `PR`, `эс кью эл` -> `SQL`, `джей сон` -> `JSON`, `о кей ар` -> `OKR`, `кей пи ай` -> `KPI`, а также ряд технических сокращений вроде `HTTP`, `REST`, `SDK`, `CLI`, `DB`, `JWT`, `RBAC`, `CPU`, `GPU`, `RAM`.
- Разбиение на предложения теперь защищает англоязычные сокращения с точками вроде `A. P. I.`, чтобы они не дробили абзацы.
- В `tests/test_postprocess.py` добавлены регрессионные тесты на удаление финальных подписей, нормализацию IT/Agile-аббревиатур и защиту dotted abbreviations.
- В `docs/project-prompt.md` дополнен раздел `Current transcript postprocessing behavior`.

Проверки:

```powershell
python -m py_compile backend\app\postprocess.py tests\test_postprocess.py
python -m pytest tests\test_postprocess.py --basetemp=tests\.pytest-tmp -o cache_dir=tests\.pytest-cache
python -m pytest tests\test_db.py tests\test_exports.py tests\test_postprocess.py --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache
```

Результат:

```text
py_compile passed
tests/test_postprocess.py: 9 passed
all explicit tests: 14 passed
```

Ограничение:

- Запуск pytest внутри sandbox снова упирался в Windows ACL на временных каталогах pytest. Полный явный прогон тестовых файлов выполнен вне sandbox с `basetemp` и `cache_dir` внутри `backend\data`.

### Уточнение по пункту 2

После уточнения пользователя:

```text
теперь реализуй пункт 2. надо чтобы англоязычные аббревиатуры определялись и записывались правильно
```

Сделано:

- Нормализация IT/Agile-аббревиатур расширена из простого списка замен в полноценный локальный словарь written- и spoken-форм.
- Spoken-формы распознают типичные русские транскрипции английских букв после ASR: `эй пи ай`, `ю ай`, `ю икс`, `эм ви пи`, `си ай си ди`, `ди о ди`, `дабл ю ай пи`, `эс кью эл`, `джей сон`, `эйч ти ти пи эс`, `джей эс`, `ти эс`, `си эс эс`, `эй ай`, `эл эл эм`, `эн эл пи`, `о си ар`, `эй эс ар`, `и ти эл` и другие.
- Добавлены IT/Agile сокращения: `API`, `UI`, `UX`, `MVP`, `QA`, `CI/CD`, `PR`, `DoD`, `DoR`, `WIP`, `OKR`, `KPI`, `SLA`, `SLO`, `SLI`, `SQL`, `JSON`, `XML`, `YAML`, `HTTP`, `HTTPS`, `HTML`, `CSS`, `JS`, `TS`, `REST`, `CRUD`, `SDK`, `CLI`, `IDE`, `DB`, `DNS`, `URL`, `URI`, `UUID`, `ID`, `IP`, `OAuth`, `SSO`, `JWT`, `RBAC`, `ACL`, `AI`, `ML`, `LLM`, `NLP`, `OCR`, `ASR`, `STT`, `TTS`, `ETL`, `BI`, `CRM`, `ERP`, `CMS`, `CDN`, `VPN`, `SSH`, `FTP`, `SFTP`, `SSL`, `TLS`, `TCP`, `UDP`, `PDF`, `CSV`, `XLSX`, `DOCX`.
- Правила spoken-замен теперь обрабатываются от более длинных сокращений к коротким, чтобы `си ди эн` превращалось в `CDN`, а не в `CD эн`.
- Разделители внутри spoken-аббревиатур ограничены пробелом/дефисом/слэшем, чтобы правило не склеивало слова через запятую и не давало ложные срабатывания.
- Добавлены тесты на длинные spoken-аббревиатуры, приоритет длинных замен и AI/data-сокращения.

Проверки:

```powershell
python -m py_compile backend\app\postprocess.py tests\test_postprocess.py
python -m pytest tests\test_postprocess.py -p no:cacheprovider --basetemp=backend\data\pytest-tmp-postprocess2
python -m pytest tests\test_db.py tests\test_exports.py tests\test_postprocess.py --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache
```

Результат:

```text
tests/test_postprocess.py: 12 passed
all explicit tests: 17 passed
```

## Сессия 6: облачная правка текста с fallback на локальные правила

Дата: 2026-05-20

Пользователь попросил добавить следующую фичу:

```text
необходимо использовать облачные лучшие решения для анализа и приведение текста в подобаюзее состояние.
используем для определения праильности написания слов и аббревиатур, как русских, так и английских.
если облачные сервисы не доступны, тогда это надо сделать локально
```

Затем пользователь уточнил, что OpenAI может быть недоступен и нужно добавить провайдеров по приоритету:

```text
deepseek, qwen, grok, gigachad, yandexgpt, или другие более специализированные сервисы
```

Сделано:

- Добавлен модуль `backend/app/text_polish.py`.
- После локальной постобработки и перед экспортом TXT/SRT/VTT в `backend/app/services.py` теперь вызывается `polish_transcript()`.
- Добавлены настройки в `backend/app/settings.py`: `TEXT_POLISH_PROVIDER`, `TEXT_POLISH_PROVIDERS`, `TEXT_POLISH_MODEL`, `TEXT_POLISH_TIMEOUT_SECONDS`, `OPENAI_API_KEY`.
- Режим по умолчанию `TEXT_POLISH_PROVIDER=auto`.
- Provider-chain в `auto` режиме: `openai`, `deepseek`, `qwen`, `grok`, `gigachat`, `yandexgpt`, `mistral`, `groq`, затем локальные правила.
- Приоритет можно переопределить через `TEXT_POLISH_PROVIDERS`, например `deepseek,qwen,openai,yandexgpt`.
- Поддержаны alias: `xai` -> `grok`, `gigachad`/`giga` -> `gigachat`, `dashscope` -> `qwen`, `yandex` -> `yandexgpt`.
- Для OpenAI-compatible провайдеров используется `/chat/completions`: OpenAI, DeepSeek, Qwen/DashScope compatible mode, Grok/xAI, Mistral, Groq.
- Для GigaChat и YandexGPT добавлены отдельные адаптеры.
- Если ключа нет, провайдер недоступен, возвращает ошибку или отдает невалидный JSON, обработка переходит к следующему провайдеру. Если облака не сработали, используется локальная нормализация `normalize_domain_terms()`.
- Cloud prompt просит исправлять орфографию, пунктуацию, регистр, русские и английские слова, IT/Agile-аббревиатуры и названия технологий без пересказа, сокращения, добавления фактов или изменения смысла.
- Таймкоды и спикеры сохраняются, облако исправляет только `text` внутри сегментов.
- README обновлен: описана опциональная облачная правка текста, env-переменные и локальный режим.
- `docs/project-prompt.md` обновлен: прежнее ограничение “не использовать облачные API” уточнено. Облако разрешено только для опционального text polish после локального ASR и обязательно с локальным fallback.

Проверки:

```powershell
python -m py_compile backend\app\settings.py backend\app\services.py backend\app\text_polish.py tests\test_text_polish.py
python -m pytest tests\test_text_polish.py tests\test_postprocess.py -p no:cacheprovider --basetemp=backend\data\pytest-tmp-polish-chain
```

Результат:

```text
tests/test_text_polish.py + tests/test_postprocess.py: 19 passed
```

Ограничение:

- Полный pytest вне sandbox пользователь не разрешил. Полный явный прогон внутри sandbox дошел до выполнения тестов: `tests/test_postprocess.py` и `tests/test_text_polish.py` прошли, но `test_db.py`/`test_exports.py` снова уперлись в Windows ACL на временном каталоге pytest во время setup/cleanup. Это известная проблема окружения из предыдущих сессий.

## Сессия 7: опциональная акустическая diarization-модель

Дата: 2026-05-20

Пользователь попросил использовать `docs/project-prompt.md` и `docs/chat-history.md` и реализовать diarization-модель для обработки информации.

Сделано:

- Добавлен модуль `backend/app/diarization.py`.
- Diarization реализована как опциональный слой через `pyannote.audio`, модель по умолчанию `pyannote/speaker-diarization-3.1`.
- Добавлен `requirements-diarization.txt` с optional dependency `pyannote.audio>=3.3.0`.
- Добавлены настройки:
  - `DIARIZATION_ENABLED`
  - `DIARIZATION_MODEL`
  - `DIARIZATION_DEVICE`
  - `DIARIZATION_MIN_SPEAKERS`
  - `DIARIZATION_MAX_SPEAKERS`
  - `HF_TOKEN` / `HUGGINGFACE_TOKEN`
- Пустые `DIARIZATION_MIN_SPEAKERS` / `DIARIZATION_MAX_SPEAKERS` трактуются как unset, чтобы env без значения не ломал старт приложения.
- `FasterWhisperEngine` теперь может получать diarization engine, запускать его после faster-whisper ASR и до локальной постобработки.
- ASR-сегменты получают speaker label по максимальному временному overlap с голосовыми интервалами pyannote.
- Raw labels pyannote вроде `SPEAKER_00` маппятся в стабильные `Спикер 1`, `Спикер 2`, ...
- Если diarization выключена или модель падает/недоступна, транскрибация не падает и использует прежнюю текстовую разметку.
- `postprocess.assign_speakers()` теперь сохраняет уже проставленные diarization-метки `speaker`, но явные текстовые метки и самопредставления по-прежнему могут уточнить имя.
- Если diarization-метка вроде `Спикер 1` была уточнена явной текстовой меткой имени, последующие сегменты этого же diarization-спикера продолжают использовать найденное имя.
- `JobService` и диагностический runner `backend/data/run_real_transcription.py` подключают diarization через общую конфигурацию.
- README дополнен инструкцией по установке и env-переменным diarization.
- `docs/project-prompt.md` дополнен текущим поведением diarization.

Проверки:

```powershell
python -m py_compile backend\app\diarization.py backend\app\transcriber.py backend\app\services.py backend\app\settings.py backend\data\run_real_transcription.py tests\test_diarization.py
python -m pytest tests\test_diarization.py tests\test_postprocess.py -p no:cacheprovider --basetemp=backend\data\pytest-tmp-diarization
python -m pytest tests\test_db.py tests\test_exports.py tests\test_postprocess.py tests\test_text_polish.py tests\test_diarization.py -p no:cacheprovider --basetemp=backend\data\pytest-tmp-diarization-full
```

Результат:

```text
py_compile passed
tests/test_diarization.py + tests/test_postprocess.py: 17 passed
full explicit test set outside sandbox: 29 passed
```

Ограничения:

- Реальный pyannote-прогон не выполнялся в этой сессии: для него нужно установить optional dependency и, вероятно, указать Hugging Face token с доступом к модели.
- Первый полный pytest внутри sandbox снова уперся в известный Windows ACL `PermissionError: [WinError 5]` на pytest temp cleanup, но повторный полный прогон вне sandbox прошел успешно.

## Сессия 8: срочный hotfix CUDA fallback и проверка `.m4a` до TXT

Дата: 2026-05-20

Пользователь сообщил, что в UI при транскрибации `.m4a` получил ошибку:

```text
Library cublas64_12.dll is not found or cannot be loaded
```

Цель: срочно довести локальный MVP до рабочего состояния без изменения архитектуры, EXE, SaaS или redesign.

Сделано:

- Исправлен порядок инициализации CUDA DLL directories в `backend/app/transcriber.py`: теперь `nvidia/cublas/bin` и `nvidia/cudnn/bin` добавляются до импорта `faster_whisper.WhisperModel`.
- Для Windows дополнительно обновляется `PATH` текущего процесса на найденные CUDA/cuDNN DLL directories.
- Добавлена устойчивая цепочка загрузки модели:
  - CUDA `float16`;
  - CUDA `int8_float16`;
  - CPU `int8`.
- Если все режимы загрузки модели не сработали, backend формирует readable error с перечислением проверенных режимов.
- В `backend/app/services.py` добавлен file logging в `backend/data/logs/backend.log`; при падении job туда пишется полный traceback.
- В `backend/app/audio.py` ошибки ffmpeg теперь превращаются в понятные сообщения: ffmpeg не найден или ffmpeg не смог подготовить аудио.
- Добавлены регрессионные тесты `tests/test_transcriber_fallback.py`.
- README и `docs/project-prompt.md` обновлены командами запуска/проверки и описанием fallback.

Проверки:

```powershell
ffmpeg -version
python -m pip show nvidia-cublas-cu12 nvidia-cudnn-cu12 faster-whisper ctranslate2
python -m py_compile backend\app\audio.py backend\app\services.py backend\app\settings.py backend\app\transcriber.py tests\test_transcriber_fallback.py
python -m pytest tests\test_db.py tests\test_exports.py tests\test_postprocess.py tests\test_text_polish.py tests\test_diarization.py tests\test_transcriber_fallback.py -p no:cacheprovider --basetemp=backend\data\pytest-tmp-fallback-full
```

Результат:

```text
ffmpeg available
nvidia-cublas-cu12 12.9.2.10
nvidia-cudnn-cu12 9.22.0.52
faster-whisper 1.2.1
ctranslate2 4.7.1
py_compile passed
32 passed
```

Реальная проверка загрузки модели:

```text
cuda dll dirs added
faster_whisper import ok
cuda float16 model load ok
```

Реальная проверка `.m4a`:

- Источник: `backend/data/uploads/7a99472e-0341-491b-ad7b-b8165284b6dd.m4a`, размер `127042990` bytes.
- Проверка выполнена через FastAPI TestClient как upload flow.
- Job: `bc723b6a-e300-4177-8576-c7ab6ed65da6`.
- Статусы: `processing` -> `completed`.
- Время до completed: около `140` секунд.
- TXT chars: `57091`.
- TXT path: `backend/data/results/bc723b6a-e300-4177-8576-c7ab6ed65da6/transcript.txt`.
- `/api/jobs/{job_id}/result`: `200`, `57091` chars.
- `/api/jobs/{job_id}/download/txt`: `200`, `101109` bytes.

Backend перезапущен на `127.0.0.1:8000` с локальными env:

```powershell
HF_HUB_OFFLINE=1
HF_HUB_DISABLE_XET=1
TEXT_POLISH_PROVIDER=local
DIARIZATION_ENABLED=0
```

Health check:

```text
GET http://127.0.0.1:8000/api/health -> ok
```

## Сессия 9: stabilization ASR/diarization, UI cleanup, ETA и отмена обработки

Дата: 2026-05-21

Контекст:

- Пользователь потребовал production-grade стабилизацию backend, ASR, diarization, raw/final transcript separation, observability, тесты и UI/UX без декоративных заглушек.
- Критичные жалобы: raw download отдавал `Not Found`, speaker diarization выглядел случайным, LLM/словарь/имена могли загрязнять распознанный текст, ETA показывал нереалистичные значения, UI имел лишние пустые зоны и плохо читаемые блоки.
- Отдельный blocker: pyannote требует рабочий HF token и принятый gated access к `pyannote/speaker-diarization-3.1` и `pyannote/segmentation-3.0`; token хранится локально в `backend/data/secrets/hf_token.txt` и не должен коммититься.

Сделано:

- Добавлено игнорирование `backend/data/secrets/`, чтобы HF token не утек в GitHub.
- Backend получил readiness/diagnostics для diarization и HF cache, включая проверку writable cache и доступности pyannote pipeline.
- Raw ASR сохранен как отдельный artifact `raw_asr.txt`; `/download/raw-txt` теперь умеет отдавать raw и fallback для legacy jobs.
- Убраны ненужные пользователю export endpoints/files SRT/VTT/JSON из UI-потока; основной TXT остается финальным улучшенным текстом.
- ASR modes приведены к пользовательским режимам: fast/balanced/accurate, в UI отображаются русские названия.
- Audio profile убран из UI как ручная настройка; профиль выбирается автоматически по режиму ASR.
- Добавлена оценка производительности по локальным completed jobs и baseline, чтобы ETA не схлопывался до “1 сек” в середине ASR/diarization.
- Progress/ETA переведены на полный pipeline, а не на отдельный этап: audio preparation, ASR, diarization, text assembly, export.
- Для ASR/diarization добавлены stage floors: ASR больше не считается концом всего процесса, diarization не показывает ложные секунды до завершения.
- Убраны поля participants/custom vocabulary из UI, потому что они загрязняли текст и провоцировали вставку имен/терминов прямо в transcript.
- LLM-полировка ограничена: нельзя менять порядок, смысл и слова; разрешены только speaker/name resolver и очевидная нормализация терминов.
- Speaker count больше не обязателен в UI; pipeline допускает auto speaker count и до 20 speakers.
- Diarization строится от акустики/pyannote, а LLM используется только как финальный resolver имен/терминов, не как “слуховая” переразметка разговора.
- Добавлена защита от мусорных speaker labels и от повторного вбрасывания participant/custom vocabulary в текст.
- UI переработан точечно:
  - история получила scroll и delete button на каждой записи;
  - колонки растянуты по высоте окна без ломания исходной компоновки;
  - result textarea растянута вниз до доступной области;
  - кнопки download под заголовком и статусом;
  - статусы стали темно-красными для ошибки, зелеными для успеха, желтыми для обработки;
  - статус выбранной job в левой колонке синхронизируется с выбранным элементом истории;
  - блок помощи по режимам распознавания облегчен визуально;
  - текущий статус под названием файла получил shimmer effect во время обработки;
  - кнопка refresh оставлена, добавлен визуальный feedback.
- Добавлена кнопка `Прервать` слева от refresh.
- Backend получил `POST /api/jobs/{job_id}/cancel`.
- В jobs добавлен `cancel_requested`; queued/processing job переводится в `failed/cancelled` с `Processing was cancelled by user.`
- Worker проверяет отмену между фазами и в progress callback, чтобы отмененная job не могла потом silently стать `completed`.

Важное ограничение:

- Текущая отмена безопасная/cooperative. Она мгновенно меняет состояние job и останавливает pipeline на ближайшей проверке или границе фазы. Она не убивает принудительно CUDA/pyannote/faster-whisper внутри синхронного thread.
- Для настоящего hard cancel посреди GPU/pyannote inference нужен следующий архитектурный шаг: запуск каждой job в отдельном subprocess/worker process и termination этого процесса.

Проверки:

```powershell
python -m pytest tests/test_api_smoke.py
npm run build
```

Результат:

```text
tests/test_api_smoke.py: 11 passed
frontend build: passed
backend restarted on 127.0.0.1:8000
frontend running on 127.0.0.1:5173
```
