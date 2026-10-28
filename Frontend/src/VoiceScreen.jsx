import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUp, Check, Clock3, Headphones, Heart, Info, LoaderCircle, MessageCircle, Mic, PhoneCall, Play, RotateCcw, Send, Sparkles, Volume2, X } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const SESSION_KEY = 'dory_session';

const STATUS_COPY = {
  idle: { label: 'Ready when you are', detail: 'Tap the microphone, or type below.', tone: 'text-[#61747b]', icon: Mic },
  listening: { label: 'I’m listening', detail: 'Take your time. I’m right here.', tone: 'text-[#c95b4f]', icon: Mic },
  thinking: { label: 'Let me think', detail: 'I’m checking your memory book.', tone: 'text-[#b27a25]', icon: LoaderCircle },
  speaking: { label: 'DORY is speaking', detail: 'You can tap to pause me.', tone: 'text-[#6e8a62]', icon: Volume2 },
  asking_family: { label: 'Asking your family', detail: 'I’ve sent them a gentle question.', tone: 'text-[#7f69a6]', icon: PhoneCall },
};

function buildStarterMessages(personName) {
  return [{ role: 'dory', text: personName ? `Hello ${personName}. I am Dory. I can help you remember your day, look through verified memories, and contact your family when I’m unsure.` : 'I am Dory. I can help you remember your day, look through verified memories, and contact your family when I’m unsure.', time: 'Just now' }];
}

function formatTime() {
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date());
}

function answerFromPayload(payload) {
  if (typeof payload === 'string') return payload;
  return payload?.answer || payload?.response || payload?.message || payload?.text || 'I’m not sure yet, but I can ask your family to help us remember.';
}

