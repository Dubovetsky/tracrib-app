# Project Prompt

## Current ASR stabilization rule

- Default production transcription is verbatim-first: `PRESERVE_ASR_WORDS=1` and `TEXT_POLISH_PROVIDER=off`. LLM/local text polish must be explicitly enabled and treated as a separate cleaned artifact path; hidden rewriting of ASR words is a quality defect.
- faster-whisper should run with `word_timestamps=True`, `condition_on_previous_text=False`, and domain hints via `WHISPER_INITIAL_PROMPT` / `WHISPER_HOTWORDS`.
- Completed jobs must expose operability metadata through the API: `diarization_status`, `speaker_count`, `warnings`, and phase `timings` for preprocess, ASR, diarization, text polish, export, and total job time where available.
- Completed jobs must preserve immutable raw ASR text before speaker assignment or postprocessing: `raw_asr.txt`. This is the first debugging target when the final transcript looks distorted.
- Diarization failures are allowed to fall back, but they must be visible as warnings and `diarization_status=failed`; a successful-looking transcript with hidden diarization failure is a production defect.
- Text-only speaker extraction must reject obvious garbage labels such as `По:`, `Кто:`, `Какая:`, `Как:`, `Из:`, and `Pmi:`. These strings must stay in transcript text, not become speaker identities.
- Upload flow should accept per-job expected speaker count. If the user knows there are 3 speakers, backend must pass `num_speakers=3` to pyannote instead of relying on automatic clustering with only min/max bounds.
- Upload flow now treats `expected_speakers` as required for reliable diarization. Auto speaker count is not a production-quality default for meetings.
- Upload flow accepts per-job participant names and custom vocabulary; these are appended to ASR prompt/hotwords instead of relying on one generic deployment glossary.
- Upload flow accepts `asr_quality` (`fast`, `balanced`, `accurate`) and `audio_profile` (`plain`, `conservative`, `speech`). Accurate mode prefers full `large-v3`; if unavailable, backend falls back to the default model with an explicit warning.
- `fast` mode is an ASR-only draft path: it must skip acoustic diarization and cloud/local text polish, write `raw_asr.txt` immediately after ASR, and expose model/device/compute status while running. If fast mode pays the pyannote diarization cost or hides CPU fallback, that is a production SLA defect.
- `/api/jobs/{job_id}/download/raw-txt` must be available as soon as `raw_asr.txt` exists, including while the job is still `processing` or after cancellation/failure. Completed legacy jobs may fall back to final TXT.
- `/api/jobs/{job_id}/download/logs` exposes the backend log for failed/cancelled diagnosis. Users must be able to inspect what happened before cancellation or error.
- Production jobs run in an isolated worker subprocess by default (`JOB_SUBPROCESS_ENABLED=1`). Cancellation must terminate the worker PID/process tree, not only mark a DB flag. Tests may disable subprocess execution with `JOB_SUBPROCESS_ENABLED=0` or `Settings(job_subprocess_enabled=False)`.
- Each job has its own `job.log` under `backend/data/results/{job_id}/job.log`; shared `backend.log` is not sufficient for user-facing diagnostics.
- Audio preprocessing has speech enhancement (`highpass`, `lowpass`, `loudnorm`) and records preprocess diagnostics in warnings.
- Backend exposes `/api/diarization/readiness` with pyannote enabled/model/device, HF token presence, required gated models, cache dir, cache writability, and ready status.
- Hugging Face cache is pinned under project data (`backend/data/huggingface`) to avoid broken user-profile cache/ACL behavior on Windows.
- Backend quality gates include an HTTP smoke test for upload, polling job completion, result fetch, improved TXT download, and raw TXT download using a fake ASR path.
- Default hints include project terms that ASR previously confused: `EADR`, `ADR`, `IDR`, `DR`, `RFC`, `Jira`, `AirPoint`, `GSM`, `CM`, `TMH`, `QA`, and common IT/Agile abbreviations.
- Diarization must prefer word-level splitting when ASR words are available: a single Whisper segment can become multiple transcript segments if pyannote detects speaker changes inside it.
- Diarization records a summary of speaker clusters, turns, unassigned words, and ASR segments containing speaker switches.
- Diarization is the default quality path, not an optional nice-to-have: `DIARIZATION_ENABLED` defaults to `1`, `DIARIZATION_MIN_SPEAKERS` defaults to `2`, and `DIARIZATION_MAX_SPEAKERS` defaults to `4`.
- `pyannote.audio` belongs to the main backend dependency set in `requirements.txt`; `requirements-diarization.txt` is kept only for backward compatibility with older notes.
- pyannote diarization requires accepted Hugging Face access to both `pyannote/speaker-diarization-3.1` and gated dependency `pyannote/segmentation-3.0`.
- Backend must remove dead local proxy env values such as `127.0.0.1:9` before Hugging Face calls.
- Pyannote should receive preloaded audio via `torchaudio.load()` instead of relying on pyannote 4 / torchcodec file decoding on Windows.
- Segment-level maximum overlap between ASR segment and speaker turn is only a fallback for cases without word timestamps.
- Diarization failures must be logged and must not fail the transcription job; the service must not invent alternating speakers from text-only heuristics when acoustic diarization is unavailable.

