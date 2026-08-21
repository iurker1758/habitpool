import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionExpired, api, onSessionExpired } from "./api";

// Plain literals rather than real Responses — request() and json() read
// only what these carry.
const res = (type: ResponseType, status: number, body: unknown = null) =>
  ({
    type,
    status,
    ok: status >= 200 && status < 300,
    statusText: "",
    json: () => Promise.resolve(body),
  }) as Response;

// What the browser hands back for the Access login redirect under
// `redirect: "manual"` (measured live in umalab under Access).
const accessRedirect = () => res("opaqueredirect", 0);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("expired-session detection", () => {
  it("throws SessionExpired on an opaqueredirect and notifies the subscriber", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(accessRedirect()));
    const listener = vi.fn();
    const unsubscribe = onSessionExpired(listener);
    try {
      await expect(api.habits()).rejects.toBeInstanceOf(SessionExpired);
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      unsubscribe();
    }
  });

  it("sends every call with redirect: manual, on top of the caller's init", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res("basic", 201));
    vi.stubGlobal("fetch", fetchMock);
    await api.checkOff(7);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkoffs",
      expect.objectContaining({ method: "POST", redirect: "manual" })
    );
  });

  it("leaves real statuses alone — a 404 still throws a plain status error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res("basic", 404)));
    const listener = vi.fn();
    const unsubscribe = onSessionExpired(listener);
    try {
      const failure = await api.habits().catch((e: unknown) => e);
      expect(failure).toBeInstanceOf(Error);
      expect(failure).not.toBeInstanceOf(SessionExpired);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it("passes a rejected fetch (network down) through untouched", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const listener = vi.fn();
    const unsubscribe = onSessionExpired(listener);
    try {
      await expect(api.me()).rejects.toBeInstanceOf(TypeError);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it("stops notifying after unsubscribe", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(accessRedirect()));
    const listener = vi.fn();
    onSessionExpired(listener)();
    await expect(api.me()).rejects.toBeInstanceOf(SessionExpired);
    expect(listener).not.toHaveBeenCalled();
  });
});
