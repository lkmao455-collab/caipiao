import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import BarChart from "./BarChart.vue";

describe("BarChart 几何与渲染", () => {
  const items = [
    { label: "A", value: 10 },
    { label: "B", value: 20 },
    { label: "C", value: 5 },
  ];

  it("每个 item 渲染一个 rect，并按比例计算高度", () => {
    const wrapper = mount(BarChart, {
      props: { items, height: 120, pad: 10, slot: 18, color: "#1976D2" },
    });
    const rects = wrapper.findAll("rect");
    expect(rects.length).toBe(3);

    // 最大值 20 → 高度 = height - pad = 110
    const maxRect = rects[1];
    expect(Number(maxRect.attributes("height"))).toBeCloseTo(110, 5);
    expect(Number(maxRect.attributes("y"))).toBeCloseTo(10, 5);

    // 值 10（一半）→ 高度 55
    expect(Number(rects[0].attributes("height"))).toBeCloseTo(55, 5);
  });

  it("svg 宽度 = pad*2 + items.length*slot", () => {
    const wrapper = mount(BarChart, {
      props: { items, height: 120, pad: 10, slot: 18 },
    });
    const svg = wrapper.find("svg");
    expect(Number(svg.attributes("width"))).toBe(10 * 2 + 3 * 18);
  });

  it("标签文本按 item.label 渲染", () => {
    const wrapper = mount(BarChart, { props: { items } });
    const labels = wrapper.findAll("text.blabel");
    expect(labels.map((t) => t.text())).toEqual(["A", "B", "C"]);
  });

  it("item 自带 color 优先于默认 color", () => {
    const wrapper = mount(BarChart, {
      props: {
        items: [
          { label: "A", value: 5 },
          { label: "B", value: 5, color: "#ff0000" },
        ],
        color: "#1976D2",
      },
    });
    const rects = wrapper.findAll("rect");
    expect(rects[0].attributes("fill")).toBe("#1976D2");
    expect(rects[1].attributes("fill")).toBe("#ff0000");
  });

  it("空 items 时不渲染 rect，宽度仅含 padding", () => {
    const wrapper = mount(BarChart, {
      props: { items: [], pad: 10, slot: 18 },
    });
    expect(wrapper.findAll("rect").length).toBe(0);
    expect(Number(wrapper.find("svg").attributes("width"))).toBe(20);
  });

  it("全为 0 时 max 回退为 1，条形高度归零", () => {
    const wrapper = mount(BarChart, {
      props: { items: [{ label: "A", value: 0 }], height: 120, pad: 10 },
    });
    const rect = wrapper.find("rect");
    expect(Number(rect.attributes("height"))).toBeCloseTo(0, 5);
    expect(Number(rect.attributes("y"))).toBeCloseTo(120, 5);
  });
});