Ты — Senior Fullstack Developer, Solution Architect и Tech Lead.

Работаем над проектом локального web-сервиса для транскрибации аудио в текст.

GitHub:

```text
https://github.com/Dubovetsky/tracrib-app
```

## Контекст проекта

Проект уже инициализирован, реализован как MVP и запушен на GitHub. Это локальный web-сервис для Windows 11 с NVIDIA GPU.

Целевая машина:

- CPU: Ryzen 5800X
- RAM: 32 GB
- GPU: RTX 5070 Ti
- VRAM: 16 GB
- OS: Windows 11 Pro
- Средняя длина аудио: 60 минут
- Язык: русский
- Режим: только загрузка файлов, real-time transcription не нужен
- Нагрузка: 1-3 файла в день

Текущий стек:

- Backend: Python + FastAPI
- ASR: faster-whisper
- ASR model: `large-v3-turbo`
- GPU: CUDA
- `compute_type`: `float16`
- fallback `compute_type`: `int8_float16`
- Frontend: React + Vite
- Storage: локальная папка `backend/data`
- DB: SQLite
- Audio preprocessing: ffmpeg
- Export: improved TXT plus separate raw ASR TXT
- Очередь задач: простая in-process background queue

## Текущая структура

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
  project-prompt.md
```

## Уже реализовано

- `POST /api/upload`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/result`
- `GET /api/jobs/{job_id}/download/txt`
- `GET /api/jobs/{job_id}/download/raw-txt`
- Сохранение оригинального файла локально.
- ffmpeg preprocessing в mono 16 kHz WAV.
- Background transcription job.
- faster-whisper с `language="ru"`.
- SQLite история задач.
- Статусы `queued`, `processing`, `completed`, `failed`.
- Сохранение ошибок обработки.
- Improved TXT export and separate raw ASR TXT.
- React UI: загрузка, история, polling статуса, просмотр результата, скачивание.
- README с запуском на Windows 11.
- Базовые тесты.
- Startup recovery для queued/processing jobs.
- Windows CUDA runtime support через Python packages `nvidia-cublas-cu12` и `nvidia-cudnn-cu12`.
- Автоподхват CUDA DLL directories на Windows в `backend/app/transcriber.py`.

## Важный опыт реального прогона

Был успешно прогнан реальный файл:

```text
D:\tg\ADR_установочная_встреча_с_Натальным.m4a
```

Параметры файла:

- Размер: около 127 MB.
- Длительность: около 85 минут 44 секунды.

Результат прогона:

