# Chat History

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
