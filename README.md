# STT Voice Input

Push-to-talk голосовой ввод через Whisper large-v3. Клиент-серверная архитектура: сервер с GPU обрабатывает речь, клиенты подключаются по сети.

Зажал Right Alt → говоришь → отпустил → текст вставляется в активное окно.
Поддерживаются Windows, X11 и Plasma/Wayland.

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
- X11: `xdotool`
- Wayland: `wl-clipboard`, `ydotool` и запущенный `ydotoold`
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

# Явный запуск Plasma/Wayland backend:
python3 stt_client_wayland.py --keyboard /dev/input/event7 --key-code 100

# Windows-клиент:
python stt_client_win.py

# Tray-индикатор (XFCE):
python3 stt_tray.py
```

### Настройки tray
В меню tray есть пункт **Settings...**. Через него можно указать STT backend,
profile, sample rate и auth-поля для `llm_proxy`.

Для STT доступны два режима:

- **Nemor Link profile** — приложение читает `~/.config/llm.json` и предлагает
  выбрать один из профилей с `kind: "stt"`. URL, порядок backend-ов,
  авторизация и TLS fingerprint полностью берутся из выбранного профиля.
- **Manual configuration** — URL, имя локального профиля, bearer token,
  host ID и TLS fingerprint задаются непосредственно в настройках voice-input.

Данные обоих режимов сохраняются раздельно, поэтому переключение режима не
стирает ручные параметры или ранее выбранный профиль Nemor Link.

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

### Plasma/Wayland

Wayland backend выбирается автоматически по `XDG_SESSION_TYPE`. Он читает
PTT-клавишу через evdev, временно копирует распознанный Unicode-текст через
`wl-copy`, вставляет его независимым от раскладки `Shift+Insert` через
`ydotool`, а затем восстанавливает прежнее содержимое clipboard. Если
пользователь успел сам скопировать новое значение, оно не перезаписывается.

Для Ubuntu:

```bash
sudo apt install wl-clipboard ydotool ydotoold
sudo usermod -aG input "$USER"
```

После добавления в группу нужен полный выход из сессии и повторный вход.
`ydotoold` должен быть запущен и иметь доступ к `/dev/uinput`; способ запуска
зависит от версии пакета. Проверка:

```bash
ydotool key SHIFT+INSERT
```

Путь клавиатуры и код клавиши можно оставить в
`~/.config/voice-input/config.json` как `KEYBOARD_DEVICE` и `KEY_CODE` либо
передать аргументами `--keyboard` и `--key-code`. Лучше использовать стабильный
путь из `/dev/input/by-id/`, а не меняющийся номер `eventN`. В отличие от X11
grab, evdev backend пока не подавляет физическую PTT-клавишу.

### Поиск устройства клавиатуры
```bash
python3 -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{dev.path}: {dev.name}')
"
```
