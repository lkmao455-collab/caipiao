import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Generate from "./Generate.vue";

// 替身替换整个 API 客户端，避免真实网络/后端依赖。
vi.mock("../api/client", () => ({
  getStats: vi.fn(),
  fetchProfileData: vi.fn(),
  generate: vi.fn(),
}));

import { getStats, fetchProfileData, generate } from "../api/client";

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

function fullStats(records = 10) {
  return { ...emptyStats(), total_records: records };
}

const fetchResult = {
  profile_key: "ssq",
  mode: "all",
  fetched: 1,
  added: 1,
  total: 1,
  latest: null,
};

function findButton(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll("button").find((b) => b.text() === label);
}

beforeEach(() => {
  (getStats as unknown as ReturnType<typeof vi.fn>).mockReset();
  (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockReset();
  (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
    fetchResult,
  );
  (generate as unknown as ReturnType<typeof vi.fn>).mockReset();
});

describe("Generate 空数据引导", () => {
  it("本地无数据时显示引导横幅、自动拉取全量历史，且「生成」被禁用", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });

    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("本地暂无该彩种历史数据");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(1);
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "all"]);

    const genBtn = findButton(wrapper, "生成");
    expect(genBtn).toBeTruthy();
    expect(genBtn!.attributes("disabled")).toBeDefined();
  });

  it("本地已有数据时隐藏横幅、「生成」可用，且不会自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });

    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).not.toContain("本地暂无该彩种历史数据");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(0);
    expect(findButton(wrapper, "生成")!.attributes("disabled")).toBeUndefined();
  });

  it("点击「生成」调用 generate 并渲染号码", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    (generate as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      count: 2,
      filtered_count: 1,
      tickets: [{ red: [1, 2, 3] }, { red: [4, 5, 6] }],
    });
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(
      (generate as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "balanced", 5, []]);
    // 两张票被渲染，并展示过滤后数量
    expect(wrapper.findAll(".ticket").length).toBe(2);
    expect(wrapper.text()).toContain("原始 5 注 → 过滤后 1 注");
  });

  it("generate 失败时展示错误信息", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    (generate as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("生成服务不可用"),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".error").exists()).toBe(true);
    expect(wrapper.find(".error").text()).toContain("生成服务不可用");
  });

  it("点击「拉取全量历史」触发 fetchProfileData('all')", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await findButton(wrapper, "拉取全量历史")!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "all"]);
  });

  it("切换彩种/策略重置引导并重新自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await wrapper.setProps({ profileKey: "dlt", strategyId: "hot" });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const calls = (fetchProfileData as unknown as ReturnType<typeof vi.fn>)
      .mock.calls;
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual(["tok", "dlt", "all"]);
  });

  it("携带 postFilters 时传给 generate", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    (generate as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      count: 1,
      filtered_count: 1,
      tickets: [{ red: [1, 2, 3] }],
    });
    const postFilters = [{ name: "odd_even", params: { ratio: 0.5 } }];
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced", postFilters },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "生成")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((generate as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "ssq",
      "balanced",
      5,
      postFilters,
    ]);
    expect(wrapper.find(".hint").text()).toContain("已应用后过滤");
  });

  it("点击横幅「仅拉取最新」触发 fetch('latest')", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await findButton(wrapper, "仅拉取最新")!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "latest"]);
  });

  it("total_records 为 undefined 时 ?? 0 走空分支，仍触发引导", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...emptyStats(),
      total_records: undefined,
    });
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("本地暂无该彩种历史数据");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(1);
  });

  it("getStats 失败时 catch 分支不阻断（不自动拉取）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("统计异常"),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // catch 不抛错；无引导（needsBootstrap 未置 true）→ 不会自动拉取
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBe(0);
  });

  it("拉取失败时在 fetchMsg 显示错误（refresh catch 分支）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("拉取失败"),
    );
    const wrapper = mount(Generate, {
      props: { token: "tok", profileKey: "ssq", strategyId: "balanced" },
    });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await findButton(wrapper, "拉取全量历史")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".hint").text()).toContain("拉取失败");
  });
});
