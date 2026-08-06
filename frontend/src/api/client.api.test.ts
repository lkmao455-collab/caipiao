import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  register,
  listProfiles,
  listStrategies,
  getFilters,
  listBacktests,
  getBacktest,
  deleteBacktest,
  getMe,
  getAdminStats,
  listAdminUsers,
  setUserRole,
  deleteUser,
} from "./client";

function makeResponse(ok: boolean, status: number, body: unknown) {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
});

function getFetch() {
  return globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
}

describe("register", () => {
  it("POST /auth/register", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, {}));
    await register("u", "p");
    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/auth/register");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ username: "u", password: "p" });
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 400, "dup"));
    await expect(register("u", "p")).rejects.toThrow("dup");
  });
});

describe("listProfiles", () => {
  it("GET /profiles 带 Bearer 头", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, [{ key: "ssq" }]));
    const r = await listProfiles("tok");
    expect(r).toEqual([{ key: "ssq" }]);
    expect(getFetch().mock.calls[0][0]).toBe("/profiles");
    expect((getFetch().mock.calls[0][1].headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(listProfiles("tok")).rejects.toThrow("x");
  });
});

describe("listStrategies", () => {
  it("GET /profiles/{key}/strategies", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, [{ id: "a" }]));
    const r = await listStrategies("tok", "ssq");
    expect(r).toEqual([{ id: "a" }]);
    expect(getFetch().mock.calls[0][0]).toBe("/profiles/ssq/strategies");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(listStrategies("tok", "ssq")).rejects.toThrow("x");
  });
});

describe("getFilters", () => {
  it("GET /profiles/{key}/filters", async () => {
    getFetch().mockResolvedValue(
      makeResponse(true, 200, { profile_key: "ssq", available: true, params: [] }),
    );
    const r = await getFilters("tok", "ssq");
    expect(r.available).toBe(true);
    expect(getFetch().mock.calls[0][0]).toBe("/profiles/ssq/filters");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(getFilters("tok", "ssq")).rejects.toThrow("x");
  });
});

describe("listBacktests", () => {
  it("GET /backtest", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, [{ id: 1 }]));
    const r = await listBacktests("tok");
    expect(r).toEqual([{ id: 1 }]);
    expect(getFetch().mock.calls[0][0]).toBe("/backtest");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(listBacktests("tok")).rejects.toThrow("x");
  });
});

describe("getBacktest", () => {
  it("GET /backtest/{id}?kind=", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, { tickets: [] }));
    const r = await getBacktest("tok", 3, "batch");
    expect(r).toEqual({ tickets: [] });
    expect(getFetch().mock.calls[0][0]).toBe("/backtest/3?kind=batch");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(getBacktest("tok", 3, "batch")).rejects.toThrow("x");
  });
});

describe("deleteBacktest", () => {
  it("DELETE /backtest/{id}?kind=", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, {}));
    await deleteBacktest("tok", 3, "batch");
    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/backtest/3?kind=batch");
    expect(init.method).toBe("DELETE");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(deleteBacktest("tok", 3, "batch")).rejects.toThrow("x");
  });
});

describe("getMe", () => {
  it("GET /me", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, { id: "1", username: "u", role: "user" }));
    const r = await getMe("tok");
    expect(r.role).toBe("user");
    expect(getFetch().mock.calls[0][0]).toBe("/me");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(getMe("tok")).rejects.toThrow("x");
  });
});

describe("getAdminStats", () => {
  it("GET /admin/stats", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, { user_count: 2 }));
    const r = await getAdminStats("tok");
    expect(r.user_count).toBe(2);
    expect(getFetch().mock.calls[0][0]).toBe("/admin/stats");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(getAdminStats("tok")).rejects.toThrow("x");
  });
});

describe("listAdminUsers", () => {
  it("GET /admin/users", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, [{ id: "1" }]));
    const r = await listAdminUsers("tok");
    expect(r).toEqual([{ id: "1" }]);
    expect(getFetch().mock.calls[0][0]).toBe("/admin/users");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(listAdminUsers("tok")).rejects.toThrow("x");
  });
});

describe("setUserRole", () => {
  it("PATCH /admin/users/{id}/role", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, { id: "1", role: "admin" }));
    const r = await setUserRole("tok", "1", "admin");
    expect(r.role).toBe("admin");
    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/admin/users/1/role");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ role: "admin" });
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(setUserRole("tok", "1", "admin")).rejects.toThrow("x");
  });
});

describe("deleteUser", () => {
  it("DELETE /admin/users/{id}", async () => {
    getFetch().mockResolvedValue(makeResponse(true, 200, {}));
    await deleteUser("tok", "1");
    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/admin/users/1");
    expect(init.method).toBe("DELETE");
  });
  it("失败抛错", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "x"));
    await expect(deleteUser("tok", "1")).rejects.toThrow("x");
  });
});