function MicButton({ status, onClick }) {
  const state = STATUS_COPY[status];
  const Icon = state.icon;
  const isListening = status === 'listening';
  const isThinking = status === 'thinking';
  const isSpeaking = status === 'speaking';
  const isAsking = status === 'asking_family';

  return (
    <div className="relative flex h-[260px] w-[260px] items-center justify-center sm:h-[300px] sm:w-[300px]">
      <div className={`absolute inset-6 rounded-full border ${isListening ? 'animate-listening-ring border-[#dc7d70] bg-[#f8ded8]' : isAsking ? 'border-[#c8b9e2] bg-[#eee9f8]' : 'border-[#ead7ae] bg-[#fbf2df]'}`} />
      <div className={`absolute inset-11 rounded-full border border-dashed ${isListening ? 'border-[#e8a096]' : 'border-[#dfc98f]'}`} />
      <button
        type="button"
        onClick={onClick}
        aria-label={isListening ? 'Stop listening' : 'Talk to DORY'}
        className={`relative z-10 flex h-40 w-40 items-center justify-center rounded-full border-[10px] border-[#fffaf1] shadow-[0_18px_42px_rgba(114,79,34,.18)] transition-all duration-300 hover:scale-[1.03] active:scale-[.97] sm:h-44 sm:w-44 ${isListening ? 'bg-[#d86d62] text-white shadow-[0_0_0_14px_rgba(216,109,98,.16)]' : isThinking ? 'bg-[#e7ae4b] text-[#684715]' : isSpeaking ? 'bg-[#87a277] text-white' : isAsking ? 'bg-[#9b88c3] text-white' : 'animate-soft-breathe bg-[#f1c56f] text-[#563e1c]'}`}
      >
        {isThinking ? <LoaderCircle size={54} strokeWidth={1.5} className="animate-spin" /> : <Icon size={56} strokeWidth={1.55} />}
        {isListening && <span className="absolute inset-[-17px] rounded-full border-2 border-[#d86d62]/60 animate-listening-ring" />}
      </button>
      {isThinking && <div className="absolute bottom-7 flex gap-1.5" aria-label="DORY is thinking"><span className="h-2.5 w-2.5 rounded-full bg-[#c98828] animate-bob" /><span className="h-2.5 w-2.5 rounded-full bg-[#c98828] animate-bob [animation-delay:150ms]" /><span className="h-2.5 w-2.5 rounded-full bg-[#c98828] animate-bob [animation-delay:300ms]" /></div>}
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[92%] rounded-[24px] px-5 py-4 sm:max-w-[78%] ${isUser ? 'rounded-br-md bg-[#1f3346] text-white' : 'rounded-bl-md border border-[#e8decd] bg-[#fffaf1] text-[#263b4e] shadow-[0_6px_20px_rgba(88,66,33,.05)]'}`}>
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.18em] opacity-55">
          {isUser ? 'You' : 'DORY'} <span className="normal-case tracking-normal">· {message.time}</span>
        </div>
        <p className="mt-2 text-[1.08rem] leading-7 sm:text-[1.15rem]">{message.text}</p>
        {!isUser && <div className="mt-3 flex items-center gap-2 text-xs font-semibold text-[#789071]"><Check size={14} /> Grounded in your memory book</div>}
      </div>
    </div>
  );
}

export default function VoiceScreen({ personId = '', personName = '', onUnknown }) {
  const [status, setStatus] = useState('idle');
  const [messages, setMessages] = useState(() => buildStarterMessages(personName));
  const [draft, setDraft] = useState('');
  const [offline, setOffline] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(true);
  const recognitionRef = useRef(null);
  const speakingRef = useRef(null);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSpeechSupported(false);
      return undefined;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => setStatus('listening');
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (transcript) {
        setDraft(transcript);
        void sendMessage(transcript);
      }
    };
    recognition.onerror = () => setStatus('idle');
    recognition.onend = () => setStatus((current) => current === 'listening' ? 'idle' : current);
    recognitionRef.current = recognition;

    return () => {
      recognition.onresult = null;
      recognition.onend = null;
      recognition.stop();
      window.speechSynthesis?.cancel();
    };
  }, []);

  const latestDoryMessage = useMemo(() => [...messages].reverse().find((message) => message.role === 'dory'), [messages]);
  const state = STATUS_COPY[status];

  const speak = (text) => {
    if (!window.speechSynthesis) {
      setStatus('idle');
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.92;
    utterance.pitch = 1.02;
    utterance.onend = () => setStatus('idle');
    utterance.onerror = () => setStatus('idle');
    speakingRef.current = utterance;
    setStatus('speaking');
    window.speechSynthesis.speak(utterance);
  };

  async function sendMessage(messageText) {
    const cleanText = messageText.trim();
    if (!cleanText || status === 'thinking') return;
    setDraft('');
    setOffline(false);
    setMessages((current) => [...current, { role: 'user', text: cleanText, time: formatTime() }]);
    setStatus('thinking');

    try {
      let token = '';
      try { token = JSON.parse(localStorage.getItem(SESSION_KEY) || '{}')?.token || ''; } catch { /* the request will remain unauthenticated */ }
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        // The conversation so far, so Dory can follow it ("no", "what about yesterday?").
        body: JSON.stringify({ person_id: personId, message: cleanText, history: messages.slice(-8).map((m) => ({ speaker: m.role === 'dory' ? 'Dory' : (personName || 'Person'), text: m.text })) }),
      });
      if (!response.ok) throw new Error(`Chat request failed with ${response.status}`);
      const payload = await response.json();
      const answer = answerFromPayload(payload);
      const askingFamily = Boolean(payload?.asking_family || payload?.needs_family || payload?.status === 'asking_family');
      setMessages((current) => [...current, { role: 'dory', text: answer, time: formatTime() }]);
      if (askingFamily) { setStatus('asking_family'); onUnknown?.({ question: cleanText, status: 'Pending' }); }
      else speak(answer);
    } catch {
      const fallback = 'I’m having trouble reaching the family memory book right now. We can try again in a moment, or you can tell me another way.';
      setOffline(true);
      setMessages((current) => [...current, { role: 'dory', text: fallback, time: formatTime() }]);
      setStatus('idle');
    }
  }

  const toggleListening = () => {
    if (status === 'listening') {
      recognitionRef.current?.stop();
      setStatus('idle');
      return;
    }
    if (status === 'speaking') {
      window.speechSynthesis?.cancel();
      setStatus('idle');
      return;
    }
    if (!recognitionRef.current) {
      setOffline(true);
      return;
    }
    try { recognitionRef.current.start(); } catch { setStatus('idle'); }
  };

  const handleQuickAction = (message) => void sendMessage(message);

  return (
    <div className="soft-grid overflow-hidden px-4 pb-5 pt-6 sm:px-7 sm:pt-8 lg:px-10">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e7dece] bg-[#fffaf1]/75 px-4 py-3 text-xs font-semibold text-[#758087] shadow-sm sm:px-5">
        <div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#e9f1e4] text-[#709263]"><Heart size={14} fill="currentColor" /></span> Your calm corner is ready.</div>
        <div className="flex items-center gap-2"><Clock3 size={14} /> {new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())}</div>
      </div>

      <section className="grid gap-7 lg:grid-cols-[minmax(0,1.15fr)_minmax(380px,.85fr)] lg:items-start">
        <div className="rounded-[32px] border border-[#e7dece] bg-[#fffaf1]/80 p-5 shadow-[0_16px_55px_rgba(84,61,29,.07)] sm:p-8 lg:min-h-[650px]">
          <div className="flex items-start justify-between gap-5">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.2em] text-[#b27a25]">Voice Screen</p>
              <h1 className="mt-2 max-w-xl font-display text-4xl leading-[1.05] tracking-[-.045em] text-[#1f3346] sm:text-5xl">{personName ? `Good evening, ${personName}.` : 'Good evening.'}</h1>
              <p className="mt-4 max-w-lg text-base leading-7 text-[#718087]">A little help remembering the day, one gentle question at a time.</p>
            </div>
            <div className="hidden h-12 w-12 items-center justify-center rounded-2xl bg-[#f5e1b5] text-[#92651d] sm:flex"><Sparkles size={22} /></div>
          </div>

          <div className="mt-8 flex flex-wrap gap-2.5">
            <button type="button" onClick={() => handleQuickAction('Start an evening chat with me.')} className="group flex items-center gap-2 rounded-full border border-[#e2c98f] bg-[#fff4d8] px-4 py-2.5 text-sm font-bold text-[#74551e] transition hover:-translate-y-0.5 hover:bg-[#ffedbd]"><MessageCircle size={16} /> Start Evening Chat <ArrowUp size={14} className="rotate-45 opacity-50 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></button>
            <button type="button" onClick={() => handleQuickAction('Please play my morning briefing.')} className="group flex items-center gap-2 rounded-full border border-[#d8e5d2] bg-[#eef5e9] px-4 py-2.5 text-sm font-bold text-[#5f795a] transition hover:-translate-y-0.5 hover:bg-[#e4f0dd]"><Play size={15} fill="currentColor" /> Play Morning Briefing <ArrowUp size={14} className="rotate-45 opacity-50 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></button>
          </div>

          <div className="mt-2 flex flex-col items-center justify-center sm:mt-0 sm:min-h-[345px]">
            <MicButton status={status} onClick={toggleListening} />
            <div className={`-mt-2 text-center ${state.tone}`}>
              <div className="text-lg font-bold">{state.label}</div>
              <div className="mt-1 text-sm text-[#839094]">{state.detail}</div>
            </div>
          </div>

          <div className="mx-auto mt-2 flex max-w-md items-center justify-center gap-2 text-center text-xs font-semibold leading-5 text-[#8a9595]"><Info size={14} className="shrink-0 text-[#b99555]" /> {speechSupported ? 'Voice recognition is ready in this browser.' : 'Voice recognition is not available here, so you can type below.'}</div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[32px] border border-[#e7dece] bg-[#f1e8d8]/75 p-5 sm:p-6">
            <div className="flex items-center justify-between gap-4">
              <div><p className="text-xs font-bold uppercase tracking-[.2em] text-[#b27a25]">Our conversation</p><h2 className="mt-1 text-xl font-bold text-[#1f3346]">I remember what you say.</h2></div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#fffaf1] text-[#6d8e67]"><Headphones size={19} /></div>
            </div>
            <div className="mt-5 max-h-[390px] space-y-3 overflow-y-auto pr-1">{messages.map((message, index) => <MessageBubble key={`${message.time}-${index}`} message={message} />)}</div>
            {latestDoryMessage && <button type="button" onClick={() => speak(latestDoryMessage.text)} className="mt-4 flex items-center gap-2 text-sm font-bold text-[#66805f] transition hover:text-[#405d4a]"><Volume2 size={16} /> Read that again</button>}
          </div>

          <form onSubmit={(event) => { event.preventDefault(); void sendMessage(draft); }} className="rounded-[28px] border border-[#e7dece] bg-[#fffaf1] p-3 shadow-[0_10px_30px_rgba(84,61,29,.06)]">
            <div className="flex items-center gap-2 rounded-[21px] border border-[#e7dece] bg-[#fdf9f1] p-2 pl-4 transition focus-within:border-[#d8b86b] focus-within:ring-4 focus-within:ring-[#f4d99b]/30">
              <input value={draft} onChange={(event) => setDraft(event.target.value)} className="min-w-0 flex-1 bg-transparent py-2 text-base text-[#1f3346] focus:outline-none" aria-label="Type a question for DORY" />
              {draft && <button type="button" onClick={() => setDraft('')} aria-label="Clear text" className="rounded-full p-2 text-[#9ba5a1] hover:bg-[#f1e8d8] hover:text-[#5c6f76]"><X size={16} /></button>}
              <button type="submit" aria-label="Send question" disabled={!draft.trim() || status === 'thinking'} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#1f3346] text-white transition hover:bg-[#2c4960] disabled:cursor-not-allowed disabled:opacity-35"><Send size={18} /></button>
            </div>
            <div className="mt-2 flex items-center justify-between px-2 text-[11px] font-semibold text-[#9aa39e]"><span>Not in the mood to talk? Typing works too.</span><button type="button" onClick={() => setMessages(buildStarterMessages(personName))} className="flex items-center gap-1 hover:text-[#6f7d7d]"><RotateCcw size={12} /> Reset</button></div>
          </form>

          {offline && <div className="flex items-start gap-3 rounded-2xl border border-[#efc6b6] bg-[#fff0ea] px-4 py-3 text-sm leading-5 text-[#934e45]"><Info size={17} className="mt-0.5 shrink-0" /><div><strong className="font-bold">The family memory book is offline.</strong> Your question is safe. Try again when the connection is back.</div></div>}
        </div>
      </section>
    </div>
  );
}
