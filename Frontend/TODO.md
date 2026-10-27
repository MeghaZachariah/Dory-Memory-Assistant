# DORY implementation checklist

## Root shell and navigation
- [x] Built `src/App.jsx` as the root shell with a sticky top navigation bar that instantly switches between Voice Screen and Family Dashboard.
- [x] Kept the requested frontend in exactly three source files under `src/`: `App.jsx`, `VoiceScreen.jsx`, and `Dashboard.jsx`.

## Patient voice-first experience
- [x] Built `src/VoiceScreen.jsx` with a warm, calming, high-contrast cream/amber/deep-slate UI optimized for seniors.
- [x] Added animated microphone states: Idle, Listening with pulsing red ring, Thinking with bouncing amber indicator, Speaking, and Asking Family.
- [x] Integrated SpeechRecognition and speechSynthesis with graceful fallbacks when browser speech capabilities are unavailable.
- [x] Connected chat interactions to `POST /api/chat`, including quick actions, readable responses, text-input fallback, loading states, and clean offline errors.

## Family caregiver dashboard
- [x] Built `src/Dashboard.jsx` with five tabs: Dory's Answers (Lie-Catcher), Saved Facts (Receipts), Today's Overview, Family Questions, and Memory Book & Meds.
- [x] Fetches dashboard data from `/dashboard/summary`, `/dashboard/facts`, `/dashboard/logs`, and `/dashboard/questions`.
- [x] Includes loading, empty, and backend-offline states throughout dashboard views.
- [x] Includes status badges, source quotes, caregiver alerts, pending Telegram questions, and a manual grounded-memory form.

## Runtime and delivery
- [x] Added Vite/Tailwind setup and a route manifest for the root page.
- [x] Verified the app builds cleanly and saved the source in the project checkpoint.
