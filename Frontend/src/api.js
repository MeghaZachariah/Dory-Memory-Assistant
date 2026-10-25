// All calls to the backend live here. When the real backend replaces the mock,
// nothing else in the frontend should need to change (see API_CONTRACT.md).
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

export const chat = (body) => post("/chat", body);
export const getBriefing = (personId) =>
  request(`/briefing/morning?person_id=${encodeURIComponent(personId)}`);
export const finishEvening = (body) => post("/checkin/evening/finish", body);
export const resetDemo = () => post("/demo/reset", {});

// Used by the family dashboard (next task)
export const getDashboard = (personId) => request(`/dashboard/${encodeURIComponent(personId)}`);
export const postFamilyAnswer = (body) => post("/family/answer", body);
export const logMedicine = (body) => post("/med/log", body);
export const addMemoryFact = (body) => post("/memory/fact", body);
