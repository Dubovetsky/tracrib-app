# Transcrib App

Локальный web-сервис для транскрибации аудио в текст на Windows 11 с NVIDIA GPU. ASR работает локально через faster-whisper; опциональная diarization-модель может разделять реплики по голосам; опциональная облачная постобработка может исправлять текст, слова и IT/Agile-аббревиатуры с fallback на локальные правила. MVP не делает real-time транскрибацию.

## Стек

- Backend: Python, FastAPI, SQLite
- ASR: faster-whisper, модель `large-v3-turbo`
- GPU: CUDA, `float16` с fallback на `int8_float16`
- Audio preprocessing: ffmpeg, mono 16 kHz WAV
- Frontend: React + Vite
- Storage: локальная папка `backend/data`
- Diarization: опциональный локальный слой `pyannote.audio` после ASR
- Text polish: локальные правила + опциональная цепочка облачных LLM-провайдеров

## Структура

```text
backend/app/
  audio.py        # ffmpeg preprocessing
  db.py           # SQLite metadata
  exports.py      # txt/srt/vtt rendering
  main.py         # FastAPI endpoints
  services.py     # upload storage and background queue
  settings.py     # local settings from env
  transcriber.py  # faster-whisper integration
  diarization.py  # optional pyannote speaker diarization
frontend/
  src/main.tsx    # upload/status/result UI
tests/            # базовые unit tests
```

## Требования

1. Windows 11 Pro.
2. Python 3.11+.
3. Node.js 20+.
4. NVIDIA driver и CUDA runtime, совместимые с faster-whisper/CTranslate2.
5. ffmpeg в `PATH`.

Проверка ffmpeg:

```powershell
ffmpeg -version
```

Если ffmpeg не установлен:

```powershell
winget install -e --id Gyan.FFmpeg
```

## Запуск backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

По умолчанию данные пишутся в `backend/data`. Можно переопределить:

```powershell
$env:TRANSCRIB_APP_DATA_DIR="D:\transcrib-data"
```

Полезные переменные:

```powershell
$env:WHISPER_MODEL="large-v3-turbo"
$env:WHISPER_DEVICE="cuda"
$env:WHISPER_COMPUTE_TYPE="float16"
$env:WHISPER_FALLBACK_COMPUTE_TYPE="int8_float16"
```

Опциональная diarization по голосам:

```powershell
pip install -r requirements-diarization.txt
$env:DIARIZATION_ENABLED="1"
$env:DIARIZATION_MODEL="pyannote/speaker-diarization-3.1"
$env:DIARIZATION_DEVICE="cuda"
$env:DIARIZATION_MIN_SPEAKERS="2"
$env:DIARIZATION_MAX_SPEAKERS="4"
$env:HF_TOKEN="..."
```

`pyannote/speaker-diarization-3.1` может требовать Hugging Face token и принятие условий модели на Hugging Face. Если diarization выключена или модель недоступна, задача продолжает работать со старой локальной текстовой разметкой спикеров.

Опциональная облачная правка текста:

```powershell
$env:TEXT_POLISH_PROVIDER="auto"
$env:TEXT_POLISH_PROVIDERS="openai,deepseek,qwen,grok,gigachat,yandexgpt,mistral,groq"
$env:OPENAI_API_KEY="..."
$env:DEEPSEEK_API_KEY="..."
$env:QWEN_API_KEY="..."
$env:GROK_API_KEY="..."
$env:GIGACHAT_ACCESS_TOKEN="..."
$env:YANDEXGPT_API_KEY="..."
$env:YANDEXGPT_FOLDER_ID="..."
```

Если ключей нет, сервис недоступен или ответ облака не разобран, приложение использует локальные правила и не валит задачу. Для полного локального режима:

```powershell
$env:TEXT_POLISH_PROVIDER="local"
```

## Запуск frontend

В новом терминале:

```powershell
cd frontend
npm install
npm run dev
```

Откройте [http://127.0.0.1:5173](http://127.0.0.1:5173).

Если backend запущен не на `127.0.0.1:8000`, задайте:

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev
```

## API

- `POST /api/upload` - загрузить аудио-файл.
- `GET /api/jobs` - история задач.
- `GET /api/jobs/{job_id}` - статус задачи.
- `GET /api/jobs/{job_id}/result` - текст результата.
- `GET /api/jobs/{job_id}/download/txt` - скачать TXT.
- `GET /api/jobs/{job_id}/download/srt` - скачать SRT.
- `GET /api/jobs/{job_id}/download/vtt` - скачать VTT.

## Обработка

1. Backend сохраняет оригинальный файл в `backend/data/uploads`.
2. Worker берёт задачу из локальной очереди.
3. ffmpeg конвертирует файл в mono 16 kHz WAV.
4. faster-whisper запускается с `language="ru"`.
5. Если включена diarization, pyannote размечает интервалы голосов, а ASR-сегменты получают speaker label по максимальному overlap с голосовыми интервалами.
6. Локальная постобработка чистит служебные подписи, сохраняет diarization-метки спикеров, разбивает текст на читаемые блоки и нормализует частые IT/Agile-аббревиатуры.
7. Если настроены облачные ключи, text polish пробует провайдеров по приоритету и приводит текст в более аккуратное состояние. При ошибке используется локальный результат.
8. Результаты сохраняются в `backend/data/results/{job_id}`.
9. SQLite хранит историю, статусы и ошибки.

Если приложение перезапущено, задачи `queued` возвращаются в очередь. Задачи, прерванные во время `processing`, помечаются как `failed`, чтобы не зависать навсегда.

## Тесты

```powershell
pytest
```

Текущие тесты проверяют SQLite persistence и генерацию txt/srt/vtt. Они не запускают faster-whisper и не требуют GPU.
