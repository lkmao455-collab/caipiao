import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Compare from "./Compare.vue";

vi.mock("../api/client", () => ({
  listStrategies: vi.fn(),
  getStats: vi.fn(),
  generate: vi.fn(),
}));

import { listStrategies, getStats, generate } from "../api/client";

const stats = {
  profile_key: "ssq",
  total_records: 100,
  groups: {
    red: {
      key: "red",
      name: "红",
      lo: 1,
      hi: 33,
      count: 33,
      color: "#f00",
      frequency: { "1": 5, "2": 3 },
      hot: [1],
      cold: [2],
      missing: [],
    },
  },
  summary: {},
  odd_even_ratio: [0, 0],
  high_low_ratio: [0, 0],
  sum_statistics: {},
  span: {},
  zone_distribution: {},
  common_pairs: [],
  primary_group: "red",
};

const strategies = [
  { id: "balanced", name: "均衡", description: "", configurable: false, config_schema: null },
  { id: "hot", name: "热号", description: "", configurable: false, config_schema: null },
];

function tickets(n: number) {
  const arr = Array.from({ length: n }, (_, i) => ({ groups: { red: [i + 1, i + 2, i + 3] } }));
  // 含一个缺少主号组的票，覆盖 primaryNumbers 兜底分支
  arr.push({ groups: { blue: [20, 21, 22] } });
  return arr;
}

beforeEach(() => {
  (listStrategies as unknown as ReturnType<typeof vi.fn>).mockReset();
  (getStats as unknown as ReturnType<typeof vi.fn>).mockReset();
  (generate as unknown as ReturnType<typeof vi.fn>).mockReset();
  (listStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(strategies);
  (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(stats);
  (generate as unknown as ReturnType<typeof vi.fn>).mockImplementation(
    async (_t: string, _k: string, _s: string, count: number) => ({
      count,
      filtered_count: count,
      tickets: tickets(count),
    }),
  );
});

describe("Compare", () => {
  it("挂载加载策略与统计，默认选中首个策略", async () => {
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((listStrategies as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "ssq",
    ]);
    expect(wrapper.findAll('input[type="checkbox"]').length).toBe(2);
  });

  it("比较生成：渲染对比图、历史基线、策略卡片与和值分布", async () => {
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((generate as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
    // 频率分布对比图（GroupedBarChart）
    expect(wrapper.find(".grouped").exists()).toBe(true);
    // 历史频率基线（BarChart）
    expect(wrapper.find(".barchart").exists()).toBe(true);
    // 策略卡片
    expect(wrapper.findAll(".strat-card").length).toBe(1);
    expect(wrapper.text()).toContain("均和值");
  });

  it("选择两个策略时计算重叠度（Jaccard）", async () => {
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const boxes = wrapper.findAll('input[type="checkbox"]');
    await boxes[1].setValue(true); // 选中第二个策略
    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((generate as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
    expect(wrapper.find(".ov-table").exists()).toBe(true);
    expect(wrapper.text()).toContain("Jaccard");
  });

  it("未选择策略时报错", async () => {
    (listStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const wrapper = mount(Compare, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("请至少选择一个策略");
  });

  it("generate 失败时显示错误", async () => {
    (generate as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("生成失败"));
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("生成失败");
  });

  it("切换彩种重置结果并重新加载", async () => {
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".strat-card").length).toBe(1);

    (listStrategies as unknown as ReturnType<typeof vi.fn>).mockClear();
    await wrapper.setProps({ profileKey: "fc3d" });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.findAll(".strat-card").length).toBe(0);
    expect((listStrategies as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "fc3d",
    ]);
  });

  it("无 strategyId 时默认选中首个策略（&& 短路分支）", async () => {
    const wrapper = mount(Compare, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const boxes = wrapper.findAll('input[type="checkbox"]');
    expect(boxes[0].element.checked).toBe(true);
  });

  it("strategyId 不在列表中时回退到首个策略（some 为 false 分支）", async () => {
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "not-exist" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const boxes = wrapper.findAll('input[type="checkbox"]');
    // 回退选中第一个（balanced）
    expect(boxes[0].element.checked).toBe(true);
  });

  it("无策略列表时初始 selected 为空（ss.length 三元 else 分支）", async () => {
    (listStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const wrapper = mount(Compare, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.findAll('input[type="checkbox"]').length).toBe(0);
  });

  it("getStats 失败时进入 load 的 catch 分支", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("统计失败"),
    );
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("统计失败");
  });

  it("primary_group 为空时 lo/hi 与 historicalSeries 走回退分支", async () => {
    // stats 正常返回（保证 strategies 仍加载），但 primary_group 缺失
    // → primaryGroup 为 "" → lo/hi 回退 1/33；historicalSeries 因 primaryGroup 空返回 []
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...stats,
      primary_group: undefined,
    });
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 对比图仍渲染（numbers 由 lo/hi 回退生成）
    expect(wrapper.find(".grouped").exists()).toBe(true);
    // historicalSeries 因 primaryGroup 为空返回 [] → 不额外渲染历史基线 BarChart
    // （每个策略卡片自带一个 sumHistogram BarChart，故 barchart 数量应等于策略卡片数）
    expect(wrapper.findAll(".barchart").length).toBe(
      wrapper.findAll(".strat-card").length,
    );
  });

  it("票无主号组时 primaryNumbers 兜底层级（?? {} / !Array / Array.isArray 分支）", async () => {
    (generate as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async () => ({
        count: 2,
        filtered_count: 2,
        // 第一张无 red 组（走 groups.blue 兜底），第二张完全没有 groups（走 ?? {}）
        tickets: [{ groups: { blue: [1, 2, 3] } }, { other: true }],
      }),
    );
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.findAll(".strat-card").length).toBe(1);
  });

  it("generate 返回空票时各占比回退 0 分支（totalNumbers / sums.length / sumBuckets）", async () => {
    (generate as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async () => ({ count: 0, filtered_count: 0, tickets: [] }),
    );
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    const card = wrapper.find(".strat-card");
    expect(card.exists()).toBe(true);
    // 注数：0；均和值：0.0（sums.length || 1 分支）
    expect(card.text()).toContain("注数：0");
    expect(card.text()).toContain("均和值：0.0");
  });

  it("历史频率总和为 0 时 ||1 回退分支", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...stats,
      groups: {
        red: { ...stats.groups.red, frequency: { "1": 0, "2": 0 } },
      },
    });
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 频率全为 0 但键存在 → historicalSeries.length > 0，仍渲染基线
    expect(wrapper.find(".barchart").exists()).toBe(true);
  });

  it("两策略去重号码均为空时 union 为 0（jaccard 0 分支）", async () => {
    (generate as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async () => ({ count: 1, filtered_count: 1, tickets: [{ groups: {} }] }),
    );
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const boxes = wrapper.findAll('input[type="checkbox"]');
    await boxes[1].setValue(true); // 选中第二个策略
    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    // overlap 表存在，Jaccard 为 0%
    expect(wrapper.find(".ov-table").exists()).toBe(true);
    expect(wrapper.text()).toContain("Jaccard");
    expect(wrapper.text()).toContain("0%");
  });

  it("所有和值相等时 size ||1 回退分支", async () => {
    (generate as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async () => ({
        count: 2,
        filtered_count: 2,
        // 每组号码和值均为 3 → max === min → size 回退为 1
        tickets: [{ groups: { red: [1, 1, 1] } }, { groups: { red: [1, 1, 1] } }],
      }),
    );
    const wrapper = mount(Compare, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "比较生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".grouped").exists()).toBe(true);
    expect(wrapper.find(".strat-card").exists()).toBe(true);
  });
});
