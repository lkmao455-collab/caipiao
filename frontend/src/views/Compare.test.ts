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
});
