// Functional shell: today's habits + live unlocked money. Deliberately unstyled
// beyond basics — the real design pass is its own step. The optimistic-update
// pattern here (flip the checkbox, then reconcile with the server) is the core
// interaction to keep: the reward tick must feel instant.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, dollars, Habit, onSessionExpired, SessionExpired, WeekSummary } from "./api";

export default function App() {
  const [habits, setHabits] = useState<Habit[]>([]);
  const [week, setWeek] = useState<WeekSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Latched by any /api request answered with the Access login redirect
  // (issue #23). The only way down is a probe that gets past the edge.
  const [sessionExpired, setSessionExpired] = useState(false);
  const [checking, setChecking] = useState(false);
  const probing = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [h, w] = await Promise.all([api.habits(), api.currentWeek()]);
      setHabits(h.filter((x) => x.status !== "archived"));
      setWeek(w);
      setError(null);
    } catch (e) {
      // The overlay owns this case; a backend-down message under it would
      // be the false diagnosis the issue is about.
      if (e instanceof SessionExpired) return;
      setError("Can't reach the backend — is uvicorn running?");
    }
  }, []);

  useEffect(() => onSessionExpired(() => setSessionExpired(true)), []);

  // The overlay stands down only on proof the session is whole: any
  // response that got past the edge, ok or not. A fresh redirect throws
  // SessionExpired and leaves it up; a rejected fetch (network down)
  // reached nothing and proves nothing — standing down on it would drop
  // the user into an app where every request fails.
  const probeSession = useCallback(() => {
    if (probing.current) return;
    probing.current = true;
    setChecking(true);
    void (async () => {
      try {
        await api.me();
      } catch (e) {
        if (e instanceof SessionExpired || e instanceof TypeError) return;
      } finally {
        probing.current = false;
        setChecking(false);
      }
      setSessionExpired(false);
      void refresh();
    })();
  }, [refresh]);

  // Coming back from the sign-in tab is the natural moment the session is
  // whole again, so returning focus doubles as the Retry.
  useEffect(() => {
    if (!sessionExpired) return;
    const onReturn = () => {
      if (document.visibilityState === "visible") probeSession();
    };
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
    return () => {
      window.removeEventListener("focus", onReturn);
      document.removeEventListener("visibilitychange", onReturn);
    };
  }, [sessionExpired, probeSession]);

  useEffect(() => {
    // False positive: refresh() only sets state after awaiting the fetch, but
    // the rule can't see through the useCallback boundary.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  // "Today" is the backend's APP_TIMEZONE date, carried in the summary — the
  // same day a check-off lands on. The browser's clock is never consulted.
  const doneToday = (habitId: number) =>
    (week && week.checkoff_days[habitId]?.includes(week.today)) ?? false;

  const toggle = async (habit: Habit) => {
    const was = doneToday(habit.id);
    try {
      if (was) await api.undoCheckOff(habit.id);
      else await api.checkOff(habit.id);
    } catch (e) {
      // The overlay is already up; the tick is redone by hand after re-auth.
      if (e instanceof SessionExpired) return;
      throw e;
    }
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

      {/* No dismissal — closing it would drop the user into an app where
          every request fails. Sign In opens a relative /api path, where the
          edge runs the Access login; a top-level navigation reaches it only
          because of the navigateFallbackDenylist in vite.config.ts — keep
          them in sync. */}
      {sessionExpired && (
        <div className="session-backdrop">
          <div
            className="session-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="session-title"
          >
            <h2 id="session-title">Session Expired</h2>
            <p>Your login session has expired. Sign in again in a new tab, then come back here.</p>
            <div className="session-actions">
              <a className="session-signin" href="/api/me" target="_blank" rel="noopener">
                Sign In
              </a>
              <button className="session-retry" onClick={probeSession} disabled={checking}>
                {checking ? "Checking…" : "Retry"}
              </button>
            </div>
          </div>
        </div>
      )}

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
        {habits.length === 0 && !error && !sessionExpired && (
          <p>No habits yet — add your first three via the API docs at /docs.</p>
        )}
      </section>
    </main>
  );
}
