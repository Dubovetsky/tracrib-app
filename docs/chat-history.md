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
