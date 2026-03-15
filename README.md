# STT Voice Input

Push-to-talk голосовой ввод через Whisper large-v3. Клиент-серверная архитектура: сервер с GPU обрабатывает речь, клиенты подключаются по сети.

Зажал Right Alt → говоришь → отпустил → текст вставляется в активное окно.

## Архитектура

```
[Linux/Windows клиент]                    [Сервер (GPU)]
Right Alt → Микрофон → HTTP POST ──────→ Whisper large-v3
xdotool/Ctrl+V ← текст ←── JSON ←──────  распознавание
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
- `pynput`, `sounddevice`, `numpy`, `requests`, `pyperclip`, `keyboard`

## Установка (Linux, сервер + клиент на одной машине)

```bash
git clone <repo-url>
cd voice-input
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
/usr/bin/python3 stt_tray.py
```

### Удалённый доступ
На клиентской машине в `config.py` (Linux) или в `stt_client_win.py` (Windows) укажите IP сервера:
```python
STT_SERVER = "http://192.168.1.100:5055"
```

## Файлы

| Файл | Назначение |
|------|-----------|
| `stt_server.py` | HTTP-сервер с Whisper (запускается на машине с GPU) |
| `stt_client.py` | Linux-клиент: evdev push-to-talk → сервер → xdotool |
| `stt_client_win.py` | Windows-клиент: pynput push-to-talk → сервер → Ctrl+V |
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
