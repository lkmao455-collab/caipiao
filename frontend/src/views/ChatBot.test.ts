import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import ChatBot from "./ChatBot.vue";

// Mock fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("ChatBot.vue", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders toggle button", () => {
    const wrapper = mount(ChatBot, { props: { token: "t" } });
    expect(wrapper.find(".chat-toggle").exists()).toBe(true);
  });

  it("shows chat window when toggle clicked", async () => {
    const wrapper = mount(ChatBot, { props: { token: "t" } });
    await wrapper.find(".chat-toggle").trigger("click");
    expect(wrapper.find(".chat-window").exists()).toBe(true);
  });

  it("shows welcome message on open", async () => {
    const wrapper = mount(ChatBot, { props: { token: "t" } });
    await wrapper.find(".chat-toggle").trigger("click");
    expect(wrapper.find(".chat-messages").text()).toContain("智能客服");
  });

  it("sends message on enter", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ reply: "测试回复", suggestions: [], action: null }),
    });

    const wrapper = mount(ChatBot, { props: { token: "t" } });
    await wrapper.find(".chat-toggle").trigger("click");

    const input = wrapper.find("input");
    await input.setValue("你好");
    await input.trigger("keyup.enter");

    expect(mockFetch).toHaveBeenCalled();
  });

  it("sends message on button click", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ reply: "测试回复", suggestions: [], action: null }),
    });

    const wrapper = mount(ChatBot, { props: { token: "t" } });
    await wrapper.find(".chat-toggle").trigger("click");

    const input = wrapper.find("input");
    await input.setValue("测试");

    const sendBtn = wrapper.findAll("button").find((b) => b.text() === "发送");
    await sendBtn?.trigger("click");

    expect(mockFetch).toHaveBeenCalled();
  });

  it("renders suggestion buttons", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          reply: "回复",
          suggestions: ["建议1", "建议2"],
          action: null,
        }),
    });

    const wrapper = mount(ChatBot, { props: { token: "t" } });
    await wrapper.find(".chat-toggle").trigger("click");

    const input = wrapper.find("input");
    await input.setValue("问题");
    await input.trigger("keyup.enter");

    await vi.dynamicImportSettled();
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".suggestions").exists()).toBe(true);
  });

  it("closes chat window", async () => {
    const wrapper = mount(ChatBot, { props: { token: "t" } });
    await wrapper.find(".chat-toggle").trigger("click");
    expect(wrapper.find(".chat-window").exists()).toBe(true);

    await wrapper.find(".close-btn").trigger("click");
    expect(wrapper.find(".chat-window").exists()).toBe(false);
  });
});
