import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Stats from "./Stats.vue";

// 替身替换整个 API 客户端，避免真实网络/后端依赖。
vi.mock("../api/client", () => ({
  getStats: vi.fn(),
  fetchProfileData: vi.fn(),
}));

import { getStats, fetchProfileData } from "../api/client";

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
});

describe("Stats 空数据引导", () => {
  it("本地无数据时显示引导横幅并自动拉取全量历史（仅一次）", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });

    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("本地暂无该彩种历史数据");
    // bootstrapped 守卫：自动拉取恰好一次
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(1);
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "all"]);
  });

  it("本地已有数据时隐藏横幅且不会自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });

    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).not.toContain("本地暂无该彩种历史数据");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBe(0);
    // 展示统计摘要
    expect(wrapper.text()).toContain("共 10 期");
  });

  it("点击「拉取最新开奖」触发 fetchProfileData('latest')", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const btn = findButton(wrapper, "拉取最新开奖");
    expect(btn).toBeTruthy();
    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await btn!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "latest"]);
  });

  it("拉取成功后展示 fetchMsg 提示", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fullStats(),
    );
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await findButton(wrapper, "拉取最新开奖")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".hint").exists()).toBe(true);
    expect(wrapper.find(".hint").text()).toContain("已抓取");
  });

  it("切换彩种重置引导状态并重新自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyStats(),
    );
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 切换到另一彩种
    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await wrapper.setProps({ profileKey: "dlt" });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const calls = (fetchProfileData as unknown as ReturnType<typeof vi.fn>)
      .mock.calls;
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual(["tok", "dlt", "all"]);
  });

  it("含分组频率时渲染条形图并调用 maxFreq", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      profile_key: "ssq",
      total_records: 10,
      groups: {
        red: {
          key: "red",
          name: "红",
          lo: 1,
          hi: 3,
          count: 3,
          color: "#f00",
          frequency: { "1": 5, "2": 3, "3": 0 },
          hot: [1],
          cold: [3],
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
    });
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".bars").exists()).toBe(true);
    expect(wrapper.findAll(".bar").length).toBe(3);
    expect(wrapper.text()).toContain("热号：1");
    expect(wrapper.text()).toContain("冷号：3");
  });

  it("getStats 失败时显示错误且不自动拉取", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("统计服务不可用"),
    );
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("统计服务不可用");
    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBe(0);
  });

  it("点击横幅「拉取全量历史」触发 fetch('all')", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await findButton(wrapper, "拉取全量历史")!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "all"]);
  });

  it("点击横幅「仅拉取最新」触发 fetch('latest')", async () => {
    (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(emptyStats());
    const wrapper = mount(Stats, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mockClear();
    await findButton(wrapper, "仅拉取最新")!.trigger("click");
    await flushPromises();

    expect(
      (fetchProfileData as unknown as ReturnType<typeof vi.fn>).mock.calls[0],
    ).toEqual(["tok", "ssq", "latest"]);
  });
});