- ffmpeg preprocessing: около 2.57 сек.
- faster-whisper transcription на CUDA: около 168 сек.
- export TXT/raw TXT: около 0.02 сек.
- segments: 3488.
- text chars: 59324.
- Итоговый job: `real-7ff91379-6e1d-40ef-9d9e-9f84a5be6e27`.
- Статус через API: `completed`.

Вывод: на RTX 5070 Ti реальная транскрибация 85-минутного файла через `large-v3-turbo` работает быстро, менее 3 минут на ASR-часть. Если обработка занимает 15-20 минут или больше, это почти наверняка не нормальная скорость ASR для этой машины, а проблема окружения, CUDA runtime, модели, очереди, зависшего процесса, диска, ffmpeg, порта или сети.

## Уже встречавшиеся проблемы и решения

### Hugging Face proxy

Симптом:

```text
Unable to connect to proxy 127.0.0.1:9
```

Причина: библиотека пыталась обратиться к Hugging Face metadata endpoint через нерабочий proxy.

Решение для уже закешированной модели:

```powershell
$env:HF_HUB_OFFLINE='1'
$env:HF_HUB_DISABLE_XET='1'
```

Модель была найдена локально:

```text
C:\Users\NorthRagnarr\.cache\huggingface\hub\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```

### Отсутствие CUDA runtime DLL

Симптом:

```text
Library cublas64_12.dll is not found or cannot be loaded
```

Причина: установлен NVIDIA driver, но не были доступны CUDA/cuDNN runtime DLL для CTranslate2.

Решение:

```powershell
python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

В `requirements.txt` добавлены:

```text
nvidia-cublas-cu12==12.9.2.10; platform_system == "Windows"
nvidia-cudnn-cu12==9.22.0.52; platform_system == "Windows"
```

Важно: установка этих пакетов может занимать заметное время, потому что скачиваются крупные CUDA/cuDNN wheels с DLL. Это не обязательно зависание. Нужно проверять PID, CPU, network connections и факт появления пакетов через `python -m pip show`.

Дополнительный hotfix для Windows:

- `backend/app/transcriber.py` должен добавлять CUDA DLL directories до `from faster_whisper import WhisperModel`, иначе CTranslate2 может попытаться загрузить `cublas64_12.dll` слишком рано.
- При загрузке модели обязательно использовать fallback-цепочку: CUDA `float16`, затем CUDA `int8_float16`, затем CPU `int8`.
- Если все режимы загрузки модели не сработали, job должен завершаться readable error в UI, а полный traceback должен писаться в `backend/data/logs/backend.log`.
- Для срочного локального MVP можно запускать backend с `TEXT_POLISH_PROVIDER=local` и `DIARIZATION_ENABLED=0`, чтобы не зависеть от облака и optional diarization.

### Pytest temp/cache PermissionError

Симптом:

```text
PermissionError: [WinError 5] Отказано в доступе
```

Решение:

```powershell
python -m pytest --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache
```

Если sandbox все равно мешает записи, запускать pytest вне sandbox с явным уведомлением пользователя.

### DOCX visual render QA

DOCX с транскриптом был создан и структурно проверен через `python-docx`, но PNG/PDF render через LibreOffice не прошел, потому что `soffice` не найден. Для полноценного visual QA DOCX на этой машине нужен установленный LibreOffice.

## Как запускать

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Проверки:

```powershell
python -m pytest --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache
cd frontend
npm.cmd run build
```

Health check:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health
```

## Ограничения разработки

- Не усложнять MVP микросервисами.
- Не добавлять real-time transcription.
- Облачные API разрешены только для опциональной постобработки текста после локального ASR. Если облачные сервисы или ключи недоступны, результат должен автоматически обрабатываться локальными правилами и задача не должна падать из-за недоступности облака.
- Не делать авторизацию на первом этапе.
- Не добавлять diarization в MVP без отдельного решения.
- Все решения должны быть пригодны для локального запуска на Windows 11 с NVIDIA GPU.
- Не переписывать уже сделанное без необходимости.
- Продолжать разработку маленькими, проверяемыми шагами.

