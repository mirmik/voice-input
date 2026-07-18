# STT Voice Input

Push-to-talk голосовой ввод через Whisper large-v3. Клиент-серверная архитектура: сервер с GPU обрабатывает речь, клиенты подключаются по сети.

Зажал Right Alt → говоришь → отпустил → текст вставляется в активное окно.

## Архитектура

```
[Linux/Windows клиент]                    [Сервер (GPU)]
Right Alt → Микрофон → HTTP POST ──────→ Whisper large-v3
xdotool/SendInput ← текст ←── JSON ←──────  распознавание
```

Сервер загружает модель один раз и обслуживает любое количество клиентов. Модель в VRAM только пока сервер запущен.

## Требования

### Сервер
- NVIDIA GPU с поддержкой CUDA
- Python 3.10+
- `faster-whisper`, `flask`, `numpy`

### Linux-клиент
- `evdev`, `sounddevice`, `numpy`, `requests`
- `xdotool` для вставки текста
- Пользователь в группе `input` (для evdev без sudo)

### Windows-клиент
- `sounddevice`, `numpy`, `requests`, `pystray`, `pillow`

## Установка (Linux, сервер + клиент на одной машине)

```bash
git clone <repo-url>
cd voice-input
pip install -r requirements.txt
./install.sh
```

## Использование

### Через tray (Linux)
После логина иконка микрофона в трее.
- **Start STT** — запускает сервер (загружает модель) + клиент
- **Stop STT** — останавливает оба, освобождает VRAM
- **Quit** — убирает из трея

### Ручной запуск
```bash
# Сервер (на машине с GPU):
python3 stt_server.py

# Linux-клиент (на той же или другой машине):
python3 stt_client.py

# Windows-клиент:
python stt_client_win.py

# Tray-индикатор (XFCE):
python3 stt_tray.py
```

### Настройки tray
В меню tray есть пункт **Settings...**. Через него можно указать STT backend,
profile, sample rate и auth-поля для `llm_proxy`.

Приложение хранит свои настройки в:
```text
~/.config/voice-input/config.json
```

Конкретный адрес backend-а, токены и TLS fingerprint не хранятся в репозитории;
они должны быть заданы в пользовательском config-е.


### Удалённый доступ
Для удалённого backend-а откройте **Settings...** в tray-меню и задайте URL
сервера. Значение сохранится в `~/.config/voice-input/config.json`.

## Файлы

| Файл | Назначение |
|------|-----------|
| `stt_server.py` | HTTP-сервер с Whisper (запускается на машине с GPU) |
| `stt_client.py` | Linux-клиент: evdev push-to-talk → сервер → xdotool |
| `stt_client_win.py` | Windows-клиент: push-to-talk → сервер → SendInput |
| `stt_tray.py` | XFCE tray-индикатор (управляет сервером и клиентом) |
| `config.py` | Все настройки: устройство, клавиша, модель, сервер |
| `install.sh` | Установка зависимостей и autostart |

## Настройка (config.py)

```python
KEYBOARD_DEVICE = "/dev/input/event7"  # evdev устройство клавиатуры
KEY_CODE = 100                          # 100 = Right Alt
MODEL_SIZE = "large-v3"                 # tiny/base/small/medium/large-v3
LANGUAGE = "ru"                         # или "en", или None (авто)
STT_SERVER = "http://localhost:5055"    # URL сервера (для клиента)
STT_PORT = 5055                         # порт (для сервера)
PYTHON = "python3"                      # интерпретатор для tray
```

### Поиск устройства клавиатуры
```bash
python3 -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{dev.path}: {dev.name}')
"
```
