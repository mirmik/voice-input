# STT Voice Input

Push-to-talk голосовой ввод для Linux (XFCE) через Whisper large-v3.

Зажал Right Alt → говоришь → отпустил → текст вставляется в активное окно.

## Как это работает

```
Right Alt (evdev) → Микрофон (sounddevice) → Whisper large-v3 (faster-whisper, GPU)
    → xdotool type → текст в активное окно
```

Tray-индикатор позволяет включать/выключать STT без терминала, чтобы не держать модель в VRAM постоянно.

## Требования

- Linux (XFCE, но должно работать и в других DE с поддержкой AppIndicator)
- NVIDIA GPU с поддержкой CUDA (для Whisper)
- Python 3.10+
- Клавиатура, видимая через evdev

## Установка

```bash
git clone <repo-url>
cd whisper-test
./install.sh
```

Скрипт установит:
- Системные пакеты: `python3-gi`, `gir1.2-ayatanaappindicator3-0.1`, `xdotool`
- Python-пакеты: `faster-whisper`, `evdev`, `sounddevice`, `numpy`
- Добавит пользователя в группу `input` (для доступа к evdev без sudo)
- Создаст autostart-запись для XFCE
- Скачает модель Whisper large-v3 (~3 ГБ)

После установки перелогиньтесь (для группы `input`).

## Использование

### Через tray
После логина иконка микрофона появится в трее (перечёркнутый = STT выключен).
- Клик → **Start STT** — загружает модель, начинает слушать клавишу
- Клик → **Stop STT** — выгружает модель, освобождает VRAM
- **Quit** — убирает из трея

### Ручной запуск
```bash
# Только STT (без трея):
python3 voice_input.py

# Tray-индикатор:
/usr/bin/python3 stt_tray.py
```

### Голосовой чат с Claude
```bash
python3 voice_chat.py
```
Требует настроенный Claude Code. Ответы Claude выводятся в терминал и (опционально) озвучиваются через XTTS v2.

## Файлы

| Файл | Назначение |
|------|-----------|
| `voice_input.py` | Основной STT-скрипт: evdev → запись → Whisper → xdotool |
| `voice_chat.py` | Голосовой чат с Claude через `--resume` |
| `stt_tray.py` | XFCE tray-индикатор для управления voice_input.py |
| `install.sh` | Скрипт установки зависимостей и autostart |

## Настройка

### Клавиша активации
В `voice_input.py` измените `KEY_CODE`:
```python
KEY_CODE = ecodes.KEY_RIGHTALT  # Right Alt по умолчанию
```

### Устройство ввода
Если клавиатура не Mistel или event7 не подходит, найдите правильный:
```bash
python3 -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{dev.path}: {dev.name}')
"
```
Затем измените путь в `voice_input.py`:
```python
kbd = evdev.InputDevice("/dev/input/event7")  # ← ваш путь
```

### Модель Whisper
```python
MODEL_SIZE = "large-v3"  # варианты: tiny, base, small, medium, large-v3
```

### Python-интерпретатор для tray
Если используется pyenv, в `stt_tray.py` проверьте путь:
```python
PYTHON = os.path.expanduser("~/.pyenv/versions/3.10.19/bin/python3")
```
