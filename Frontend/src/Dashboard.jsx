import { useCallback, useEffect, useState } from "react";
import { PERSON_ID, PERSON_NAME } from "./config";
import { addMemoryFact, getDashboard, logMedicine, postFamilyAnswer } from "./api";
import "./dashboard.css";

const TABS = ["Today", "Dory's answers", "Facts", "Questions", "Memory Book"];

const time = (iso) =>
  iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";

function factBadge(f) {
  if (f.source_type === "person_chat") return `Said by ${PERSON_NAME}`;
  if (f.source_type === "memory_book") return `Memory Book, ${f.confirmed_by}`;
  if (f.source_type === "family_answer") return `Told by ${f.confirmed_by}`;
  return f.source_type;
}

function AnswerBadge({ entry }) {
  if (entry.blocked) return <span className="badge bad">Blocked by checker</span>;
  if (entry.status === "refused") return <span className="badge warn">Medicine rule</span>;
  if (entry.status === "emergency") return <span className="badge bad">Emergency</span>;
  if (entry.status === "unknown") return <span className="badge info">Asked family</span>;
  return <span className="badge ok">Passed</span>;
}

export default function Dashboard() {
  const [tab, setTab] = useState(TABS[0]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await getDashboard(PERSON_ID));
      setError("");
    } catch {
      setError("Can't reach Dory's server. Check that the backend is running.");
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000); // live updates for the demo
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div className="dash">
      <header className="dash-top">
        <h1>Dory <small>for {data?.person.name ?? "..."}</small></h1>
        <nav role="tablist" aria-label="Dashboard sections">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
      </header>

      {error && <p className="banner">{error}</p>}
      {!data && !error && <p>Loading...</p>}

      {data && tab === "Today" && (
        <section>
          <p className="summary">{data.summary}</p>
          <div className="counts">
            {[
              ["Questions asked", data.counts.asked],
              ["Answered by Dory", data.counts.answered_by_dory],
              ["Asked family", data.counts.asked_family],
              ["Blocked by checker", data.counts.blocked],
              ["Medicine rule used", data.counts.refused_medicine],
            ].map(([label, n]) => (
              <div className="count" key={label}><b>{n}</b><span>{label}</span></div>
            ))}
          </div>
          <h2>Needs attention</h2>
          {data.alerts.length === 0 && <p className="muted">Nothing needs attention.</p>}
          <ul className="alerts">
            {data.alerts.map((a, i) => (
              <li key={i} className={`alert ${a.level}`}>{a.text}</li>
            ))}
          </ul>
        </section>
      )}

      {data && tab === "Dory's answers" && (
        <section>
          <p className="muted">Everything Dory said, newest first. Every answer is checked against its sources before it is spoken.</p>
          {data.answers_log.length === 0 && <p>No questions yet.</p>}
          {data.answers_log.map((e) => (
            <article key={e.id} className="row">
              <div className="row-head"><AnswerBadge entry={e} /><span className="muted">{time(e.time)} · {e.model_tier}</span></div>
              <p className="q">"{e.question}"</p>
              {e.blocked && e.draft && <p className="draft">Draft blocked (no source): {e.draft}</p>}
              <p>{e.answer}</p>
              {e.sources.length > 0 && (
                <p className="muted">Sources: {e.sources.map((s) => s.label).join("; ")}</p>
              )}
            </article>
          ))}
        </section>
      )}

      {data && tab === "Facts" && (
        <section>
          <p className="muted">What Dory knows, with the exact words it came from.</p>
          {data.facts.map((f) => (
            <article key={f.id} className="row">
              <div className="row-head"><span className="badge info">{factBadge(f)}</span><span className="muted">{time(f.source_time)}</span></div>
              <p>{f.text}</p>
              {f.source_quote && <p className="quote">"{f.source_quote}"</p>}
            </article>
          ))}
        </section>
      )}

      {data && tab === "Questions" && <Questions questions={data.questions} onDone={load} />}
      {data && tab === "Memory Book" && <MemoryBook meds={data.med_log} onDone={load} />}
    </div>
  );
}

function Questions({ questions, onDone }) {
  const [drafts, setDrafts] = useState({});
  const [by, setBy] = useState("Anu");
  const [msg, setMsg] = useState("");

  async function save(q) {
    try {
      await postFamilyAnswer({ question_id: q.id, answer: drafts[q.id], answered_by: by });
      setMsg("");
      onDone();
    } catch {
      setMsg("Could not save. Only registered family can answer, and each question once.");
    }
  }

  return (
    <section>
      <label className="inline">Answering as <input value={by} onChange={(e) => setBy(e.target.value)} /></label>
      {msg && <p className="banner">{msg}</p>}
      {questions.length === 0 && <p>No questions yet.</p>}
      {questions.map((q) => (
        <article key={q.id} className="row">
          <div className="row-head">
            <span className={`badge ${q.status === "pending" ? "warn" : "ok"}`}>{q.status}</span>
            <span className="muted">Asked {q.asked_to} · {time(q.asked_at)}</span>
          </div>
          <p className="q">"{q.text}"</p>
          {q.status === "pending" ? (
            <div className="form-row">
              <input placeholder="Type the answer" value={drafts[q.id] || ""}
                onChange={(e) => setDrafts({ ...drafts, [q.id]: e.target.value })} />
              <button disabled={!drafts[q.id]?.trim()} onClick={() => save(q)}>Save answer</button>
            </div>
          ) : (
            <p>{q.answer} <span className="muted">(told by {q.answered_by})</span></p>
          )}
        </article>
      ))}
    </section>
  );
}

function MemoryBook({ meds, onDone }) {
  const [fact, setFact] = useState("");
  const [by, setBy] = useState("Anu");
  const [med, setMed] = useState({ medicine: "", time: "", confirmed_by: "Priya (caregiver)" });
  const [msg, setMsg] = useState("");

  async function run(fn, reset) {
    try { await fn(); reset(); setMsg(""); onDone(); }
    catch { setMsg("Could not save. Check the name is a registered family member or caregiver."); }
  }

  return (
    <section>
      {msg && <p className="banner">{msg}</p>}
      <h2>Add to the Memory Book</h2>
      <p className="muted">Facts family type here are the most trusted source.</p>
      <div className="form-row">
        <input placeholder={`e.g. ${PERSON_NAME}'s wedding was on June 12, 1989`} value={fact} onChange={(e) => setFact(e.target.value)} />
        <input className="short" value={by} onChange={(e) => setBy(e.target.value)} aria-label="Added by" />
        <button disabled={!fact.trim()} onClick={() => run(() => addMemoryFact({ text: fact, added_by: by }), () => setFact(""))}>Add fact</button>
      </div>

      <h2>Medicine log</h2>
      <p className="muted">Only this log is used when {PERSON_NAME} asks about tablets.</p>
      <div className="form-row">
        <input placeholder="Medicine" value={med.medicine} onChange={(e) => setMed({ ...med, medicine: e.target.value })} />
        <input className="short" placeholder="09:00" value={med.time} onChange={(e) => setMed({ ...med, time: e.target.value })} />
        <input className="short" value={med.confirmed_by} onChange={(e) => setMed({ ...med, confirmed_by: e.target.value })} aria-label="Logged by" />
        <button disabled={!med.medicine.trim() || !med.time.trim()}
          onClick={() => run(() => logMedicine(med), () => setMed({ ...med, medicine: "", time: "" }))}>Log it</button>
      </div>
      <ul className="meds">
        {meds.map((m) => <li key={m.id}>{m.date} {m.time} · {m.medicine} <span className="muted">({m.confirmed_by})</span></li>)}
      </ul>
    </section>
  );
}
