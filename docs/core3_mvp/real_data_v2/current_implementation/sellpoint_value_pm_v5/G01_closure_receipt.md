# V5-G01 关闭回执

## 结论

`PASSED — V5-G02 ALLOWED`。

205 真实数据已经证明 V5 不需要依赖单一直接 SKU/M14 才能形成参照：375/377 有市场池基线，367 有同预算替代，346 有品牌梯度，312 有强自身价格曲线，327 有至少 5 个 broad synthetic donors。C01-C08 Gold Set 已冻结并可按 source hash 重放。

## G01 对设计的修正

1. broad recall 与 eligible counterfactual 必须分层；
2. M14 raw 84 个 target 但 eligible=0，V5 resolver 必须以多层 fallback 为主能力；
3. 288 个 excluded 初步候选不是已可拓展战场，必须补尺寸/价格市场门槛；
4. 65E7Q 最新 M11C 与 M11D allocation 结构不完全一致，M11D 必须绑定自身 lineage；
5. 合成 donor 覆盖高但 inventory unavailable、promotion 仅 suspect，首版保持观察性；
6. M11D allocation 三项相加回到 6,023 台，明确是既有销量分账而非新增。

## 实时证据

- `healthz={"status":"ok"}`；
- `readyz={"status":"ready","database":"ok"}`；
- 完整探针双跑 SHA-256：`d6c0bd60d9c35cef56cfb275c1a0d0d5375cf400b85b22dcd2f39e2bf1f468d6`；
- cohort manifest：`ae3ea428f5293a9016e2d88ca6e908ae8c4f842af671953aa7d6a1fa3defb450`；
- 所有 DB session 强制 read-only，数据库/205 写入为 0/0。

## 校验与提交

- Python compile 通过；
- coverage/cohort/65E7Q JSON 均通过 `jq empty`；
- `git diff --cached --check` 通过；
- 主提交：`32413611297e753efd7b6673486ef70474508385`；
- 未暂存或修改现有 M12D 质量修复和其他脏工作区文件。

## G02 前置合同

G02 必须冻结 typed schema、broad/eligible 状态机、ExpansionEligibilityGate、synthetic balance/placebo/stability、residual archetype、量价五笔账、PM DTO 和 C01-C08 测试追溯。G02 仍不实现运行代码、不写 205。