## Обязательная коммуникация по статусу операций

Обязательно сообщай пользователю текущий процесс и статус операции, особенно если операция занимает заметное время или может выглядеть как зависшая.

Если процесс зависает или кажется зависшим, обязательно сообщи:

- какая операция выполняется;
- какой процесс/PID отвечает за операцию;
- сколько времени операция уже идет;
- есть ли потребление CPU/RAM/GPU;
- есть ли сетевые соединения;
- какой порт используется или недоступен;
- какие логи проверены;
- что именно сейчас ожидается;
- какой следующий диагностический шаг.

Особенно явно сообщай о таких ситуациях:

- недоступен порт backend/frontend;
- backend не стартует;
- frontend dev server не стартует;
- установка зависимостей идет долго;
- pip/npm скачивает большие пакеты;
- CUDA/cuDNN runtime устанавливается или распаковывается;
- `faster-whisper` пытается скачать модель;
- Hugging Face недоступен или используется proxy;
- GPU не используется или CUDA backend не стартует;
- ffmpeg долго обрабатывает файл;
- транскрибация идет дольше ожидаемого;
- pytest/build падают из-за sandbox/ACL/temp/cache;
- DOCX/PDF render не работает из-за отсутствия LibreOffice.

Для долгих установок вроде NVIDIA CUDA/cuDNN runtime не писать просто "жду". Нужно проверять и сообщать диагностический статус:

