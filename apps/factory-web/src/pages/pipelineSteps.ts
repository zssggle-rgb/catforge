export const pipelineSteps = [
  { key: "generate_params", label: "参数归一", description: "生成标准参数和证据链" },
  { key: "generate_claims", label: "卖点映射", description: "识别 Mini LED、高亮、高刷等标准卖点" },
  { key: "generate_comment_topics", label: "评论主题", description: "将评论切分并归入体验主题" },
  { key: "score_tasks_battlefields", label: "任务战场评分", description: "输出用户任务和价值战场关系" },
  { key: "calculate_market_metrics", label: "市场指标", description: "计算覆盖率、PSI、SSI、CPI" },
  { key: "build_review_queue", label: "复核队列", description: "收敛低置信、冲突和高价值 SKU" }
];

export const sampleFiles = [
  { file_path: "examples/sample_sku_master.csv", file_type: "sku_master", label: "SKU 主数据" },
  { file_path: "examples/sample_sku_params.csv", file_type: "sku_param", label: "SKU 参数" },
  { file_path: "examples/sample_sku_claims.csv", file_type: "sku_claim", label: "宣传卖点" },
  { file_path: "examples/sample_sku_comments.csv", file_type: "sku_comment", label: "用户评论" },
  { file_path: "examples/sample_market_facts.csv", file_type: "market_fact", label: "量价事实" }
];

