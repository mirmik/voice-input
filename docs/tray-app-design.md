# Дизайн-док: Voice Input Tray App

## Цель

Сделать `voice-input` полноценным tray-приложением для голосового ввода в режиме push-to-talk.

Приложение должно:

- жить в системном трее;
- включать и выключать глобальный перехват клавиши из tray-меню;
- подавлять исходную клавишу, если выбранный backend это поддерживает;
- отправлять записанный звук в STT backend или, в будущем, запускать локальную модель;
- вставлять распознанный текст в активное окно;
- иметь GUI для редактирования настроек;
- использовать единый файл конфигурации приложения;
- поддерживать несколько платформенных backend-ов перехвата клавиш.

## Основной сценарий

1. Пользователь запускает приложение.
2. В системном трее появляется иконка.
3. Пользователь включает голосовой ввод через tray-меню.
4. Приложение устанавливает выбранный глобальный hotkey backend.
5. Пользователь удерживает настроенную клавишу.
6. Приложение начинает запись.
7. Пользователь отпускает клавишу.
8. Приложение останавливает запись.
9. Аудио отправляется в STT backend.
10. Распознанный текст вставляется в активное окно.
11. Пользователь может менять сервер, авторизацию, hotkey, звук и способ вставки через GUI.

## Общая архитектура

```text
Tray / GUI
   |
Application Controller
   |
   +-- Config Service
   +-- Hotkey Backend
   +-- Audio Recorder
   +-- STT Backend
   +-- Text Inserter
   +-- Diagnostics / Logging
```

## Application Controller

Контроллер владеет runtime-состоянием приложения и связывает подсистемы между собой.

Обязанности:

- запускать и останавливать активный режим;
- связывать hotkey-события с recorder-ом;
- отправлять записанное аудио в выбранный STT backend;
- вставлять распознанный текст;
- обновлять состояние tray-иконки;
- применять измененные настройки;
- переключать STT backend;
- обрабатывать ошибки backend-ов;
- корректно завершать приложение.

Предлагаемые состояния:

```text
stopped
starting
running
recording
transcribing
error
```

`recording` и `transcribing` могут быть временными под-состояниями поверх `running`.

## Config Service

У приложения должен быть один config service и один основной конфигурационный файл.

Предлагаемые пути:

- Windows: `%APPDATA%\VoiceInput\config.json`
- Linux: `~/.config/voice-input/config.json`

Начальная схема:

```json
{
  "version": 1,
  "hotkey": {
    "backend": "auto",
    "key": {
      "display": "Right Alt",
      "windows_vk": "VK_RMENU",
      "windows_scan": 56,
      "x11_keysym": "Alt_R",
      "linux_evdev_code": 100
    },
    "suppress_original": true
  },
  "audio": {
    "sample_rate": 16000,
    "device": null,
    "min_duration_sec": 0.3
  },
  "stt": {
    "mode": "remote",
    "profile": "default",
    "server_url": "http://localhost:5055",
    "auth": {
      "type": "bearer",
      "token": null,
      "host_id": null,
      "auth_file": null
    }
  },
  "insertion": {
    "method": "clipboard_paste",
    "restore_clipboard": true
  },
  "ui": {
    "start_on_login": false,
    "start_enabled": false,
    "show_notifications": true
  },
  "logging": {
    "level": "info"
  }
}
```

Auth-токены в идеале не должны навсегда оставаться plain JSON.

Возможные варианты хранения:

- Windows Credential Manager;
- Secret Service / libsecret на Linux;
- fallback в JSON с явным предупреждением;
- внешний auth-файл, совместимый с текущей схемой `llm-proxy`.

## Tray и Settings GUI

Tray menu:

```text
Voice Input: On/Off
Settings...
Diagnostics...
Quit
```

Состояния tray-иконки:

- disabled;
- enabled / idle;
- recording;
- transcribing;
- error.

Разделы окна настроек:

- STT backend:
  - remote server URL;
  - profile;
  - auth token или auth file;
  - test connection.
- Hotkey:
  - текущая клавиша;
  - кнопка capture key;
  - checkbox suppress original;
  - выбор backend-а: auto, Windows hook, X11 grab, evdev, system remapper.
- Audio:
  - input device;
  - sample rate;
  - test microphone.
- Text insertion:
  - clipboard paste;
  - direct typing;
  - restore clipboard.
- Startup:
  - launch on login;
  - enable capture on startup.
- Diagnostics:
  - backend status;
  - last errors;
  - detected platform;
  - selected hotkey backend.

Рекомендуемый GUI toolkit: `PySide6`.

Причины:

- есть нормальная cross-platform tray-история;
- можно сделать полноценное окно настроек;
- не придется делить tray и settings GUI между разными библиотеками.

