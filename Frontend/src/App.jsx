import { useRef, useState } from "react";
import { PERSON_ID, PERSON_NAME } from "./config";
import { chat, finishEvening, getBriefing, resetDemo } from "./api";
import { useSpeech } from "./useSpeech";

// Add ?demo=1 to the address to show the demo buttons (hidden for the person).
const DEMO = new URLSearchParams(window.location.search).get("demo") === "1";

const STATUS_TEXT = {
  idle: "Ready when you are",
  listening: "I'm listening",
  thinking: "Let me think",
  speaking: "Dory is speaking",
  typing: "Type your answer below",
};

const OFFLINE_REPLY =
  "I can't reach my notes right now. Please ask your family to help, and try again in a moment.";

function listenMessage(code) {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "Dory needs your microphone. Allow it in the browser, or type below.";
    case "no-speech":
      return "I didn't hear anything. Tap the big button and try again.";
    case "unsupported":
      return "Voice doesn't work in this browser. Please type below.";
    default:
      return "I couldn't hear that. Tap the big button to try again, or type below.";
  }
}

const dateLine = () =>
  new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric" }).format(
    new Date()
  );

function MicIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
      <path
        d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function App() {
  const speech = useSpeech();
  const [phase, setPhase] = useState("idle"); // idle | listening | thinking | speaking | typing
  const [mode, setMode] = useState("chat"); // chat | evening
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState("");
  const [typed, setTyped] = useState("");
  const [reply, setReply] = useState({
    text: `Hello, ${PERSON_NAME}. Tap the big button and talk to me.`,
    status: "greeting",
    sources: [],
  });

  const typedResolver = useRef(null); // set while the evening chat waits for typed text
  const cancelled = useRef(false);

  // ----- speaking -----
  async function say(text) {
    setPhase("speaking");
    await speech.speak(text);
    setPhase("idle");
  }

  async function showReply(res) {
    setReply({
      text: res.reply,
      status: res.status,
      sources: res.sources || [],
    });
    await say(res.reply);
  }

  async function showOffline() {
    setReply({ text: OFFLINE_REPLY, status: "offline", sources: [] });
    await say(OFFLINE_REPLY);
  }

  // ----- one question and answer -----
  async function ask(text) {
    setNotice("");
    setHeard(text);
    setPhase("thinking");
    try {
      const res = await chat({ person_id: PERSON_ID, text, mode: "chat" });
      await showReply(res);
    } catch {
      await showOffline();
    }
  }

  async function talk() {
    if (phase === "listening") return speech.stopListening();
    if (phase === "speaking") {
      speech.stopSpeaking();
      return setPhase("idle");
    }
    if (phase !== "idle" || mode === "evening") return;

    setNotice("");
    setHeard("");
    setPhase("listening");
    try {
      const text = await speech.listen(setHeard);
      await ask(text);
    } catch (e) {
      setPhase("idle");
      setNotice(listenMessage(e.code));
    }
  }

  // ----- evening check-in -----
  function getAnswer() {
    if (speech.supported.listen) {
      setPhase("listening");
      return speech.listen(setHeard);
    }
    setPhase("typing"); // browsers without voice recognition: wait for typed text
    return new Promise((resolve) => {
      typedResolver.current = resolve;
    });
  }

  async function runEvening() {
    if (phase !== "idle") return;
    cancelled.current = false;
    setMode("evening");
    setNotice("");
    setHeard("");

    const transcript = [];
    let turn = 0;
    let text = "";
    try {
      while (true) {
        setPhase("thinking");
        const res = await chat({ person_id: PERSON_ID, text, mode: "evening", turn });
        transcript.push({ role: "dory", text: res.reply });
        setReply({ text: res.reply, status: "evening", sources: [] });
        await say(res.reply);
        if (res.done || cancelled.current) break;

        let answer;
        try {
          answer = await getAnswer();
        } catch (e) {
          if (!cancelled.current) setNotice(listenMessage(e.code));
          break;
        }
        if (cancelled.current || !answer) break;
        setHeard(answer);
        transcript.push({ role: "person", text: answer });
        turn += 1;
        text = answer;
      }
      if (transcript.some((line) => line.role === "person")) {
        await finishEvening({ person_id: PERSON_ID, transcript });
      }
    } catch {
      await showOffline();
    } finally {
      setMode("chat");
      setPhase("idle");
    }
  }

  function stopEvening() {
    cancelled.current = true;
    speech.stopAll();
    if (typedResolver.current) {
      typedResolver.current("");
      typedResolver.current = null;
    }
  }

  // ----- morning briefing -----
  async function playBriefing() {
    if (phase !== "idle" || mode !== "chat") return;
    setNotice("");
    setHeard("");
    setPhase("thinking");
    try {
      const res = await getBriefing(PERSON_ID);
      setReply({ text: res.text, status: "briefing", sources: res.sources || [] });
      await say(res.text);
    } catch {
      await showOffline();
    }
  }

  // ----- typed text (backup for voice) -----
  function submitTyped(event) {
    event.preventDefault();
    const text = typed.trim();
    if (!text) return;
    setTyped("");
    if (typedResolver.current) {
      const resolve = typedResolver.current;
      typedResolver.current = null;
      resolve(text);
    } else if (phase === "idle" && mode === "chat") {
      ask(text);
    }
  }

  async function reset() {
    stopEvening();
    try {
      await resetDemo();
    } catch {
      /* ignore */
    }
    setReply({
      text: `Hello, ${PERSON_NAME}. Tap the big button and talk to me.`,
      status: "greeting",
      sources: [],
    });
    setHeard("");
    setNotice("Demo reset.");
  }

  const talkLabel =
    phase === "listening"
      ? "I'm listening"
      : phase === "speaking"
      ? "Tap to stop"
      : phase === "thinking"
      ? "One moment"
      : "Talk to Dory";
  const talkDisabled =
    phase === "thinking" || phase === "typing" || (mode === "evening" && phase !== "listening");
  const firstSource = reply.sources?.find((s) => s.label);

  return (
    <main className="screen" data-phase={phase}>
      <header className="top">
        <span className="wordmark">Dory</span>
        <time className="today">{dateLine()}</time>
      </header>

      <section className="stage" aria-hidden="false">
        <div className="orb" data-phase={phase} aria-hidden="true">
          <span className="ring" />
          <span className="ring" />
          <span className="ring" />
          <span className="core" />
        </div>
        <p className="status">{STATUS_TEXT[phase]}</p>
      </section>

      <section className="words" data-status={reply.status} aria-live="polite">
        {heard && phase !== "idle" && <p className="heard">You said: {heard}</p>}
        <p className="reply">{reply.text}</p>
        {firstSource && <p className="because">{firstSource.label}</p>}
        {reply.status === "unknown" && <p className="chip">Waiting for your family</p>}
        {reply.status === "refused" && <p className="chip">Checked with your caregiver's notes</p>}
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
      </section>

      <section className="controls">
        <button
          className="talk"
          data-phase={phase}
          onClick={talk}
          disabled={talkDisabled || !speech.supported.listen}
          aria-label={talkLabel}
        >
          <MicIcon />
          <span>{talkLabel}</span>
        </button>

        <form className="type" onSubmit={submitTyped}>
          <label htmlFor="typed">
            {speech.supported.listen ? "Or type here" : "Voice is not available. Type here"}
          </label>
          <div className="type-row">
            <input
              id="typed"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              placeholder="Type a question"
            />
            <button type="submit" className="send">
              Send
            </button>
          </div>
        </form>

        {mode === "evening" && (
          <button className="plain" onClick={stopEvening}>
            Done for now
          </button>
        )}

        {DEMO && (
          <div className="demo">
            <button onClick={runEvening} disabled={phase !== "idle"}>
              Start evening chat
            </button>
            <button onClick={playBriefing} disabled={phase !== "idle" || mode !== "chat"}>
              Play morning briefing
            </button>
            <button onClick={reset}>Reset demo</button>
          </div>
        )}
      </section>
    </main>
  );
}