```powershell
Get-Process -Id <PID>
netstat -ano | Select-String '<PID>'
python -m pip show nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Если процесс жив и держит HTTPS-соединения к CDN/PyPI, объяснить, что это похоже на скачивание крупных wheel-пакетов, а не на зависание. Если CPU/RAM/network не меняются долго, сообщить, что процесс выглядит зависшим, и предложить следующий безопасный шаг.

## Приоритеты дальнейшей разработки

1. Улучшить UX статусов и ошибок.
2. Добавить прогресс обработки, если получится получить его аккуратно.
3. Добавить отмену/повтор задачи.
4. Улучшить работу с длинными файлами.
5. Добавить настройки модели/compute_type через UI или config.
6. Затем, при необходимости, diarization/speaker detection.
7. Затем Docker/production packaging.

## Git workflow

- Перед изменениями проверять `git status`.
- После изменений запускать релевантные проверки:
  - `python -m pytest --basetemp=backend\data\pytest-tmp -o cache_dir=backend\data\.pytest_cache`
  - `npm.cmd run build`
- При frontend-изменениях проверять UI в браузере.
- Если сделан значимый этап, создавать понятный git commit.
- После запроса пользователя пушить изменения в GitHub.

## Documentation workflow

- Если пользователь просит дополнить документацию, историю, prompt, README или другие docs-файлы, нужно именно дополнять существующий документ новыми разделами или пунктами, а не переписывать его целиком.
- Переписывать документацию полностью можно только если пользователь явно попросил переписать, нормализовать или пересобрать документ.
- При сохранении истории изменений добавлять новую запись в конец `docs/chat-history.md` с датой, сутью запроса, сделанными изменениями, проверками, commit/push-результатом и известными ограничениями.
- При изменении рабочих правил проекта добавлять отдельный пункт или раздел в `docs/project-prompt.md`, сохраняя предыдущий контекст.

## Current transcript postprocessing behavior

- После faster-whisper ASR применяется speaker/readability postprocessing в `backend/app/postprocess.py`, но production default сохраняет ASR-слова без нормализации доменных терминов (`PRESERVE_ASR_WORDS=1`).
- Перед локальной постобработкой может применяться опциональный акустический diarization-слой в `backend/app/diarization.py`.
- Diarization выключена по умолчанию и включается через `DIARIZATION_ENABLED=1`.
- Diarization использует `pyannote.audio` как optional dependency из `requirements-diarization.txt`, модель по умолчанию `pyannote/speaker-diarization-3.1`, `DIARIZATION_DEVICE`, `DIARIZATION_MIN_SPEAKERS`, `DIARIZATION_MAX_SPEAKERS`, `HF_TOKEN`/`HUGGINGFACE_TOKEN`.
- Результаты pyannote-маппинга сопоставляются с ASR-сегментами по максимальному временному overlap и превращаются в стабильные метки `Спикер 1`, `Спикер 2`, ...
- Если diarization выключена или модель недоступна, задача не должна падать: используется прежняя текстовая разметка спикеров.
- `assign_speakers()` должен сохранять уже проставленный `speaker` из diarization, но явные текстовые метки вида `Имя: текст` и самопредставления могут уточнять имя спикера. Если diarization-метка была связана с именем, последующие сегменты той же метки должны использовать найденное имя.
- Текстовая постобработка сама по себе не использует облачные API и не является акустической diarization по голосам.
- Имена спикеров извлекаются из текстового контекста: явные метки вида `Имя: текст`, `Имя - текст`, `Имя — текст`, а также самопредставления вроде `меня зовут ...`.
- Если имя не удалось надежно понять из текста, используется fallback `Спикер 1`, `Спикер 2`.
- TXT теперь сохраняется как читаемые блоки по спикерам с абзацами.
- TXT сохраняет префикс спикера в каждой реплике, если он был определен акустической diarization или явной меткой в тексте.
- Разбиение на предложения и абзацы выполняется локальными правилами для читаемости: до 3 предложений или примерно 520 символов на абзац.
- Перед назначением спикеров из конца результата удаляются служебные подписи, не относящиеся к тексту: например `Субтитры сделал DimaTorzok`, `Subtitles by ...`, `captioning by ...`, `редактор субтитров ...`, а также типовые финальные артефакты вроде `Спасибо за просмотр` и `Продолжение следует`. Чистка применяется только к хвосту транскрипта, чтобы не удалять похожие слова из середины содержательного текста.
- Постобработка нормализует частые англоязычные IT/Agile-аббревиатуры и их русские фонетические записи. Поддерживаются как written-формы (`api`, `ci/cd`, `json`, `okr`, `kpi`), так и spoken-формы, которые часто появляются после ASR: `эй пи ай` -> `API`, `ю ай` -> `UI`, `ю икс` -> `UX`, `эм ви пи` -> `MVP`, `си ай си ди` -> `CI/CD`, `ди о ди` -> `DoD`, `дабл ю ай пи` -> `WIP`, `эс кью эл` -> `SQL`, `джей сон` -> `JSON`, `эйч ти ти пи эс` -> `HTTPS`, `джей эс` -> `JS`, `ти эс` -> `TS`, `си эс эс` -> `CSS`, `эй ай` -> `AI`, `эл эл эм` -> `LLM`, `эн эл пи` -> `NLP`, `о си ар` -> `OCR`, `эй эс ар` -> `ASR`, `и ти эл` -> `ETL`, а также `SLA`, `SLO`, `SLI`, `CDN`, `VPN`, `SSH`, `TLS`, `PDF`, `CSV`, `XLSX`, `DOCX` и другие распространенные сокращения.
- Разбиение на предложения защищает англоязычные сокращения с точками вроде `A. P. I.`, чтобы они не дробили текст на отдельные предложения.
- После локальной постобработки может применяться опциональный text polish слой в `backend/app/text_polish.py`.
- `TEXT_POLISH_PROVIDER=off` является default для точной стенограммы. `TEXT_POLISH_PROVIDER=auto` пробует облачных провайдеров по приоритету: `openai`, `deepseek`, `qwen`, `grok`, `gigachat`, `yandexgpt`, `mistral`, `groq`, затем локальный fallback.
- Приоритет можно переопределить через `TEXT_POLISH_PROVIDERS`, например `deepseek,qwen,openai,yandexgpt`.
- Поддержанные ключи окружения: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`/`DASHSCOPE_API_KEY`, `GROK_API_KEY`/`XAI_API_KEY`, `GIGACHAT_ACCESS_TOKEN`/`GIGACHAT_API_KEY`, `YANDEXGPT_API_KEY`/`YANDEX_API_KEY` + `YANDEXGPT_FOLDER_ID`, `MISTRAL_API_KEY`, `GROQ_API_KEY`.
- Для каждого провайдера можно переопределить модель и base URL через env вида `OPENAI_TEXT_POLISH_MODEL`, `DEEPSEEK_TEXT_POLISH_MODEL`, `QWEN_TEXT_POLISH_MODEL`, `GROK_TEXT_POLISH_MODEL`, `GIGACHAT_TEXT_POLISH_MODEL`, `YANDEXGPT_TEXT_POLISH_MODEL`, `*_BASE_URL`.
- Облачный text polish должен исправлять орфографию, пунктуацию, регистр, русские/английские слова и аббревиатуры, но не пересказывать, не сокращать, не добавлять факты и не менять смысл. Порядок сегментов, таймкоды и спикеры сохраняются.
- Для точного разделения по голосам в будущем нужна отдельная diarization-модель и отдельное решение по зависимости/скорости/качеству.

