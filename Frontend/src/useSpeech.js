import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// Browser speech APIs. Chrome and Edge support both. Firefox has no recognition,
// so the app falls back to typing. Microphone needs HTTPS (or localhost).
const Recognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;
const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

export function useSpeech({ lang = "en-US", rate = 0.9 } = {}) {
  const recRef = useRef(null);
  const [voice, setVoice] = useState(null);

  // Pick a calm English voice once the browser has loaded its voice list.
  useEffect(() => {
    if (!canSpeak) return;
    const pick = () => {
      const english = window.speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
      setVoice(
        english.find((v) => /natural|samantha|google uk english female|aria|jenny/i.test(v.name)) ||
          english.find((v) => v.localService) ||
          english[0] ||
          null
      );
    };
    pick();
    window.speechSynthesis.onvoiceschanged = pick;
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  /** Listen once. Resolves with the final text, rejects with { code }. */
  const listen = useCallback(
    (onInterim) =>
      new Promise((resolve, reject) => {
        if (!Recognition) return reject({ code: "unsupported" });
        const rec = new Recognition();
        recRef.current = rec;
        rec.lang = lang;
        rec.interimResults = true;
        rec.continuous = false;
        rec.maxAlternatives = 1;

        let finalText = "";
        let failed = false;

        rec.onresult = (event) => {
          let interim = "";
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const piece = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalText += piece;
            else interim += piece;
          }
          if (onInterim) onInterim((finalText + interim).trim());
        };
        rec.onerror = (event) => {
          failed = true;
          reject({ code: event.error });
        };
        rec.onend = () => {
          recRef.current = null;
          if (failed) return;
          const text = finalText.trim();
          if (text) resolve(text);
          else reject({ code: "no-speech" });
        };
        try {
          rec.start();
        } catch {
          reject({ code: "start-failed" });
        }
      }),
    [lang]
  );

  const stopListening = useCallback(() => {
    if (recRef.current) recRef.current.stop(); // finishes with what was heard so far
  }, []);

  /** Speak text aloud. Always resolves when speech ends or is interrupted. */
  const speak = useCallback(
    (text) =>
      new Promise((resolve) => {
        if (!canSpeak) return resolve();
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang;
        utterance.rate = rate; // a little slower than normal
        utterance.pitch = 1;
        if (voice) utterance.voice = voice;
        utterance.onend = resolve;
        utterance.onerror = resolve;
        window.speechSynthesis.speak(utterance);
      }),
    [lang, rate, voice]
  );

  const stopSpeaking = useCallback(() => {
    if (canSpeak) window.speechSynthesis.cancel();
  }, []);

  const stopAll = useCallback(() => {
    if (recRef.current) recRef.current.abort();
    stopSpeaking();
  }, [stopSpeaking]);

  const supported = useMemo(() => ({ listen: !!Recognition, speak: canSpeak }), []);

  return { supported, listen, stopListening, speak, stopSpeaking, stopAll };
}
