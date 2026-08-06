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
  runBacktest,
  listBacktests,
  deleteBacktest,
  getBacktest,
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

function backtestRecord(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    created_at: "2024",
    profile_key: "ssq",
    strategy_id: "balanced",
    target_date: "2024-01-01",
    start_date: "2024-01-01",
    end_date: "2024-01-31",
    total_rounds: 5,
    tickets_count: 5,
    total_cost: 10,
    total_fixed_prize: 0,
    float_prize_count: 0,
    hit_count: 1,
    profit: -10,
    kind: "single",
    ...over,
  };
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
  (runBacktest as unknown as ReturnType<typeof vi.fn>).mockReset();
  (listBacktests as unknown as ReturnType<typeof vi.fn>).mockReset();
  (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (deleteBacktest as unknown as ReturnType<typeof vi.fn>).mockReset();
  (getBacktest as unknown as ReturnType<typeof vi.fn>).mockReset();
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

describe("Backtest 回测执行与记录", () => {
  it("运行回测：调用 runBacktest 并展示汇总", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [{ target_date: "2024", issue: "1", matches: {}, hit: true, best_tier: null, round_fixed_prize: 0, round_float_count: 0 }],
      summary: {
        total_rounds: 1,
        hit_count: 1,
        first_ticket_hit_count: 1,
        profit: 0,
        total_cost: 2,
        total_fixed_prize: 0,
        float_prize_count: 0,
        tier_breakdown: {},
      },
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((runBacktest as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "ssq",
      "balanced",
      5,
      20,
    ]);
    expect(wrapper.text()).toContain("盈亏");
  });

  it("运行回测含未命中回合时命中列渲染「—」（三元 else 分支）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [
        { target_date: "2024-01-01", issue: "1", matches: {}, hit: true, best_tier: null, round_fixed_prize: 0, round_float_count: 0 },
        { target_date: "2024-01-02", issue: "2", matches: {}, hit: false, best_tier: null, round_fixed_prize: 0, round_float_count: 0 },
      ],
      summary: {
        total_rounds: 2,
        hit_count: 1,
        first_ticket_hit_count: 1,
        profit: 0,
        total_cost: 2,
        total_fixed_prize: 0,
        float_prize_count: 0,
        tier_breakdown: {},
      },
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 命中回合显示「中」，未命中回合显示「—」
    expect(wrapper.text()).toContain("中");
    expect(wrapper.text()).toContain("—");
  });

  it("展开详情时 getBacktest 失败显示错误（openDetail catch 分支）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([backtestRecord()]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0, hit_count: 0, first_ticket_hit_count: 0, profit: 0,
        total_cost: 0, total_fixed_prize: 0, float_prize_count: 0, tier_breakdown: {},
      },
    });
    (getBacktest as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("详情拉取失败"));
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 先运行一次回测以填充历史记录，历史表格才会出现「详情」按钮
    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "详情")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("详情拉取失败");
  });

  it("回测失败显示错误", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("回测失败"));
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("回测失败");
  });

  it("展开历史记录详情并关闭", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    const record = backtestRecord();
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([record]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0,
        hit_count: 0,
        first_ticket_hit_count: 0,
        profit: 0,
        total_cost: 0,
        total_fixed_prize: 0,
        float_prize_count: 0,
        tier_breakdown: {},
      },
    });
    (getBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      issue: "1",
      total_cost: 2,
      total_fixed_prize: 0,
      float_prize_count: 0,
      profit: -2,
      tickets: [{ ticket_index: 0, groups: { red: [1, 2, 3] }, hits: { red: 1 }, prize_name: "未中奖", prize_amount: null, is_first: true }],
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 先运行回测以填充历史记录，使详情/删除按钮出现
    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "详情")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".detail").exists()).toBe(true);
    expect(wrapper.text()).toContain("回测详情");

    await findButton(wrapper, "关闭")!.trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".detail").exists()).toBe(false);
  });

  it("删除历史记录调用 deleteBacktest 并刷新", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([backtestRecord()]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0,
        hit_count: 0,
        first_ticket_hit_count: 0,
        profit: 0,
        total_cost: 0,
        total_fixed_prize: 0,
        float_prize_count: 0,
        tier_breakdown: {},
      },
    });
    (deleteBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "删除")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect((deleteBacktest as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      1,
      "single",
    ]);
  });

  it("batch 类型详情展示各注位命中期数", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      backtestRecord({ kind: "batch" }),
    ]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0,
        hit_count: 0,
        first_ticket_hit_count: 0,
        profit: 0,
        total_cost: 0,
        total_fixed_prize: 0,
        float_prize_count: 0,
        tier_breakdown: {},
      },
    });
    (getBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      total_rounds: 5,
      first_ticket_hit_count: 1,
      total_fixed_prize: 0,
      float_prize_count: 0,
      profit: -10,
      ticket_index_hits: { "0": 3, "1": 2 },
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    await findButton(wrapper, "详情")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("各注位命中期数");
    expect(wrapper.text()).toContain("0:3");
  });

  it("切换彩种/策略重置引导状态并重新加载", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await wrapper.setProps({ profileKey: "dlt", strategyId: "hot" });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const calls = (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual(["tok", "dlt", "all"]);
  });

  it("修改注数/期数并点击横幅「仅拉取最新」", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const nums = wrapper.findAll('input[type="number"]');
    await nums[0].setValue(7); // 每期注数
    await nums[1].setValue(30); // 回测期数

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await findButton(wrapper, "仅拉取最新")!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "latest"]);
  });
});

