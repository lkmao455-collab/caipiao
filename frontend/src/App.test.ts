import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import App from "./App.vue";

vi.mock("./api/client", () => ({
  getMe: vi.fn(),
  listProfiles: vi.fn(),
  listStrategies: vi.fn(),
  getStats: vi.fn(),
  getFilters: vi.fn(),
  getAdminStats: vi.fn(),
  listAdminUsers: vi.fn(),
  listBacktests: vi.fn(),
  getBacktest: vi.fn(),
  deleteBacktest: vi.fn(),
  generate: vi.fn(),
  runBacktest: vi.fn(),
  fetchProfileData: vi.fn(),
  register: vi.fn(),
  login: vi.fn(),
}));

import {
  getMe,
  listProfiles,
  listStrategies,
  getStats,
  getFilters,
  getAdminStats,
  listAdminUsers,
  listBacktests,
  login,
} from "./api/client";

const statsMock = {
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

const profile = { key: "ssq", name: "双色球", category: "lottery", subtitle: "", group_keys: [] };
const strategy = { id: "balanced", name: "均衡", description: "", configurable: false, config_schema: null };

beforeEach(() => {
  const store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = String(v);
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  });
  (getMe as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    id: "1",
    username: "me",
    role: "user",
    created_at: "",
  });
  (listProfiles as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([profile]);
  (listStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([strategy]);
  (getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(statsMock);
  (getFilters as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    profile_key: "ssq",
    available: false,
    params: [],
  });
  (getAdminStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    user_count: 1,
    admin_count: 0,
    api_key_count: 0,
    total_usage: 0,
  });
  (listAdminUsers as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listBacktests as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (login as unknown as ReturnType<typeof vi.fn>).mockResolvedValue("tok-abc");
});

function tabButtons(wrapper: ReturnType<typeof mount>) {
  return wrapper.find(".tabs").findAll("button");
}
async function clickTab(wrapper: ReturnType<typeof mount>, label: string) {
  await tabButtons(wrapper).find((b) => b.text() === label)!.trigger("click");
  await flushPromises();
  await wrapper.vm.$nextTick();
}

describe("App 外壳", () => {
  it("无 token 时显示登录页", async () => {
    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.text()).toContain("登录 / 注册");
    expect(wrapper.find(".tabs").exists()).toBe(false);
  });

  it("有 token 时直接进入工作区", async () => {
    localStorage.setItem("cp_token", "tok-abc");
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("选择彩种与策略");
  });

  it("登录流程：emit authed 后进入工作区并写入 localStorage", async () => {
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.find('input[placeholder="用户名"]').setValue("alice");
    await wrapper.find('input[placeholder="密码"]').setValue("pw");
    await wrapper.findAll("button").find((b) => b.text() === "登录")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(localStorage.getItem("cp_token")).toBe("tok-abc");
    expect(wrapper.text()).toContain("选择彩种与策略");
  });

  it("退出后回到登录页并清除 token", async () => {
    localStorage.setItem("cp_token", "tok-abc");
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").find((b) => b.text() === "退出")!.trigger("click");
    await wrapper.vm.$nextTick();

    expect(localStorage.getItem("cp_token")).toBeNull();
    expect(wrapper.text()).toContain("登录 / 注册");
  });

  it("选择彩种后切到各 Tab 均正确挂载对应视图", async () => {
    localStorage.setItem("cp_token", "tok-abc");
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 通过 Profiles 的「下一步：生成」完成选择，使 Tabs 出现
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "下一步：生成")!
      .trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".tabs").exists()).toBe(true);

    await clickTab(wrapper, "统计");
    expect(wrapper.text()).toContain("统计分析");

    await clickTab(wrapper, "回测");
    expect(wrapper.text()).toContain("走查式回测");

    await clickTab(wrapper, "过滤");
    expect(wrapper.text()).toContain("后过滤规则");

    await clickTab(wrapper, "对比");
    expect(wrapper.text()).toContain("策略对比");

    await clickTab(wrapper, "生成");
    expect(wrapper.text()).toContain("生成号码");
  });

  it("管理员角色才显示「管理」Tab", async () => {
    localStorage.setItem("cp_token", "tok-abc");
    localStorage.setItem("cp_role", "admin");
    (getMe as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "1",
      username: "me",
      role: "admin",
      created_at: "",
    });
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper
      .findAll("button")
      .find((b) => b.text() === "下一步：生成")!
      .trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(tabButtons(wrapper).some((b) => b.text() === "管理")).toBe(true);
    await clickTab(wrapper, "管理");
    expect(wrapper.text()).toContain("管理后台");
  });

  it("应用后过滤后切换到生成视图（onFiltersApply）", async () => {
    localStorage.setItem("cp_token", "tok-abc");
    (getFilters as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      profile_key: "ssq",
      available: true,
      params: [{ name: "odd_even", type: "int", default: 0.5, min: 0, max: 1, description: "奇偶比" }],
    });
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.vm.$nextTick();

    await wrapper
      .findAll("button")
      .find((b) => b.text() === "下一步：生成")!
      .trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    await clickTab(wrapper, "过滤");
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "应用过滤到生成")!
      .trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("生成号码");
  });

  it("登录后 getMe 失败时 catch 分支将 role 置空且不报错", async () => {
    (getMe as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("鉴权失败"),
    );
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.find('input[placeholder="用户名"]').setValue("alice");
    await wrapper.find('input[placeholder="密码"]').setValue("pw");
    await wrapper.findAll("button").find((b) => b.text() === "登录")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 进入工作区（onAuthed 已设置 token），但 getMe 失败 → role 为空
    expect(wrapper.text()).toContain("选择彩种与策略");
    // role 为空 → 不应出现「管理」Tab 按钮
    expect(
      wrapper.findAll("button").some((b) => b.text() === "管理"),
    ).toBe(false);
  });
});
