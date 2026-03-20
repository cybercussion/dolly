# Dolly

![One man can make a difference](https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTlIZB_E6c6W8PU0PVNfkGbUtxsKyrLC_Fv3g&s)

In a dangerous world, where in 2026 I have to stare at a event with no image on my watch, I decided to do something about it.

Python daemon that monitors Blink and Wyze cameras for motion events and pushes rich image notifications to Android via [ntfy](https://ntfy.sh) — optimized for Samsung Galaxy Watch Ultra (BigPictureStyle).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your camera credentials and ntfy topic.

### Blink

On first run you'll be prompted for a 2FA code sent to your email/phone. Credentials are cached in `blink.json` for subsequent runs.

### Wyze

Wyze requires an API key pair and email/password authentication.

1. Get your API key and key ID from the [Wyze Developer Console](https://developer-api-console.wyze.com)
2. If you sign in with Google or Apple, Wyze doesn't expose a password by default. To set one:
   - Go to Google Account > Security > Third-party connections
   - Unlink Wyze
   - In the Wyze app, tap "Sign in with email" and use "Forgot password" with your Google/Apple email
   - Set a password via the reset link
   - You can re-link Google/Apple afterward if you want
3. Add your email, password, key_id, and api_key to `config.yaml`

## Test Authentication

```bash
source .venv/bin/activate && python tests/auth.py
```

## Test Notifications

Install [ntfy](https://play.google.com/store/apps/details?id=io.heckel.ntfy) from the Play Store and subscribe to your topic (must match `ntfy.topic` in `config.yaml`). Then:

```bash
source .venv/bin/activate && python tests/notify.py
```

## Run the Daemon

```bash
source .venv/bin/activate && python run.py
```

Polls cameras every 10s, detects new motion clips, extracts a frame from the clip, and pushes it to ntfy. Ctrl-C to stop.

## Install as macOS Service

Runs as a launchd agent — auto-starts on login, restarts on crash.

```bash
cp com.cybercussion.dolly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cybercussion.dolly.plist
```

Manage:

```bash
launchctl list | grep dolly                                          # status
launchctl unload ~/Library/LaunchAgents/com.cybercussion.dolly.plist # stop
launchctl load ~/Library/LaunchAgents/com.cybercussion.dolly.plist   # start
```

Logs: `dolly.log` in the project directory.

## Project Structure

```
├── run.py                     # Daemon entry point
├── tests/
│   ├── auth.py                # Camera authentication
│   ├── motion.py              # One-shot motion check
│   ├── notify.py              # Send a notification
│   └── debug_media.py         # Debug Blink media API
└── dolly/
    ├── config.py              # YAML loader + camera source factory
    ├── daemon.py              # Poll loop + motion state tracking
    ├── notifier.py            # ntfy push (image + text)
    └── cameras/
        ├── base.py            # CameraSource ABC + CameraInfo dataclass
        ├── blink.py           # Blink integration (blinkpy)
        └── wyze.py            # Wyze integration (wyze-sdk)
```

### Adding a new camera brand

1. Create `dolly/cameras/newbrand.py` implementing `CameraSource`
2. Register it in `dolly/config.py:build_sources()`
3. Add config block to `config.yaml`
