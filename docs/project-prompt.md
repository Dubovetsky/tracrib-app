# Project Prompt

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
- Export: TXT, SRT, VTT
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
- `GET /api/jobs/{job_id}/download/srt`
- `GET /api/jobs/{job_id}/download/vtt`
- Сохранение оригинального файла локально.
- ffmpeg preprocessing в mono 16 kHz WAV.
- Background transcription job.
- faster-whisper с `language="ru"`.
- SQLite история задач.
- Статусы `queued`, `processing`, `completed`, `failed`.
- Сохранение ошибок обработки.
- TXT/SRT/VTT export.
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
- export TXT/SRT/VTT: около 0.02 сек.
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

- После faster-whisper ASR применяется локальная постобработка в `backend/app/postprocess.py`.
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
- SRT/VTT сохраняют префикс спикера в каждой реплике, если он был определен.
- Разбиение на предложения и абзацы выполняется локальными правилами для читаемости: до 3 предложений или примерно 520 символов на абзац.
- Перед назначением спикеров из конца результата удаляются служебные подписи, не относящиеся к тексту: например `Субтитры сделал DimaTorzok`, `Subtitles by ...`, `captioning by ...`, `редактор субтитров ...`, а также типовые финальные артефакты вроде `Спасибо за просмотр` и `Продолжение следует`. Чистка применяется только к хвосту транскрипта, чтобы не удалять похожие слова из середины содержательного текста.
- Постобработка нормализует частые англоязычные IT/Agile-аббревиатуры и их русские фонетические записи. Поддерживаются как written-формы (`api`, `ci/cd`, `json`, `okr`, `kpi`), так и spoken-формы, которые часто появляются после ASR: `эй пи ай` -> `API`, `ю ай` -> `UI`, `ю икс` -> `UX`, `эм ви пи` -> `MVP`, `си ай си ди` -> `CI/CD`, `ди о ди` -> `DoD`, `дабл ю ай пи` -> `WIP`, `эс кью эл` -> `SQL`, `джей сон` -> `JSON`, `эйч ти ти пи эс` -> `HTTPS`, `джей эс` -> `JS`, `ти эс` -> `TS`, `си эс эс` -> `CSS`, `эй ай` -> `AI`, `эл эл эм` -> `LLM`, `эн эл пи` -> `NLP`, `о си ар` -> `OCR`, `эй эс ар` -> `ASR`, `и ти эл` -> `ETL`, а также `SLA`, `SLO`, `SLI`, `CDN`, `VPN`, `SSH`, `TLS`, `PDF`, `CSV`, `XLSX`, `DOCX` и другие распространенные сокращения.
- Разбиение на предложения защищает англоязычные сокращения с точками вроде `A. P. I.`, чтобы они не дробили текст на отдельные предложения.
- После локальной постобработки может применяться опциональный text polish слой в `backend/app/text_polish.py`.
- `TEXT_POLISH_PROVIDER=auto` пробует облачных провайдеров по приоритету: `openai`, `deepseek`, `qwen`, `grok`, `gigachat`, `yandexgpt`, `mistral`, `groq`, затем локальный fallback.
- Приоритет можно переопределить через `TEXT_POLISH_PROVIDERS`, например `deepseek,qwen,openai,yandexgpt`.
- Поддержанные ключи окружения: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`/`DASHSCOPE_API_KEY`, `GROK_API_KEY`/`XAI_API_KEY`, `GIGACHAT_ACCESS_TOKEN`/`GIGACHAT_API_KEY`, `YANDEXGPT_API_KEY`/`YANDEX_API_KEY` + `YANDEXGPT_FOLDER_ID`, `MISTRAL_API_KEY`, `GROQ_API_KEY`.
- Для каждого провайдера можно переопределить модель и base URL через env вида `OPENAI_TEXT_POLISH_MODEL`, `DEEPSEEK_TEXT_POLISH_MODEL`, `QWEN_TEXT_POLISH_MODEL`, `GROK_TEXT_POLISH_MODEL`, `GIGACHAT_TEXT_POLISH_MODEL`, `YANDEXGPT_TEXT_POLISH_MODEL`, `*_BASE_URL`.
- Облачный text polish должен исправлять орфографию, пунктуацию, регистр, русские/английские слова и аббревиатуры, но не пересказывать, не сокращать, не добавлять факты и не менять смысл. Порядок сегментов, таймкоды и спикеры сохраняются.
- Для точного разделения по голосам в будущем нужна отдельная diarization-модель и отдельное решение по зависимости/скорости/качеству.
