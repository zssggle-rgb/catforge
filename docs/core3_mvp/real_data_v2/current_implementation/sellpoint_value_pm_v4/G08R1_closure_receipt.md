# G08R1 关闭回执：核心合同修复与重新验收通过

## Objective

修复 G08 发现的 B01-B08，重新执行完整本地验收和方法、工程、产品经理业务语言三审；不连接 205、不部署、不切默认路由。

## 结果

`G08R1 completed; acceptance passed; G09 shadow validation allowed`。

## 完成内容

1. lineage 同版本同批次比较规范化 hash，refs 顺序确定；
2. 候选 30 recall / 12 snapshot / 3 per computed role；
3. M11D 只进入样本解释权重，不改销量或购买归因；
4. weekly DB 2001 探针、完整 group 裁剪、超限显式阻断金额；
5. Q5 config v2、200 次确定性 week-cluster bootstrap、LOO 联合门禁、质量加权中心和联合保守区间；
6. pure negative、mixed、not observed 和 lineage conflict 分开；
7. G01 artifact SHA 与 C01-C05 actual payload 回放；
8. 市场空间补齐尺寸档、观察窗口和平台范围，过时职责说明及重复文案已修正。

## 验证回执

- 324 related tests passed；
- 92 V4 tests passed；
- V4 coverage 93%；
- py_compile/Ruff/diff check passed；
- 10,000 rows peak 25.413MB；
- Q5 v2 report P95 0.016519s；
- SQL query count <=20；
- G01-G08 historical artifacts 35/35 matched；
- 方法/工程/PM 三审全部 PASS；
- DB/205/server writes 0/0/0；
- external LLM/network calls 0。

## Commits

- repair contract：`a568e44`；
- lineage/candidate：`73d920b`；
- market cells/M11D weight：`7936acc`；
- experience states：`e3d13e7`；
- Q5 bootstrap contract：`03c4b89`；
- frozen cohorts：`30961e7`；
- PM scope/manifest receipt：`e7536d7`；
- review artifact commit：`ab13a74`；
- 本关闭回执、manifest 和完成状态：本文件所在 closure commit。

## 下一 Goal

`G09 allowed`，仅限 RC、205 影子部署和真实数据验收，feature flag/default route 继续关闭。`G10 denied`，默认路由切换必须由用户单独批准。
