import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import GroupedBarChart from "./GroupedBarChart.vue";

describe("GroupedBarChart 几何与渲染", () => {
  const categories = [1, 2, 3];
  const series = [
    { name: "A", color: "#111", values: [10, 0, 5] },
    { name: "B", color: "#222", values: [20, 4, 0] },
  ];

  it("每个分类、每个序列渲染一个 rect", () => {
    const wrapper = mount(GroupedBarChart, { props: { categories, series } });
    // 3 categories * 2 series = 6 rects
    expect(wrapper.findAll("rect").length).toBe(6);
  });

  it("最大值条高度 = height - pad", () => {
    const wrapper = mount(GroupedBarChart, {
      props: { categories, series, height: 160, pad: 10 },
    });
    const rects = wrapper.findAll("rect");
    // 最大值 20 出现在 series B 的 category 1（索引 ci=0, si=1）
    const maxRect = rects.find(
      (r) =>
        Number(r.attributes("y")) === 10 && Number(r.attributes("height")) === 150,
    );
    expect(maxRect).toBeTruthy();
  });

  it("分类标签按 categories 渲染", () => {
    const wrapper = mount(GroupedBarChart, { props: { categories, series } });
    const labels = wrapper.findAll("text.clabel");
    expect(labels.map((t) => t.text())).toEqual(["1", "2", "3"]);
  });

  it("svg 宽度 = pad*2 + categories*catSlot", () => {
    const wrapper = mount(GroupedBarChart, {
      props: { categories, series, barW: 10, gap: 3, pad: 10 },
    });
    const catSlot = 10 * 2 + 3; // 23
    expect(Number(wrapper.find("svg").attributes("width"))).toBe(10 * 2 + 3 * catSlot);
  });

  it("空序列时 max 回退为 1，矩形高度为零", () => {
    const wrapper = mount(GroupedBarChart, {
      props: { categories: [1], series: [{ name: "A", color: "#111", values: [0] }], height: 160, pad: 10 },
    });
    const rect = wrapper.find("rect");
    expect(Number(rect.attributes("height"))).toBeCloseTo(0, 5);
    expect(Number(rect.attributes("y"))).toBeCloseTo(160, 5);
  });

  it("values 长度不足时缺失项回退为 0（?? 分支）", () => {
    // categories 有 3 项，但 series 的 values 只有 1 项 → s.values[ci] 在 ci>0 时为 undefined
    const wrapper = mount(GroupedBarChart, {
      props: {
        categories: [1, 2, 3],
        series: [{ name: "A", color: "#111", values: [10] }],
        height: 160,
        pad: 10,
      },
    });
    const rects = wrapper.findAll("rect");
    // 第 1 个（ci=0）有值，后两个（ci=1,2）走 ?? 0 分支
    expect(rects.length).toBe(3);
    expect(Number(rects[1].attributes("height"))).toBeCloseTo(0, 5);
    expect(Number(rects[2].attributes("height"))).toBeCloseTo(0, 5);
  });
});
