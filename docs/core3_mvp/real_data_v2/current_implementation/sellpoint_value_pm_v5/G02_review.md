# V5-G02 方法、工程与 PM 语言审查

## 结论

`PASSED — G03 IMPLEMENTATION ALLOWED`。

P0：0。P1：0。P2：4，均已写入实现门禁或后续验证，不阻断 G03。

## 方法审查

### 通过

- broad recall 和 eligible effect 明确分层；
- synthetic 有 overlap、balance、effective donors、placebo、leave-one 和不外推；
- 缺库存/完整促销使 causal claim 固定 false；
- high/low 使用 out-of-fold residual，不以原始销量直接定义；
- strict amount 继续只由 V4 强门禁产生；
- M11D allocation 与 gross/net 完全分离；
- cannibalization 不可识别时 net=null。

### P2

1. SMD/权重阈值属于 v1 配置，G04 必须用 C03 合成/真实数据检查是否过严或过松；变更需升版本。
2. placebo percentile 只能决定“是否突出”，不决定 effect 是否存在；schema 已把 gate 与 highlight 分离。

## 工程审查

### 通过

- 复用 V4 context/linkage/pair curve，新增运行文件预算 4；
- schema 均 extra forbid，unknown 显式；
- 核心方法确定性，无 LLM/网络；
- 查询、内存、row cap 和降级路径明确；
- 同一 DTO 驱动全部载体；
- 默认 off、pre-query reject 和旧版回归明确。

### P2

3. out-of-fold regularized baseline 的数值实现必须固定列排序、fold 和线性代数容差；G04 加跨顺序 determinism test。
4. G01 探针 cohort 只保存 aggregate source hashes，不含原始评论；C04/C08 的评论细节断言需使用现有受控 fixture，而不是在测试中联网读取。

## PM 语言审查

### 通过

- 第一屏只回答亮点、价格、销量、已有增强和新拓展；
- 亮点可为空，不强行 Top 3；
- “机会战场”留在 existing；
- 合成差异明确观察性；
- price 与 volume 分列；
- 不输出 WTP/价值棒/内部模块码/工作清单；
- 不用高价证明高价值，不用 M11D 分配证明新增。

## 必须守住的停止条件

- G03 不实现 synthetic/archetype；
- G04 不实现 PM renderer 或 strict amount；
- G05 不修改 M11C taxonomy/production profile；
- G06 不用 synthetic/archetype 生成严格金额；
- G07 不切默认自然语言路由；
- G08 未通过方法/工程/PM 三审不得部署 205。
