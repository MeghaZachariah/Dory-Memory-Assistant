# Dory Android app

The person's side of Dory. It rings like a real phone call every morning and evening (even when the phone is locked or the app is closed), then talks by voice. All the thinking happens on the Dory server, which calls Nemotron on Nebius Token Factory.

- **8 am:** "Dory is calling." Answer, and Dory reads the morning reminder.
- **8 pm:** Dory calls for the evening chat: four gentle questions, then the facts are saved.
- **Any time:** tap "Talk to Dory" and ask a question.

Listening and speaking use Android's built-in engines, so they're free. There are no phone-minute charges, because it's not a phone-network call.

## 1. Start the Dory server on your laptop

From the repo root (`dory-hackathon/`):

```bash
pip install -r backend/ai/requirements.txt -r backend/api/requirements.txt
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs to see every endpoint. Click `POST /demo/load` → "Try it out" → "Execute" to load the sample person (Mary). It uses no credits.

Without `NEBIUS_API_KEY` in `.env`, medicine questions and the demo still work, but memory answers say "Sorry, I didn't catch that."

## 2. Install Flutter (once)

Follow https://docs.flutter.dev/get-started/install for your laptop (choose **Android**). That installs Flutter and Android Studio. Then check:

```bash
flutter doctor
```

Fix anything it marks with a red cross under "Flutter" and "Android toolchain". Run `flutter doctor --android-licenses` if it asks.

## 3. Create the Android project files

This folder has the app code but not the Android build files (Gradle, icons), which Flutter generates for your machine:

```bash
cd mobile/dory_app
flutter create --platforms=android --org com.dory --project-name dory_app .
flutter pub get
```

`flutter create` keeps the files already here (`lib/`, `pubspec.yaml`, `AndroidManifest.xml`, `test/`) and only adds what's missing.

## 4. Connect your phone and run

1. On the phone: Settings → About phone → tap **Build number** 7 times. Then Settings → Developer options → turn on **USB debugging**.
2. Plug the phone into the laptop and accept the prompt on the phone.
3. Run:

```bash
flutter devices        # your phone should be listed
flutter run            # builds, installs and opens Dory
```

## 5. Point the app at your server

The phone has to reach the server on your laptop. Easiest way, over the USB cable:

```bash
adb reverse tcp:8000 tcp:8000
```

Then in the app: **Settings → Dory server address → `http://localhost:8000`** → Test connection → Save.

Over Wi-Fi instead: use your laptop's IP (`ipconfig` on Windows, `ip addr` on Mac/Linux), like `http://192.168.1.20:8000`. Both devices must be on the same network. College Wi-Fi often blocks this, so connect the laptop to your phone's hotspot. On Windows, allow Python through the firewall when asked.

## 6. Try it

1. Allow notifications, the microphone and full-screen calls when asked.
2. Tap **Test the ring (10 seconds)**, lock the phone, and wait. It should ring with "Dory, Evening chat". Answer it.
3. Tap **Talk to Dory** and ask "Did I take my tablets?" Dory reads the caregiver's log; no AI is involved.
4. With credits set up, ask "Did anyone visit me?" or "When was my wedding?"

To install on another phone without a cable: `flutter build apk --debug`, then send `build/app/outputs/flutter-apk/app-debug.apk` and open it on the phone (allow "install unknown apps").

## If something goes wrong

| Problem | Fix |
|---|---|
| Doesn't ring at the set time | Settings → Apps → Dory → Battery → **Unrestricted**. Also allow **Alarms & reminders** for Dory. Some phones (Xiaomi, Oppo, Vivo, Samsung) also need Dory added to "auto-start" or "never sleeping apps". |
| Rings but no full-screen call when locked | Settings → Apps → Dory → allow **Full-screen notifications** (Android 14+). |
| "Can't reach the Dory server" | Check the server is running, re-run `adb reverse`, or check the Wi-Fi IP. |
| Dory doesn't hear you | Allow the microphone; make sure "Speech services by Google" is installed and up to date. |
| Wrong language | Settings → Language, e.g. `ml-IN` for Malayalam, `hi-IN` for Hindi. The phone needs that language's speech pack (Google app → Settings → Voice → Offline speech recognition). |
| Build error | Run `flutter clean` then `flutter pub get` and try again. If it still fails, copy the error text and ask. |

## Where things are

| File | What it does |
|---|---|
| `lib/calls.dart` | The ringing call screen and the daily 8 am / 8 pm schedule |
| `lib/call_screen.dart` | The conversation during a call: morning reminder, evening chat, questions |
| `lib/voice.dart` | Listening and speaking |
| `lib/api.dart` | Talking to the Dory server |
| `lib/home_screen.dart`, `lib/settings_screen.dart` | The two screens |
| `lib/theme.dart` | Colours and large text |

## Honest limits

- Android only. It isn't a phone-network call, so it needs the app installed and internet.
- If the phone is off, or the person declines, the call is missed. A "Missed call from Dory" notification lets them call back.
- Exact timing depends on the phone's battery settings (see the table above).
