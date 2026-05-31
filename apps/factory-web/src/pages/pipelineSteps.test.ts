import { describe, expect, it } from "vitest";
import { pipelineSteps, sampleFiles } from "./pipelineSteps";

describe("CatForge 前端配置", () => {
  it("保留 MVP 所需流水线步骤", () => {
    expect(pipelineSteps.map((step) => step.key)).toEqual([
      "generate_params",
      "generate_claims",
      "generate_comment_topics",
      "score_tasks_battlefields",
      "calculate_market_metrics",
      "build_review_queue"
    ]);
  });

  it("提供五类样例数据导入入口", () => {
    expect(sampleFiles).toHaveLength(5);
    expect(sampleFiles.map((file) => file.file_type)).toContain("market_fact");
  });
});

