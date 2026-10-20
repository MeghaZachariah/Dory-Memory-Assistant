import React, { useState, useEffect } from 'react';

const API_BASE = "http://localhost:8000/api";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("logs");
  const [summaryData, setSummaryData] = useState(null);
  const [facts, setFacts] = useState([]);
  const [logs, setLogs] = useState([]);
  const [questions, setQuestions] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/dashboard/summary`).then(res => res.json()).then(setSummaryData);
    fetch(`${API_BASE}/dashboard/facts`).then(res => res.json()).then(setFacts);
    fetch(`${API_BASE}/dashboard/logs`).then(res => res.json()).then(setLogs);
    fetch(`${API_BASE}/dashboard/questions`).then(res => res.json()).then(setQuestions);
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 font-sans flex flex-col">
      <header className="bg-slate-900 text-white p-6 shadow-md flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-wide">DORY Family Dashboard</h1>
          <p className="text-slate-400 text-sm">Monitoring & Safety Controls for Mum</p>
        </div>
        <div className="flex gap-2">
          <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full text-xs font-semibold">● Lie-Catcher Active</span>
          <span className="px-3 py-1 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-full text-xs font-semibold">● Bot Listening</span>
        </div>
      </header>

      <nav className="bg-white border-b border-slate-200 px-6 flex gap-8">
        {[
          { id: "logs", label: "Dory's Answers (Lie-Catcher)" },
          { id: "facts", label: "Saved Facts (Receipts)" },
          { id: "summary", label: "Today's Overview" },
          { id: "questions", label: "Family Questions" },
          { id: "memory", label: "Memory Book & Meds" }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`py-4 font-semibold text-sm border-b-2 transition-colors ${
              activeTab === tab.id ? "border-amber-600 text-amber-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="flex-1 p-6 max-w-6xl mx-auto w-full">
        {activeTab === "logs" && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-slate-800 mb-4">Live Lie-Catcher Log</h2>
            {logs.map(log => (
              <div key={log.id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex justify-between items-start">
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">{log.timestamp}</p>
                  <p className="font-semibold text-slate-900 text-lg mb-2">"{log.question}"</p>
                  <p className="text-slate-600 bg-slate-50 p-3 rounded-lg text-sm border border-slate-100">
                    <strong className="text-slate-800">Dory answered:</strong> {log.answer}
                  </p>
                </div>
                <div>
                  {log.passed ? (
                    <span className="px-3 py-1 bg-emerald-100 text-emerald-800 text-xs font-bold rounded-full border border-emerald-300">✓ Passed Checker</span>
                  ) : (
                    <span className="px-3 py-1 bg-red-100 text-red-800 text-xs font-bold rounded-full border border-red-300">🛑 Blocked by Checker</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "facts" && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-slate-800 mb-4">Extracted Facts & Source Receipts</h2>
            <div className="grid md:grid-cols-2 gap-4">
              {facts.map(fact => (
                <div key={fact.id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
                  <div>
                    <span className="text-xs font-semibold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-md mb-3 inline-block">Verified Fact #{fact.id}</span>
                    <p className="text-slate-800 font-medium text-base mb-3">{fact.text}</p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs text-slate-500">
                    <strong>Source Quote:</strong> "{fact.source_quote}"
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "summary" && summaryData && (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <h3 className="text-lg font-bold mb-3">Daily AI Briefing Summary</h3>
              <p className="text-slate-700 leading-relaxed bg-amber-50/50 p-4 rounded-lg border border-amber-100">{summaryData.today_summary}</p>
            </div>
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <h3 className="text-lg font-bold mb-3 text-red-600">Caregiver Alerts</h3>
              <ul className="space-y-2">
                {summaryData.alerts.map((alert, idx) => (
                  <li key={idx} className="p-3 bg-red-50 text-red-700 rounded-lg text-sm border border-red-100 font-medium">⚠️ {alert}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {activeTab === "questions" && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-slate-800 mb-4">Ask-the-Family Questions</h2>
            {questions.map(q => (
              <div key={q.id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center">
                <div>
                  <span className="text-xs font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded uppercase">{q.status}</span>
                  <p className="font-semibold text-slate-800 text-lg mt-2">{q.question}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "memory" && (
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm max-w-xl mx-auto">
            <h2 className="text-xl font-bold text-slate-800 mb-4">Add Fact to Memory Book</h2>
            <form onSubmit={e => e.preventDefault()} className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1">New Fact</label>
                <input type="text" placeholder="e.g. Wedding anniversary is June 12" className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"/>
              </div>
              <button className="w-full py-2.5 bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700">Save to Grounded Memory</button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
}