`pystray` подходит для очень маленького tray-приложения, но полноценный settings GUI все равно потребует отдельного GUI toolkit-а.

## Hotkey Backends

Нужен общий интерфейс backend-а:

```python
class HotkeyBackend:
    def start(self, hotkey, on_down, on_up) -> None:
        ...

    def stop(self) -> None:
        ...

    def capture_next_key(self, timeout=None) -> CapturedKey:
        ...

    def capabilities(self) -> HotkeyCapabilities:
        ...
```

Предлагаемые capabilities:

```text
global_capture
suppress_original
capture_next_key
requires_admin
works_on_wayland
supports_key_remap
```

### Windows Hook Backend

Реализация:

- использовать `SetWindowsHookExW(WH_KEYBOARD_LL)`;
- читать `KBDLLHOOKSTRUCT.vkCode`, `scanCode` и `flags`;
- подавлять исходную клавишу возвратом `1` из hook callback;
- держать hook callback быстрым;
- отправлять down/up события в worker queue.

Ограничения:

- обычный user-mode hook может не влиять на elevated-окна;
- lock screen, login screen и secure attention sequence вне области действия;
- некоторые аппаратные клавиши могут не приходить как обычные keyboard events.

### X11 Grab Backend

Реализация:

- использовать `XGrabKey`;
- выставлять `owner_events=False`, чтобы активный X11-клиент не получал grabbed-клавишу;
- привязываться по keysym или keycode.

Примеры:

```bash
python3 stt_client_x11.py --key Alt_R
python3 stt_client_x11.py --key ISO_Level3_Shift
python3 stt_client_x11.py --key F13
```

Ограничения:

- только X11;
- не работает для Wayland-сессий.

### Linux evdev Backend

Варианты реализации:

- читать `/dev/input/event*` напрямую;
- определять физические клавиши по evdev code, например `KEY_RIGHTALT = 100`;
- опционально использовать `EVIOCGRAB`, чтобы событие не доходило до остальной системы.

Важное ограничение:

Если использовать `EVIOCGRAB` на клавиатуре, приложение должно переизлучать все не-hotkey события через `uinput`. Иначе клавиатура станет непригодной для обычного ввода, пока устройство grabbed.

Этот backend мощный, но гораздо более инвазивный, чем X11 grabbing.

### Wayland

Wayland намеренно ограничивает глобальный перехват клавиатуры из обычных приложений.

Возможные подходы:

- compositor-specific shortcuts;
- desktop portals, если для целевого compositor-а есть пригодный API;
- системные remapper-ы вроде `keyd`;
- fallback без глобального перехвата с честным предупреждением в UI.

Полную поддержку Wayland не стоит обещать в первой версии.

### System Remapper Backend

Возможные интеграции:

- Linux: `keyd`, XKB, interception-tools;
- Windows: registry scancode map, PowerToys, Interception driver.

Это полезно для более поздней фазы, особенно если нужно поведение ниже уровня обычной desktop-сессии.

## Hotkey Selection GUI

Flow выбора клавиши:

1. Пользователь нажимает "Choose key".
2. Приложение временно входит в capture mode.
3. Следующее key down событие записывается.
4. UI показывает нормализованное имя, например `Right Alt`, `Caps Lock` или `F13`.
5. Приложение сохраняет display name и платформенные идентификаторы.
6. Пользователь может сразу проверить suppression.

Предлагаемый объект в конфиге:

```json
{
  "display": "Right Alt",
  "windows_vk": "VK_RMENU",
  "windows_scan": 56,
  "x11_keysym": "Alt_R",
  "linux_evdev_code": 100
}
```

Не стоит полагаться на один универсальный key code для всех платформ. Лучше хранить нормализованное display name и платформенные поля.

## STT Backends

Общий интерфейс:

```python
class STTBackend:
    def probe(self) -> BackendStatus:
        ...

    def transcribe(self, audio_bytes, sample_rate) -> TranscriptionResult:
        ...

    def close(self) -> None:
        ...
```

### Remote Backend

Remote backend должен остаться первым production-путем.

Обязанности:

- использовать текущий HTTP / `nemor_link` путь;
- поддерживать auth;
- выполнять health checks;
- отдавать backend status;
- поддерживать timeout configuration;
- поддерживать profile selection.

### Standalone Backend

Standalone backend можно вводить второй фазой.

Варианты:

- embedded Python `faster-whisper`;
- subprocess server под управлением tray-приложения;
- local model profile с выбором CUDA / ROCm / CPU.

Tray UI должен явно показывать lifecycle модели, особенно состояние `loading`.

Начальная рекомендация:

- спроектировать интерфейс сейчас;
- оставить remote STT первым clean implementation;
- standalone mode реализовать после стабилизации tray и config architecture.

