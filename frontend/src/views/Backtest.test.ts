import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Backtest from "./Backtest.vue";

// 用替身替换整个 API 客户端，避免真实网络/后端依赖。
vi.mock("../api/client", () => ({
  getStats: vi.fn(),
  fetchProfileData: vi.fn(),
  runBacktest: vi.fn(),
  listBacktests: vi.fn().mockResolvedValue([]),
  deleteBacktest: vi.fn(),
  getBacktest: vi.fn(),
}));

import {
  getStats,
  fetchProfileData,
} from "../api/client";

const props = { token: "tok", profileKey: "ssq", strategyId: "balanced" };

function emptyStats() {
  return {
    profile_key: "ssq",
    total_records: 0,
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
}

function fullStats() {
  return { ...emptyStats(), total_records: 10 };
}

beforeEach(() => {
  (getStats as unknown as ReturnType<typeof vi.fn>).mockReset();
  (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockReset();
  (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    profile_key: "ssq",
    mode: "all",
    fetched: 1,
    added: 1,
    total: 1,
    latest: null,
  });
});

function findButton(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll("button").find((b) => b.text() === label);
}

describe("Backtest 空数据引导", () => {
  it("本地无数据时显示引导横幅并自动拉取全量历史", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Backtest, { props });

    // onMounted -> loadStats -> getStats(0) -> 自动 refresh("all")
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 横幅文案出现
    expect(wrapper.text()).toContain("本地暂无历史数据");
    // 仅自动拉取一次（bootstrapped 守卫）
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(1);
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock
        .calls[0][2],
    ).toBe("all");
    // “运行回测” 在无数据时被禁用
    const runBtn = findButton(wrapper, "运行回测");
    expect(runBtn).toBeTruthy();
    expect(runBtn!.attributes("disabled")).toBeDefined();
  });

  it("本地已有数据时不再显示横幅、也不自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    const wrapper = mount(Backtest, { props });

    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).not.toContain("本地暂无历史数据");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(0);

    const runBtn = findButton(wrapper, "运行回测");
    expect(runBtn!.attributes("disabled")).toBeUndefined();
  });

  it("点击「拉取全量历史」触发 fetchProfileData('all')", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const btn = findButton(wrapper, "拉取全量历史");
    expect(btn).toBeTruthy();
    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await btn!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock
        .calls[0][2],
    ).toBe("all");
  });
});
