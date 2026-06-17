# 04. Acceptance Tests

This document defines MVP acceptance cases. Implement them as automated tests when feasible.

## A. Import and data quality

### Case A1: valid sample import

Input files:

- `examples/sample_sku_master.csv`
- `examples/sample_sku_params.csv`
- `examples/sample_sku_claims.csv`
- `examples/sample_sku_comments.csv`
- `examples/sample_market_facts.csv`

Expected:

- Project import completes.
- Raw row counts match file counts.
- Data quality report has zero critical errors.
- Each raw record has provenance fields.

### Case A2: missing SKU code

Input: a parameter row with empty `sku_code`.

Expected:

- Import does not crash.
- Data-quality issue with severity `critical` and code `missing_required_field`.

### Case A3: missing parameter value is unknown

Input: raw value `-` or empty.

Expected:

- Normalized value is `unknown`.
- Boolean params are not set to false unless raw value explicitly says no/false/not supported.

## B. Parameter factory

### Case B1: screen size normalization

Input examples:

- `85寸`
- `85 inch`
- `85"`

Expected:

- `param_code=screen_size_inch`
- `normalized_value=85`
- confidence >= 0.9

### Case B2: refresh rate conflict

Input:

- parameter table says `屏幕刷新率=300HZ`
- claim says `4K 170Hz 原生高刷`

Expected:

- Derive `system_refresh_rate_hz=300` and `native_refresh_rate_hz=170`, if rules support both.
- If rules cannot distinguish, create review queue item `param_conflict`.

### Case B3: Mini LED normalization

Input:

- raw param `MINILED=是`
- claim text contains `Mini LED`

Expected:

- `mini_led_flag=true`
- evidence includes parameter evidence and claim evidence.

## C. Claim factory

### Case C1: high brightness claim

Input claim: `5200nits 瞬时峰值亮度，3800nits 稳定峰值亮度`

Expected:

- Extract `instant_peak_brightness_nits=5200` and `sustained_peak_brightness_nits=3800` as derived params.
- Activate `CLAIM_HIGH_BRIGHTNESS_HDR`.

### Case C2: dimming zones

Input claim: `3500 分区 U+Mini LED 光晕控制系统`

Expected:

- Extract `dimming_zones=3500`.
- Activate `CLAIM_FINE_LOCAL_DIMMING` and `CLAIM_MINI_LED_BACKLIGHT`.

### Case C3: service claim separation

Input comment: `安装师傅很专业，服务很好`

Expected:

- Classify as service experience.
- Must not activate product claims such as picture quality, gaming, or eye-care.

## D. Comment topic

### Case D1: senior-friendly

Input comment: `系统操作流畅，界面清晰，老人也能上手`

Expected:

- Topics include `TOPIC_EASE_OF_USE` and `TOPIC_SENIOR_FRIENDLY`.
- Sentiment positive.
- Supports user task `TASK_SENIOR_EASY_USE`.

### Case D2: sports watching

Input comment: `看球赛特别爽，画面不卡`

Expected:

- Topics include `TOPIC_SPORTS_WATCHING` and/or `TOPIC_MOTION_SMOOTHNESS`.
- Supports battlefield `BF_GAMING_SPORTS`.

## E. Task and battlefield scoring

### Case E1: premium picture battlefield

SKU has Mini LED, high brightness, dimming zones, wide color, and positive picture comments.

Expected:

- Task `TASK_PREMIUM_PICTURE_AV` score >= 75.
- Battlefield `BF_PREMIUM_PICTURE` relation = main or secondary.
- Evidence references include params, claims, and comments.

### Case E2: eye-care weak battlefield

SKU has eye-care marketing claim but no parameter or comment evidence.

Expected:

- `BF_FAMILY_EYE_CARE` score below main threshold.
- Output relation = weak or pending verification.
- Result includes low-confidence reason.

## F. Claim value layer

### Case F1: insufficient comparable sample

Claim has fewer than minimum comparable sample count.

Expected:

- Do not output strong premium/price-support conclusion.
- Layer should be `pending_validation` or confidence low.

### Case F2: baseline claim

Claim coverage rate >= 0.7 and PSI/SSI not significant.

Expected:

- Layer = `baseline_threshold`.

## G. Competitor engine

### Case G1: direct competitor

Two SKUs share category, battlefield, price band, channel, size band, and key claims.

Expected:

- Competitor type = direct.
- Evidence card includes price, channel, claims, params, sales, battlefield.

### Case G2: benchmark competitor

One SKU has stronger specs, higher price, stronger sales, and same battlefield.

Expected:

- Competitor type = benchmark.

## H. Runtime export boundary

### Case H1: allowed export files only

Run runtime asset export.

Expected:

- Export package contains whitelist files only.
- It does not contain prompt templates, generation scripts, Gold Set builder code, or cross-category migration templates.