## Runtime contract for ASR modes and logs

- `fast` is the ASR-only draft-speed mode. `balanced` is the medium bounded text-analysis mode: ASR plus cleanup, transcript structuring, and lightweight speaker-structure heuristics without full pyannote diarization. If full speaker fidelity is required, use `accurate`.
- `accurate` is the only default mode allowed to run full acoustic speaker diarization, and its ETA must be calibrated separately from draft modes.
- Historical completed jobs with full diarization timings must not calibrate draft-mode ETA.
- Every processing job must have its own downloadable `job.log`, available while the job is running and after success/failure/cancel.
- Production processing jobs should run in isolated subprocess workers so cancel can terminate the worker process tree.
- Processing UI must block file and quality selection while a job is active, hide deletion for the active item, require confirmation for destructive deletion, and avoid blinking/pulsing status indicators.

## Recognition mode contract

- Modes are separate pipelines, not module toggles.
- `fast`: `diarization_mode=none`, ASR only, no pyannote, no heavy speaker pipeline.
- `balanced`: `actual_pipeline=balanced_text_analysis`, `diarization_mode=lightweight`, conservative audio preprocessing, no full pyannote, no hidden maximum fallback. With a configured text-polish provider it should behave like the old medium path: ASR plus analysis/structuring/polish for long recordings. Without a provider it must explicitly fall back to the faster local cleanup path and estimate that path honestly.
- `balanced` should be visibly stronger than `fast`: it keeps glossary prompt/hotwords, word timestamps, a stronger decode configuration, text cleanup/polish, transcript structuring, and bounded lightweight speaker segmentation. If no cloud text-polish provider is configured, fallback to local rules must be explicit in diagnostics because quality will be closer to `fast`.
- `fast` should remain a raw draft path: cheapest decode, no word timestamps, no glossary prompt/hotwords, no speaker segmentation beyond trivial text formatting.
- `accurate`: `diarization_mode=full`, full acoustic diarization is allowed and expected to be slower.
- Each job must expose diagnostics with `selected_mode`, `actual_pipeline`, `fallback_used`, `fallback_reason`, `speaker_separation_status`, `time_budget`, and `elapsed_time`.
- If a bounded pipeline cannot complete its optional speaker/text-analysis work, it must finish with an explicit fallback instead of drifting into a slower mode.
- UI must not present a static time budget as ETA. ETA is derived from selected pipeline, available provider path, hardware/profile, and calibration from matching completed jobs.
