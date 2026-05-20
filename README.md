# Transcrib App

Локальный web-сервис для транскрибации аудио в текст на Windows 11 с NVIDIA GPU. MVP не использует облачные API, не делает real-time транскрибацию и не включает diarization.

## Стек

- Backend: Python, FastAPI, SQLite
- ASR: faster-whisper, модель `large-v3-turbo`
- GPU: CUDA, `float16` с fallback на `int8_float16`
- Audio preprocessing: ffmpeg, mono 16 kHz WAV
- Frontend: React + Vite
- Storage: локальная папка `backend/data`

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
5. Результаты сохраняются в `backend/data/results/{job_id}`.
6. SQLite хранит историю, статусы и ошибки.

Если приложение перезапущено, задачи `queued` возвращаются в очередь. Задачи, прерванные во время `processing`, помечаются как `failed`, чтобы не зависать навсегда.

## Тесты

```powershell
pytest
```

Текущие тесты проверяют SQLite persistence и генерацию txt/srt/vtt. Они не запускают faster-whisper и не требуют GPU.
