// Typed client for the HabitPool API. Types mirror backend Pydantic schemas —
// keep them in sync by hand for now (codegen from OpenAPI is a nice v2).

export interface Habit {
  id: number;
  name: string;
  cue: string;
  status: "active" | "graduated" | "archived";
}

export interface WeekSummary {
  start_day: string;
  today: string;
  pool_cents: number;
  unlocked_cents: number;
  shares_permille: Record<number, number>;
  checkoff_days: Record<number, string[]>;
}

// The expired-Access-session signal (issue #23). A plain Error, not a
// status-carrying one: the only thing a caller may do with it is treat it as
// a blip while App surfaces the overlay. The message is user-facing.
export class SessionExpired extends Error {
  constructor() {
    super("session expired — sign in to keep working");
    this.name = "SessionExpired";
  }
}

const sessionListeners = new Set<() => void>();

// App subscribes to surface the Session Expired overlay. Returns the
// unsubscribe, so StrictMode's subscribe/cleanup/subscribe stays balanced.
export function onSessionExpired(listener: () => void): () => void {
  sessionListeners.add(listener);
  return () => {
    sessionListeners.delete(listener);
  };
}

// Every /api fetch goes through here. `redirect: "manual"` because an
// expired Cloudflare Access session answers with a login redirect fetch()
// can't follow (cross-origin, CORS-opaque) — manual mode turns it into an
// opaqueredirect the client can recognize (measured live in umalab under
// Access: type "opaqueredirect", status 0, for GET and JSON POST alike).
// The flip side is an invariant: no /api route may ever answer with a
// redirect, or it flashes the session overlay — `app/main.py` routes are
// exact-match and these paths never produce the trailing-slash 307.
// A rejected fetch (network down, abort) passes through untouched.
async function request(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, { ...init, redirect: "manual" });
  if (res.type === "opaqueredirect") {
    for (const listener of sessionListeners) listener();
    throw new SessionExpired();
  }
  return res;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  // The cheapest read in the API; the overlay's Sign In tab and recovery
  // probe both use it.
  me: () => request("/api/me").then((r) => json<{ email: string }>(r)),

  habits: () => request("/api/habits").then((r) => json<Habit[]>(r)),

  createHabit: (name: string, cue: string) =>
    request("/api/habits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, cue }),
    }).then((r) => json<Habit>(r)),

  currentWeek: () => request("/api/week/current").then((r) => json<WeekSummary>(r)),

  checkOff: (habitId: number, day?: string) =>
    request("/api/checkoffs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ habit_id: habitId, day }),
    }),

  undoCheckOff: (habitId: number, day?: string) =>
    request("/api/checkoffs", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ habit_id: habitId, day }),
    }),

  setPool: (poolCents: number) =>
    request("/api/week/current/pool", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pool_cents: poolCents }),
    }).then((r) => json<WeekSummary>(r)),
};

export const dollars = (cents: number) =>
  (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
