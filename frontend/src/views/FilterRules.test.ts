import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import FilterRules from "./FilterRules.vue";

vi.mock("../api/client", () => ({
  getFilters: vi.fn(),
}));

import { getFilters } from "../api/client";

const params = [
  { name: "odd_even", type: "int", default: 0.5, min: 0, max: 1, description: "奇偶比" },
  { name: "only_even", type: "bool", default: false, min: null, max: null, description: "仅偶" },
];

beforeEach(() => {
  (getFilters as unknown as ReturnType<typeof vi.fn>).mockReset();
});

describe("FilterRules", () => {
  it("不可用时提示暂不支持", async () => {
    (getFilters as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      profile_key: "ssq",
      available: false,
      params: [],
    });
    const wrapper = mount(FilterRules, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("该彩种暂不支持后过滤。");
  });

  it("可用时渲染参数，apply 携带启用的参数", async () => {
    (getFilters as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      profile_key: "ssq",
      available: true,
      params,
    });
    const wrapper = mount(FilterRules, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 启用第一个参数
    const checkbox = wrapper.find('input[type="checkbox"]');
    await checkbox.setValue(true);
    await wrapper.findAll("button").find((b) => b.text() === "应用过滤到生成")!.trigger("click");

    const ev = wrapper.emitted("apply");
    expect(ev).toBeTruthy();
    expect(ev![0][0][0]).toEqual({ name: "ssq", params: { odd_even: 0.5 } });
  });

  it("可用但全未启用时仍 emit（空 params）", async () => {
    (getFilters as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      profile_key: "ssq",
      available: true,
      params,
    });
    const wrapper = mount(FilterRules, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();
    await wrapper.findAll("button").find((b) => b.text() === "应用过滤到生成")!.trigger("click");
    expect(wrapper.emitted("apply")![0][0][0]).toEqual({ name: "ssq", params: {} });
  });

  it("加载失败显示错误", async () => {
    (getFilters as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("加载失败"));
    const wrapper = mount(FilterRules, { props: { token: "tok", profileKey: "ssq" } });
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("加载失败");
  });
});