## Audio Recorder

Recorder должен быть независим от hotkey backend-а.

Интерфейс:

```python
class Recorder:
    def start(self) -> None:
        ...

    def stop(self) -> AudioBuffer:
        ...

    def cancel(self) -> None:
        ...
```

Поведение:

- `start` idempotent;
- `stop` idempotent;
- minimum duration проверяется после записи;
- input device configurable;
- recorder не выполняет network calls.

Pipeline:

```text
hotkey down -> recorder.start
hotkey up -> audio = recorder.stop
audio -> stt.transcribe
text -> inserter.insert
```

## Text Inserter

Общий интерфейс:

```python
class TextInserter:
    def insert(self, text: str) -> None:
        ...
```

Backends:

- Windows:
  - direct Unicode typing через `SendInput`;
  - clipboard плюс `Ctrl+V` может быть fallback-методом;
  - optional clipboard restore для fallback-метода.
- X11:
  - `xdotool type`;
  - clipboard paste fallback.
- Wayland:
  - clipboard tools или compositor-specific paths;
  - скорее всего, ограниченная поддержка.

Clipboard restoration должен быть настраиваемым, потому что он может быть ненадежен с большим или сложным содержимым clipboard-а.

## Error Handling и Diagnostics

Ошибки должны быть видны в:

- tray status;
- diagnostics window;
- log file.

Типовые классы ошибок:

- STT server unreachable;
- auth failed;
- microphone unavailable;
- selected hotkey backend unavailable;
- selected key cannot be suppressed;
- text insertion failed;
- permission denied;
- model failed to load.

Предлагаемые пути логов:

- Windows: `%LOCALAPPDATA%\VoiceInput\logs\voice-input.log`
- Linux: `~/.local/state/voice-input/voice-input.log`

## Packaging

### Windows

Рекомендуемый первый package:

- PyInstaller или Nuitka `.exe`;
- config в `%APPDATA%\VoiceInput`;
- logs в `%LOCALAPPDATA%\VoiceInput`;
- autostart через registry `Run` key или Startup folder;
- без driver dependency в первой версии.

Приложение должно предупреждать, если пользователь пытается управлять elevated-приложениями из non-elevated процесса.

### Linux

Рекомендуемый путь:

- сначала поддержка X11;
- config в `~/.config/voice-input`;
- logs в `~/.local/state/voice-input`;
- autostart через `.desktop`;
- позже package как `.deb` или AppImage.

Wayland должен показываться как limited, если не настроен system-level remapper или compositor integration.

## Предлагаемая структура проекта

```text
voice_input/
  app.py
  config.py
  controller.py
  audio.py
  platform_detect.py
  logging_setup.py
  stt/
    __init__.py
    base.py
    remote.py
    standalone.py
  hotkeys/
    __init__.py
    base.py
    win_hook.py
    x11_grab.py
    linux_evdev.py
  insertion/
    __init__.py
    base.py
    win_clipboard.py
    x11_xdotool.py
  ui/
    __init__.py
    tray.py
    settings_window.py
    hotkey_capture.py
    diagnostics_window.py
```

Compatibility wrappers можно оставить:

```text
stt_client_win.py
stt_client_x11.py
stt_tray.py
```

Они должны вызывать новые entrypoints, а не содержать существенную логику.

## Фазы реализации

1. Создать config service и новую схему `config.json`.
2. Определить интерфейс `HotkeyBackend`.
3. Перенести Windows hook code в `hotkeys/win_hook.py`.
4. Перенести X11 grab code в `hotkeys/x11_grab.py`.
5. Разделить recorder, STT backend и text insertion на независимые компоненты.
6. Собрать controller, который может работать без GUI.
7. Добавить tray с On/Off/Quit.
8. Добавить settings GUI.
9. Добавить hotkey capture UI.
10. Добавить diagnostics и logging.
11. Подготовить packaging.

## Ключевые технические решения

- Поведение hotkey по умолчанию: hold-to-record.
- Hotkey события являются down/up событиями, а не toggle.
- Hook callbacks никогда не выполняют тяжелую работу.
- Suppression включается только в активном режиме.
- Config хранит platform-specific key identifiers.
- Remote STT является первым production backend-ом.
- Standalone model support проектируется сейчас, но реализуется позже.
- Wayland support явно ограничен в первой версии.

## Открытые вопросы

- Хранить auth tokens в JSON на первом этапе или сразу делать OS keychain?
- Нужен ли press-to-toggle режим наряду с hold-to-record?
- Нужно ли прямо поддерживать Windows elevated mode?
- Считать ли Wayland out of scope для первой версии?
- Делать ли первый GUI сразу на PySide6, или полезен маленький tray-only промежуточный этап?
- Включать ли clipboard restoration по умолчанию?
