import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Profiles from "./Profiles.vue";

vi.mock("../api/client", () => ({
  listProfiles: vi.fn(),
  listStrategies: vi.fn(),
}));

import { listProfiles, listStrategies } from "../api/client";

const profiles = [
  { key: "ssq", name: "双色球", category: "lottery", subtitle: "", group_keys: [] },
  { key: "fc3d", name: "3D", category: "lottery", subtitle: "", group_keys: [] },
];
const strategies = [
  { id: "balanced", name: "均衡", description: "", configurable: false, config_schema: null },
  { id: "hot", name: "热号", description: "", configurable: false, config_schema: null },
];

beforeEach(() => {
  (listProfiles as unknown as ReturnType<typeof vi.fn>).mockReset();
  (listStrategies as unknown as ReturnType<typeof vi.fn>).mockReset();
  (listProfiles as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(profiles);
  (listStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(strategies);
});

describe("Profiles", () => {
  it("挂载后加载彩种与策略，并默认选中第一个", async () => {
    const wrapper = mount(Profiles, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((listProfiles as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual(["tok"]);
    expect((listStrategies as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "ssq",
    ]);
    expect(wrapper.findAll("select").length).toBe(2);
    expect(wrapper.findAll("option").length).toBe(profiles.length + strategies.length);
  });

  it("点击「下一步：生成」emit selected 携带默认选择", async () => {
    const wrapper = mount(Profiles, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "下一步：生成")!.trigger("click");
    expect(wrapper.emitted("selected")).toBeTruthy();
    expect(wrapper.emitted("selected")![0]).toEqual(["ssq", "balanced"]);
  });

  it("加载失败显示错误", async () => {
    (listProfiles as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("加载失败"));
    const wrapper = mount(Profiles, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("加载失败");
  });

  it("切换彩种重新加载策略", async () => {
    const wrapper = mount(Profiles, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (listStrategies as unknown as ReturnType<typeof vi.fn>).mockClear();
    await wrapper.find("select").setValue("fc3d");
    await flushPromises();
    expect((listStrategies as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "fc3d",
    ]);
  });

  it("策略列表为空时不设默认 strategyId（if 长度分支）", async () => {
    (listStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const wrapper = mount(Profiles, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 没有可选策略，「下一步」按钮应被禁用
    const nextBtn = wrapper
      .findAll("button")
      .find((b) => b.text() === "下一步：生成")!;
    expect(nextBtn.attributes("disabled")).toBeDefined();
  });
});
