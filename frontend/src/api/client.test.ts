import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  login,
  getStats,
  fetchProfileData,
  generate,
  runBacktest,
  type ProfileStats,
} from "./client";

// 构建一个最小 fetch Response 替身：ok 决定成功/失败，json/text 提供解析。
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

describe("login", () => {
  it("POST /auth/login 并带回填的 token", async () => {
    getFetch().mockResolvedValue(
      makeResponse(true, 200, { access_token: "tok-123" }),
    );
    const token = await login("alice", "pw");
    expect(token).toBe("tok-123");

    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/auth/login");
    expect(init.method).toBe("POST");
    expect(String(init.body)).toContain("username=alice");
    expect(String(init.body)).toContain("password=pw");
  });

  it("失败抛出 '登录失败'", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 401, "bad"));
    await expect(login("a", "b")).rejects.toThrow("登录失败");
  });
});

describe("getStats", () => {
  it("GET /profiles/{key}/stats 并带上 Bearer 头", async () => {
    const stats: ProfileStats = {
      profile_key: "ssq",
      total_records: 42,
      groups: {},
      summary: {},
      odd_even_ratio: [0, 0],
      high_low_ratio: [0, 0],
      sum_statistics: {},
      span: {},
      zone_distribution: {},
      common_pairs: [],
      primary_group: "red",
    };
    getFetch().mockResolvedValue(makeResponse(true, 200, stats));
    const res = await getStats("tok", "ssq");
    expect(res.total_records).toBe(42);

    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/profiles/ssq/stats");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok",
    );
  });

  it("非 2xx 时把响应体作为错误信息抛出", async () => {
    getFetch().mockResolvedValue(makeResponse(false, 500, "boom"));
    await expect(getStats("tok", "ssq")).rejects.toThrow("boom");
  });
});

describe("fetchProfileData", () => {
  it("POST /profiles/{key}/fetch 并发送 mode", async () => {
    getFetch().mockResolvedValue(
      makeResponse(true, 200, {
        profile_key: "ssq",
        mode: "all",
        fetched: 3,
        added: 3,
        total: 3,
        latest: null,
      }),
    );
    const res = await fetchProfileData("tok", "ssq", "all");
    expect(res.fetched).toBe(3);

    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/profiles/ssq/fetch");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ mode: "all" });
  });
});

describe("generate", () => {
  it("POST /generate 并序列化 post_filters", async () => {
    getFetch().mockResolvedValue(
      makeResponse(true, 200, { count: 2, filtered_count: 1, tickets: [] }),
    );
    await generate("tok", "fc3d", "balanced", 2, [
      { name: "odd_even", params: { ratio: 0.5 } },
    ]);
    const [, init] = getFetch().mock.calls[0];
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({
      profile_key: "fc3d",
      strategy_id: "balanced",
      count: 2,
      post_filters: [{ name: "odd_even", params: { ratio: 0.5 } }],
    });
  });
});

describe("runBacktest", () => {
  it("POST /backtest 并带上鉴权头", async () => {
    getFetch().mockResolvedValue(
      makeResponse(true, 200, { batch_id: 7, rounds: [], summary: {} as never }),
    );
    await runBacktest("tok", "ssq", "hot", 5, 10);
    const [url, init] = getFetch().mock.calls[0];
    expect(url).toBe("/backtest");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok",
    );
  });
});
