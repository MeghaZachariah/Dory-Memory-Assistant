import React, { useState } from 'react';
import VoiceScreen from './VoiceScreen';
import Dashboard from './Dashboard';

export default function App() {
  const [view, setView] = useState('voice');

  return (
    <div>
      <div className="bg-slate-900 text-slate-300 text-xs px-4 py-2 flex justify-between items-center border-b border-slate-800">
        <span>DORY Demo Toggle</span>
        <div className="flex gap-2">
          <button 
            onClick={() => setView('voice')} 
            className={`px-3 py-1 rounded font-semibold ${view === 'voice' ? 'bg-amber-500 text-slate-900' : 'bg-slate-800 hover:bg-slate-700'}`}
          >
            Voice Screen
          </button>
          <button 
            onClick={() => setView('dashboard')} 
            className={`px-3 py-1 rounded font-semibold ${view === 'dashboard' ? 'bg-amber-500 text-slate-900' : 'bg-slate-800 hover:bg-slate-700'}`}
          >
            Family Dashboard
          </button>
        </div>
      </div>

      {view === 'voice' ? <VoiceScreen /> : <Dashboard />}
    </div>
  );
}