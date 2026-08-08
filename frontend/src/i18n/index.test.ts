import { describe, it, expect, beforeEach, vi } from "vitest";
import { setLocale, getLocale, t, zhCN, enUS } from "./index";

describe("i18n", () => {
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

  it("returns default locale (zh-CN)", () => {
    expect(getLocale()).toBe("zh-CN");
  });

  it("sets and gets locale", () => {
    setLocale("en-US");
    expect(getLocale()).toBe("en-US");
    setLocale("zh-CN");
    expect(getLocale()).toBe("zh-CN");
  });

  it("translates zh-CN correctly", () => {
    setLocale("zh-CN");
    expect(t("common.appTitle")).toBe("彩票号码生成器");
    expect(t("nav.generate")).toBe("生成");
    expect(t("auth.login")).toBe("登录");
  });

  it("translates en-US correctly", () => {
    setLocale("en-US");
    expect(t("common.appTitle")).toBe("Lottery Number Generator");
    expect(t("nav.generate")).toBe("Generate");
    expect(t("auth.login")).toBe("Login");
  });

  it("returns path for missing keys", () => {
    expect(t("nonexistent.key")).toBe("nonexistent.key");
  });

  it("has all required keys", () => {
    const requiredKeys = [
      "common.appTitle",
      "nav.generate",
      "generate.title",
      "stats.title",
      "backtest.title",
      "auth.login",
    ];

    for (const key of requiredKeys) {
      expect(zhCN).toHaveProperty(key);
      expect(enUS).toHaveProperty(key);
    }
  });
});