describe("Backtest 边界分支", () => {
  it("getStats 缺 total_records 时回退为 0（?? 分支）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...fullStats(),
      total_records: undefined,
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // (s.total_records ?? 0) === 0 为真 -> 触发引导横幅
    expect(wrapper.text()).toContain("本地暂无历史数据");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0][2],
    ).toBe("all");
  });

  it("getStats 失败时进入 catch 且不自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("统计失败"));
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBe(0);
  });

  it("拉取失败进入 refresh 的 catch", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("拉取失败"),
    );
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("拉取失败");
  });

  it("删除失败进入 remove 的 catch", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([backtestRecord()]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0, hit_count: 0, first_ticket_hit_count: 0, profit: 0,
        total_cost: 0, total_fixed_prize: 0, float_prize_count: 0, tier_breakdown: {},
      },
    });
    (deleteBacktest as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("删除失败"));
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    await findButton(wrapper, "删除")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("删除失败");
  });

  it("详情加载中展示 loading，且 ticket 缺 is_first / prize_amount 为数值时走对应分支", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([backtestRecord()]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0, hit_count: 0, first_ticket_hit_count: 0, profit: 0,
        total_cost: 0, total_fixed_prize: 0, float_prize_count: 0, tier_breakdown: {},
      },
    });
    (getBacktest as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        new Promise((res) =>
          setTimeout(
            () =>
              res({
                issue: "1",
                total_cost: 2,
                total_fixed_prize: 0,
                float_prize_count: 0,
                profit: -2,
                tickets: [
                  {
                    ticket_index: 0,
                    groups: { red: [1, 2, 3] },
                    hits: { red: 1 },
                    prize_name: "二等奖",
                    prize_amount: 50,
                    is_first: false,
                  },
                  {
                    ticket_index: 1,
                    groups: { red: [4, 5, 6] },
                    hits: { red: 0 },
                    prize_name: "未中奖",
                    prize_amount: null,
                    is_first: true,
                  },
                ],
              }),
            10,
          ),
        ),
    );
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 点击详情，等待 getBacktest 的延迟 mock 返回（10ms）
    await findButton(wrapper, "详情")!.trigger("click");
    await new Promise((r) => setTimeout(r, 20));
    await flushPromises();
    await wrapper.vm.$nextTick();

    const rows = wrapper.findAll(".tickets tbody tr");
    expect(rows.length).toBe(2);
    // 首条 ticket：is_first 为 false → 不渲染「（首注）」；prize_amount 为数值 → 直接展示
    const firstCells = rows[0].findAll("td");
    expect(firstCells[0].text()).not.toContain("（首注）");
    // 第 5 列（奖金）分支：prize_amount 非 null 时走 else 分支
    expect(firstCells[4].text()).toBe("50");
    // 第二条 ticket：is_first 为 true → 渲染「（首注）」；prize_amount 为 null → 走 '浮动' 分支
    const secondCells = rows[1].findAll("td");
    expect(secondCells[0].text()).toContain("（首注）");
    expect(secondCells[4].text()).toBe("浮动");
  });

  it("详情数据缺 tickets 时回退为空数组（|| 分支）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([backtestRecord()]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0, hit_count: 0, first_ticket_hit_count: 0, profit: 0,
        total_cost: 0, total_fixed_prize: 0, float_prize_count: 0, tier_breakdown: {},
      },
    });
    (getBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      issue: "1",
      total_cost: 2,
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    await findButton(wrapper, "详情")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".detail").exists()).toBe(true);
  });

  it("batch 类型历史记录展示起止日期区间", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(fullStats());
    (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      backtestRecord({ kind: "batch" }),
    ]);
    (runBacktest as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      batch_id: 1,
      rounds: [],
      summary: {
        total_rounds: 0, hit_count: 0, first_ticket_hit_count: 0, profit: 0,
        total_cost: 0, total_fixed_prize: 0, float_prize_count: 0, tier_breakdown: {},
      },
    });
    const wrapper = mount(Backtest, { props });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "运行回测")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("2024-01-01 ~ 2024-01-31");
  });
});
