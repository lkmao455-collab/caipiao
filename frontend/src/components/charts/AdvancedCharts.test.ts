import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import Chart3D from "./Chart3D.vue";
import AnimatedBarChart from "./AnimatedBarChart.vue";
import InteractiveHeatmap from "./InteractiveHeatmap.vue";

describe("Chart3D.vue", () => {
  it("renders cylinders", () => {
    const wrapper = mount(Chart3D, {
      props: {
        data: [
          { label: "A", value: 10 },
          { label: "B", value: 20 },
        ],
      },
    });
    expect(wrapper.findAll(".cylinder").length).toBe(2);
  });

  it("shows value labels", () => {
    const wrapper = mount(Chart3D, {
      props: {
        data: [{ label: "A", value: 15 }],
      },
    });
    expect(wrapper.text()).toContain("15");
  });

  it("handles empty data", () => {
    const wrapper = mount(Chart3D, {
      props: { data: [] },
    });
    expect(wrapper.findAll(".cylinder").length).toBe(0);
  });
});

describe("AnimatedBarChart.vue", () => {
  it("renders bars", () => {
    const wrapper = mount(AnimatedBarChart, {
      props: {
        data: [
          { label: "A", values: [10, 20] },
          { label: "B", values: [15, 25] },
        ],
        seriesNames: ["Series 1", "Series 2"],
      },
    });
    expect(wrapper.findAll("rect").length).toBeGreaterThanOrEqual(4);
  });

  it("shows series legend", () => {
    const wrapper = mount(AnimatedBarChart, {
      props: {
        data: [{ label: "A", values: [10] }],
        seriesNames: ["Series 1"],
      },
    });
    expect(wrapper.text()).toContain("Series 1");
  });

  it("handles empty data", () => {
    const wrapper = mount(AnimatedBarChart, {
      props: { data: [] },
    });
    expect(wrapper.findAll("rect").length).toBe(0);
  });
});

describe("InteractiveHeatmap.vue", () => {
  it("renders cells", () => {
    const wrapper = mount(InteractiveHeatmap, {
      props: {
        data: [
          [1, 2, 3],
          [4, 5, 6],
        ],
      },
    });
    expect(wrapper.findAll(".cell").length).toBe(6);
  });

  it("shows title", () => {
    const wrapper = mount(InteractiveHeatmap, {
      props: {
        data: [[1, 2]],
        title: "Test Heatmap",
      },
    });
    expect(wrapper.text()).toContain("Test Heatmap");
  });

  it("emits cell-click on click", async () => {
    const wrapper = mount(InteractiveHeatmap, {
      props: {
        data: [[10, 20]],
      },
    });
    await wrapper.find(".cell-group").trigger("click");
    expect(wrapper.emitted("cell-click")).toBeTruthy();
  });

  it("shows x labels", () => {
    const wrapper = mount(InteractiveHeatmap, {
      props: {
        data: [[1, 2]],
        xLabels: ["Col1", "Col2"],
      },
    });
    expect(wrapper.text()).toContain("Col1");
  });
});
