# G08R1 修复验收报告

## 结论

`PASSED — G09 SHADOW VALIDATION ALLOWED`。

G08 确认的 B01-B08 已全部修复，并从最终代码状态重新通过 324 项相关回归、93% V4 覆盖率、性能预算、35/35 历史 artifact hash 和方法/工程/PM 三审。

这只恢复 G09 影子验证准入，不代表已经部署 205、已经创建 RC 或已经切换默认路由。

## 交付变化

- Q5 config v2：确定性 week-cluster bootstrap、LOO 联合稳定性、质量加权中心和保守区间；
- lineage：同版本同批次也比较 source hash，authority hash 列表顺序确定；
- 反事实：30 recall / 12 snapshot / 3 per computed role；
- market cells：DB 2001 探针、完整 group 裁剪、超限阻断金额；
- M11D：只作为样本解释权重，不改真实销量或购买归因；
- 用户体验：pure negative、mixed、not observed 和 data conflict 分开；
- frozen cohorts：G01 artifact hash + actual payload C01-C05 回放；
- PM 表：补齐尺寸档、观察窗口和平台范围，修复重复表达；
- 默认关闭、V2 路由和 M12C 旧金额隔离保持不变。

## 验收数字

- 324 related tests passed；
- 92 V4 tests passed；
- V4 schema/service/answer coverage 93%；
- 10,000 rows peak 25.413MB；
- Q5 v2 report P95 0.016519s；
- query count <=20 且候选数量不产生 N+1；
- G01-G08 artifact hash 35/35 matched；
- database/205/server writes：0/0/0；
- external LLM/network calls：0。

## 下一步边界

允许创建 G09 Goal：形成不可变 RC、checksum 和回滚包，在 feature flag 默认关闭下做 205 影子部署，运行 health/ready、65E7Q 和全部 cohort 两次一致性、真实 JSON/Markdown/飞书回读、资源/并发/V2 线上回归和回滚演练。

G09 仍不得进入 G10；默认自然语言路由切换需要用户单独批准。
