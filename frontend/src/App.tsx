// Functional shell: today's habits + live unlocked money. Deliberately unstyled
// beyond basics — the real design pass is its own step. The optimistic-update
// pattern here (flip the checkbox, then reconcile with the server) is the core
// interaction to keep: the reward tick must feel instant.
import { useCallback, useEffect, useState } from "react";
import { api, dollars, Habit, WeekSummary } from "./api";

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function App() {
  const [habits, setHabits] = useState<Habit[]>([]);
  const [week, setWeek] = useState<WeekSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [h, w] = await Promise.all([api.habits(), api.currentWeek()]);
      setHabits(h.filter((x) => x.status !== "archived"));
      setWeek(w);
      setError(null);
    } catch (e) {
      setError("Can't reach the backend — is uvicorn running?");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const doneToday = (habitId: number) =>
    week?.checkoff_days[habitId]?.includes(todayISO()) ?? false;

  const toggle = async (habit: Habit) => {
    const was = doneToday(habit.id);
    if (was) await api.undoCheckOff(habit.id);
    else await api.checkOff(habit.id);
    await refresh(); // v1: refetch; optimistic local update is a nice upgrade
  };

  const pct =
    week && week.pool_cents > 0
      ? Math.round((week.unlocked_cents / week.pool_cents) * 100)
      : 0;

  return (
    <main className="app">
      <h1>HabitPool</h1>

      {error && <p className="error">{error}</p>}

      {week && (
        <section className="pool">
          <div className="unlocked">{dollars(week.unlocked_cents)}</div>
          <div className="pool-label">
            unlocked of {dollars(week.pool_cents)} · {pct}%
          </div>
          <progress max={100} value={pct} />
        </section>
      )}

      <section>
        <h2>Today</h2>
        <ul className="habits">
          {habits.map((h) => (
            <li key={h.id}>
              <label>
                <input
                  type="checkbox"
                  checked={doneToday(h.id)}
                  onChange={() => toggle(h)}
                />
                <span>
                  {h.name}
                  {h.cue && <em className="cue">{h.cue}</em>}
                </span>
              </label>
            </li>
          ))}
        </ul>
        {habits.length === 0 && !error && (
          <p>No habits yet — add your first three via the API docs at /docs.</p>
        )}
      </section>
    </main>
  );
}
