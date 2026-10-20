import React, { useState, useEffect, useRef } from 'react';

const API_BASE = "http://localhost:8000/api";

export default function VoiceScreen() {
  const [status, setStatus] = useState("Idle");
  const [transcript, setTranscript] = useState("");
  const [lastAnswer, setLastAnswer] = useState("");
  const [textInput, setTextInput] = useState("");
  
  const recognitionRef = useRef(null);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => setStatus("Listening");
      recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        setTranscript(text);
        handleSendText(text);
      };
      recognition.onerror = () => setStatus("Idle");
      recognition.onend = () => {
        if (status === "Listening") setStatus("Idle");
      };
      recognitionRef.current = recognition;
    }
  }, []);

  const speakText = (text, onEndCallback) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.9;
      utterance.onstart = () => setStatus("Speaking");
      utterance.onend = () => {
        setStatus("Idle");
        if (onEndCallback) onEndCallback();
      };
      window.speechSynthesis.speak(utterance);
    } else {
      setStatus("Idle");
    }
  };

  const handleMicClick = () => {
    if (status === "Listening") {
      recognitionRef.current?.stop();
    } else if (status === "Idle") {
      setTranscript("");
      recognitionRef.current?.start();
    }
  };

  const handleSendText = async (inputText) => {
    const query = inputText || textInput;
    if (!query) return;

    setStatus("Thinking");
    setTextInput("");

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_input: query })
      });
      const data = await res.json();
      setLastAnswer(data.answer);
      if (data.status === "unknown") {
        setStatus("Asking your family");
      }
      speakText(data.answer);
    } catch (err) {
      const fallback = "I am having a little trouble connecting right now, but I have messaged your family for you.";
      setLastAnswer(fallback);
      speakText(fallback);
    }
  };

  return (
    <div className="min-h-screen bg-amber-50 text-slate-800 flex flex-col justify-between p-6 md:p-12 font-sans">
      <header className="flex justify-between items-center border-b border-amber-200 pb-4">
        <h1 className="text-4xl font-extrabold tracking-wide text-amber-900">DORY</h1>
        <div className="flex gap-3">
          <button onClick={() => handleSendText("Start evening chat")} className="px-4 py-2 bg-amber-200 hover:bg-amber-300 text-amber-900 rounded-lg text-sm font-semibold shadow-sm">
            Start Evening Chat
          </button>
          <button onClick={() => handleSendText("Play morning briefing")} className="px-4 py-2 bg-amber-200 hover:bg-amber-300 text-amber-900 rounded-lg text-sm font-semibold shadow-sm">
            Play Morning Briefing
          </button>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center max-w-3xl mx-auto w-full text-center my-8">
        <div className="mb-8">
          <span className={`inline-block px-6 py-2 rounded-full text-xl font-bold ${
            status === "Listening" ? "bg-red-500 text-white animate-pulse" :
            status === "Thinking" ? "bg-amber-400 text-slate-900 animate-bounce" :
            status === "Speaking" ? "bg-emerald-600 text-white" :
            status === "Asking your family" ? "bg-blue-600 text-white" :
            "bg-amber-200 text-amber-900"
          }`}>
            {status === "Idle" ? "Tap microphone to talk" : status}
          </span>
        </div>

        <div className="w-full bg-white rounded-3xl p-8 shadow-sm border border-amber-200/60 min-h-[180px] flex items-center justify-center mb-8">
          <p className="text-3xl md:text-4xl font-medium leading-relaxed text-slate-800">
            {lastAnswer || transcript || "Hello! What would you like to know about today?"}
          </p>
        </div>

        <button
          onClick={handleMicClick}
          className={`w-36 h-36 rounded-full flex items-center justify-center shadow-lg transition-transform active:scale-95 ${
            status === "Listening" ? "bg-red-500 text-white ring-8 ring-red-200" : "bg-amber-600 text-white hover:bg-amber-700"
          }`}
          aria-label="Microphone Button"
        >
          <svg className="w-16 h-16" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"/>
          </svg>
        </button>
      </main>

      <footer className="max-w-2xl mx-auto w-full pt-4">
        <form onSubmit={(e) => { e.preventDefault(); handleSendText(); }} className="flex gap-2">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Type your question here..."
            className="flex-1 px-5 py-3 rounded-xl border border-amber-300 text-lg focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
          />
          <button type="submit" className="px-6 py-3 bg-slate-800 text-white font-semibold rounded-xl hover:bg-slate-900">
            Ask
          </button>
        </form>
      </footer>
    </div>
  );
}