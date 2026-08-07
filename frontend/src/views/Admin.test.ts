import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Admin from "./Admin.vue";

vi.mock("../api/client", () => ({
  getAdminStats: vi.fn(),
  listAdminUsers: vi.fn(),
  getMe: vi.fn(),
  setUserRole: vi.fn(),
  deleteUser: vi.fn(),
  getCacheStats: vi.fn(),
  clearCache: vi.fn(),
}));

import { getAdminStats, listAdminUsers, getMe, setUserRole, deleteUser, getCacheStats, clearCache } from "../api/client";

const me = { id: "1", username: "me", role: "admin", created_at: "2024" };
const users = [
  me,
  { id: "2", username: "bob", role: "user", created_at: "2024" },
];

beforeEach(() => {
  vi.stubGlobal("confirm", vi.fn(() => true));
  (getAdminStats as unknown as ReturnType<typeof vi.fn>).mockReset();
  (listAdminUsers as unknown as ReturnType<typeof vi.fn>).mockReset();
  (getMe as unknown as ReturnType<typeof vi.fn>).mockReset();
  (setUserRole as unknown as ReturnType<typeof vi.fn>).mockReset();
  (deleteUser as unknown as ReturnType<typeof vi.fn>).mockReset();
  (getCacheStats as unknown as ReturnType<typeof vi.fn>).mockReset();
  (clearCache as unknown as ReturnType<typeof vi.fn>).mockReset();
  (getAdminStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    user_count: 5,
    admin_count: 1,
    api_key_count: 2,
    total_usage: 100,
  });
  (listAdminUsers as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(users);
  (getMe as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(me);
  (getCacheStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    memory_cache_count: 0,
    engine_cache_count: 0,
    redis_available: false,
  });
});

describe("Admin", () => {
  it("挂载加载统计与用户列表", async () => {
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("用户：5");
    expect(wrapper.findAll("tbody tr").length).toBe(2);
    // 当前用户按钮禁用
    const meRow = wrapper.findAll("tbody tr")[0];
    expect(meRow.findAll("button")[0].attributes("disabled")).toBeDefined();
  });

  it("刷新按钮重新加载", async () => {
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    (getAdminStats as unknown as ReturnType<typeof vi.fn>).mockClear();
    await wrapper.findAll("button").find((b) => b.text() === "刷新")!.trigger("click");
    await flushPromises();
    expect((getAdminStats as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it("修改角色调用 setUserRole 并更新列表", async () => {
    (setUserRole as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "2",
      username: "bob",
      role: "admin",
      created_at: "2024",
    });
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const bobRow = wrapper.findAll("tbody tr")[1];
    await bobRow.findAll("button").find((b) => b.text() === "设为管理员")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((setUserRole as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "2",
      "admin",
    ]);
    expect(wrapper.findAll("tbody tr")[1].text()).toContain("admin");
  });

  it("删除用户（确认）调用 deleteUser 并从列表移除", async () => {
    (deleteUser as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const bobRow = wrapper.findAll("tbody tr")[1];
    await bobRow.findAll("button").find((b) => b.text() === "删除")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();

    expect((deleteUser as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual(["tok", "2"]);
    expect(wrapper.findAll("tbody tr").length).toBe(1);
  });

  it("加载失败显示错误", async () => {
    (getAdminStats as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("无权限"));
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("无权限");
  });

  it("getMe 返回 null 时 me?.id 走空分支且按钮可点击", async () => {
    // me 为 null → 模板与处理器中 me?.id 走 short-circuit 分支
    (getMe as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(null);
    (setUserRole as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "2",
      username: "bob",
      role: "admin",
      created_at: "2024",
    });
    (deleteUser as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    // 当前用户行的「（我）」标记不应出现（me 为 null）
    expect(wrapper.text()).not.toContain("（我）");
    // 点击 bob 行「设为管理员」→ 走 me.value?.id 为 undefined 的分支
    const bobRow = wrapper.findAll("tbody tr")[1];
    await bobRow.findAll("button").find((b) => b.text() === "设为管理员")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect((setUserRole as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "tok",
      "2",
      "admin",
    ]);
    // 点击 bob 行「删除」→ remove 内 me.value?.id 为 undefined 分支
    await bobRow.findAll("button").find((b) => b.text() === "删除")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect((deleteUser as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual(["tok", "2"]);
  });

  it("修改角色失败时显示错误", async () => {
    (setUserRole as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("改角色失败"));
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const bobRow = wrapper.findAll("tbody tr")[1];
    await bobRow.findAll("button").find((b) => b.text() === "设为管理员")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("改角色失败");
  });

  it("删除用户失败时显示错误", async () => {
    (deleteUser as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("删用户失败"));
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const bobRow = wrapper.findAll("tbody tr")[1];
    await bobRow.findAll("button").find((b) => b.text() === "删除")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("删用户失败");
  });

  it("confirm 取消时不调用 deleteUser", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    (deleteUser as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const wrapper = mount(Admin, { props: { token: "tok" } });
    await flushPromises();
    await wrapper.vm.$nextTick();

    const bobRow = wrapper.findAll("tbody tr")[1];
    await bobRow.findAll("button").find((b) => b.text() === "删除")!.trigger("click");
    await flushPromises();
    await wrapper.vm.$nextTick();
    expect((deleteUser as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
    expect(wrapper.findAll("tbody tr").length).toBe(2);
  });
});
