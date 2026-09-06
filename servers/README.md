# STT-серверы

Серверные зависимости устанавливаются отдельно от desktop-клиента.
Все команды ниже выполняются из корня репозитория.

| Backend | Запуск | Зависимости |
|---|---|---|
| GigaAM v3 | `python -m servers.stt_server_gigaam` | GPU PyTorch, Flask, numpy + `servers/requirements-gigaam.txt` |
| Whisper CUDA | `python -m servers.stt_server` | `pip install -r servers/requirements-cuda.txt` |
| Whisper ROCm | `python -m servers.stt_server_rocm` | `scripts/server/install_stt_server_rocm.sh` |

Серверы принимают моно float32 PCM через `POST /stt`, возвращают JSON с `text`
и `duration`; `GET /health` сообщает о готовности модели.
По умолчанию частота — 16000 Гц. Серверные значения `MODEL_SIZE`, `LANGUAGE`,
`SAMPLE_RATE`, `STT_PORT`, `STT_TOKEN` заданы в `servers/config.py` и могут быть
переопределены в `~/.config/voice-input/config.json` на серверной машине.

## Основное развёртывание

Проверено 2026-09-06 на `192.168.0.61`: конфигурация находится в
`~/.config/llm-proxy/config.yaml` (имя каталога через дефис).
Runtime `stt-gigaam` запускает GigaAM на ROCm, слушает `127.0.0.1:5056`,
имеет `autoload: true` и управляется `llm-proxy`.

Существующая команда продолжает работать:

```bash
cd /home/mirmik/project/voice-input
.venv/bin/python stt_server_gigaam.py
```

При настройке нового runtime можно использовать `-m servers.stt_server_gigaam`.
Рабочий каталог — корень репозитория. В действующем развёртывании используются:

- `.venv` с ROCm PyTorch и `.gigaam-runtime` как overlay через `PYTHONPATH`;
- `STT_HOST=127.0.0.1`, `STT_PORT_OVERRIDE=5056`;
- `GIGAAM_REVISION=7655ad717f8122257385bb4b2f373db3697e8680`;
- `HF_HUB_CACHE=/home/mirmik/project/models/stt-gigaam/huggingface-cache`;
- `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` (модель уже закэширована).

Overlay-зависимости сохранены в `requirements-gigaam.txt`; это дополнение к
GPU-окружению, а не самостоятельная установка PyTorch. GigaAM поддерживает CUDA
и ROCm, а также локальный каталог модели через `GIGAAM_MODEL_ID`.
По умолчанию одна запись ограничена 25 секундами (`GIGAAM_MAX_AUDIO_SECONDS`).

На сервере обнаружены локальные незакоммиченные изменения. При этой уборке
удалённый checkout, конфигурация и работающие процессы не изменялись.

## Whisper и systemd

```bash
scripts/server/run_stt_server.sh
scripts/server/run_stt_server_rocm.sh

scripts/server/install_systemd_user_stt_server.sh
scripts/server/install_systemd_user_stt_server_rocm.sh
```

Установщики systemd создают и включают пользовательские службы, но запускать их
нужно отдельно (`systemctl --user start stt-server.service` или
`stt-server-rocm.service`). Не запускайте systemd-копию того же backend-а,
которым уже управляет `llm-proxy`.

Python для CUDA задаётся через `PYTHON_BIN`, для ROCm — через `PYTHON_BIN` или
`VENV_DIR`. ROCm installer по умолчанию создаёт `~/venvs/voice-input-rocm`;
передайте этот путь как `VENV_DIR` при запуске. Файлы окружения:
`~/.config/voice-input/stt_server.env` и `stt_server_rocm.env`.

После перемещения скриптов в `scripts/server/` ранее установленные systemd-службы
нужно переустановить соответствующим установщиком: он обновит пути запуска.
Корневые Python-обёртки для всех трёх серверов сохранены для совместимости.
