import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import Login from "./Login.vue";

vi.mock("../api/client", () => ({
  login: vi.fn(),
  register: vi.fn(),
}));

import { login, register } from "../api/client";

beforeEach(() => {
  (login as unknown as ReturnType<typeof vi.fn>).mockReset();
  (register as unknown as ReturnType<typeof vi.fn>).mockReset();
});

async function fill(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('input[placeholder="用户名"]').setValue("alice");
  await wrapper.find('input[placeholder="密码"]').setValue("pw");
}

describe("Login", () => {
  it("登录成功 emit authed", async () => {
    (login as unknown as ReturnType<typeof vi.fn>).mockResolvedValue("tok-xyz");
    const wrapper = mount(Login);
    await fill(wrapper);
    await wrapper.find('button:not([type])').trigger("click"); // 登录
    await new Promise((r) => setTimeout(r, 0));

    expect((login as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "alice",
      "pw",
    ]);
    expect(wrapper.emitted("authed")).toBeTruthy();
    expect(wrapper.emitted("authed")![0]).toEqual(["tok-xyz"]);
  });

  it("登录失败显示错误", async () => {
    (login as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("登录失败"));
    const wrapper = mount(Login);
    await fill(wrapper);
    await wrapper.findAll("button").find((b) => b.text() === "登录")!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));

    expect(wrapper.find(".error").exists()).toBe(true);
    expect(wrapper.text()).toContain("登录失败");
  });

  it("注册并登录：先 register 再 login", async () => {
    (register as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    (login as unknown as ReturnType<typeof vi.fn>).mockResolvedValue("tok-2");
    const wrapper = mount(Login);
    await fill(wrapper);
    await wrapper.findAll("button").find((b) => b.text() === "注册并登录")!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));

    expect((register as unknown as ReturnType<typeof vi.fn>).mock.calls[0]).toEqual([
      "alice",
      "pw",
    ]);
    expect((login as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
    expect(wrapper.emitted("authed")![0]).toEqual(["tok-2"]);
  });

  it("注册失败显示错误", async () => {
    (register as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("用户已存在"));
    const wrapper = mount(Login);
    await fill(wrapper);
    await wrapper.findAll("button").find((b) => b.text() === "注册并登录")!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));

    expect(wrapper.text()).toContain("用户已存在");
  });
});
