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
  pool_cents: number;
  unlocked_cents: number;
  shares_permille: Record<number, number>;
  checkoff_days: Record<number, string[]>;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  habits: () => fetch("/api/habits").then((r) => json<Habit[]>(r)),

  createHabit: (name: string, cue: string) =>
    fetch("/api/habits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, cue }),
    }).then((r) => json<Habit>(r)),

  currentWeek: () => fetch("/api/week/current").then((r) => json<WeekSummary>(r)),

  checkOff: (habitId: number, day?: string) =>
    fetch("/api/checkoffs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ habit_id: habitId, day }),
    }),

  undoCheckOff: (habitId: number, day?: string) =>
    fetch("/api/checkoffs", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ habit_id: habitId, day }),
    }),

  setPool: (poolCents: number) =>
    fetch("/api/week/current/pool", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pool_cents: poolCents }),
    }).then((r) => json<WeekSummary>(r)),
};

export const dollars = (cents: number) =>
  (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
