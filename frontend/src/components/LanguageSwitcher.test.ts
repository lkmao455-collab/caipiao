import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import LanguageSwitcher from "./LanguageSwitcher.vue";

// Mock window.location.reload
const mockReload = vi.fn();
Object.defineProperty(window, "location", {
  value: { reload: mockReload },
  writable: true,
});

beforeEach(() => {
  // Mock localStorage
  const store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
  });
});

describe("LanguageSwitcher.vue", () => {
  it("renders language buttons", () => {
    const wrapper = mount(LanguageSwitcher);
    expect(wrapper.findAll(".lang-btn").length).toBe(2);
  });

  it("shows Chinese button text", () => {
    const wrapper = mount(LanguageSwitcher);
    expect(wrapper.text()).toContain("中文");
  });

  it("shows English button text", () => {
    const wrapper = mount(LanguageSwitcher);
    expect(wrapper.text()).toContain("EN");
  });

  it("triggers reload on language change", async () => {
    const wrapper = mount(LanguageSwitcher);
    const buttons = wrapper.findAll(".lang-btn");
    await buttons[1].trigger("click");
    expect(mockReload).toHaveBeenCalled();
  });
});
