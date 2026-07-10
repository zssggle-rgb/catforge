# M12D-G08 全量 TV batch 生成报告

- 生成时间 UTC：2026-07-08T09:44:52.515894+00:00
- 项目：d8d2245b-358b-4a64-95cc-9d7f2341bd26 / TV
- 请求批次：latest
- 读取批次：serving-scope:TV:m00_20260623014631_c8630747,m00_20260619084551_857df63b,m00_20260613004311_d548f6dc
- 入库批次：m00_20260623014631_c8630747
- 版本：m12d_tv_purchase_reason_profile_v0_1_draft
- 写入模式：write
- SKU 数：377
- 状态：success

## 质量统计

- 成功率：1.0000
- 低置信率：0.5332（201）
- 核心成交理由缺失率：0.3183（120）
- 需复核率：1.0000（377）
- 失败数：0
- Profile 记录数：377
- Anchor 记录数：3299

## 锚点分布

- core_payment: 793
- supporting: 2014
- weak_expression: 492

### Top 购买理由

- family_operation_less_friction: 377
- big_screen_cinema_substitution: 348
- av_user_willing_to_pay_for_picture: 347
- gaming_device_fit_reduces_risk: 347
- sports_motion_stability: 347
- same_size_picture_step_up: 287
- living_room_upgrade_one_step: 266
- same_price_core_config_gain: 227
- worth_paying_more_for_experience_upgrade: 221
- picture_upgrade_justifies_price: 220

## 失败清单

- 无

## 低置信清单（前 30）

- TV00009549 康佳 LED32E330CE：status=weak_expression_only，confidence=0.0500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00022396 TCL 55V8M：status=ready_degraded，confidence=0.3667，core=av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00022397 TCL 65V8M：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00023850 酷开 50P31：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025500 红米 L32RA-RA：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025501 红米 L43RA-RA：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025519 红米 L55RA-RA：status=ready_degraded，confidence=0.4167，core=av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00025784 红米 L75MA-RA：status=ready_degraded，confidence=0.4833，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026106 小米 L75MA-SPL：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026228 红米 L55RB-RA：status=ready_degraded，confidence=0.4333，core=low_price_core_experience_intact、same_price_core_config_gain，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026248 红米 L65RB-RA：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026874 创维 32H3GT：status=ready_degraded，confidence=0.3500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026886 VIDDA 32V1FD-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026941 VIDDA 55V1KD-R：status=ready_degraded，confidence=0.4333，core=low_price_core_experience_intact、same_price_core_config_gain，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026983 TCL 75S11-JN：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027055 TCL 75J7K-JN：status=ready_degraded，confidence=0.4833，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027302 VIDDA 65V1Q-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027308 TCL 75T6L：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027332 飞利浦 32PHF6590：status=ready_degraded，confidence=0.4333，core=low_price_core_experience_intact、same_price_core_config_gain，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027351 VIDDA 43V1ND-R：status=ready_degraded，confidence=0.3667，core=worth_paying_more_for_experience_upgrade，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027353 VIDDA 75V1Q-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027378 飞利浦 43PFF6590：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027405 雷鸟 43F295C：status=ready_degraded，confidence=0.3667，core=worth_paying_more_for_experience_upgrade，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027406 雷鸟 50F295C：status=ready_degraded，confidence=0.3667，core=av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027442 红米 L32RA-RAE：status=ready_degraded，confidence=0.3333，core=worth_paying_more_for_experience_upgrade，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027443 红米 L55RB-RAE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027463 红米 L43RB-APE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027475 红米 L55RB-APE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027483 TCL 55V8L PRO：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027485 TCL 65V8L PRO：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs

## 需复核清单（前 30）

- TV00009549 康佳 LED32E330CE：status=weak_expression_only，confidence=0.0500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00022396 TCL 55V8M：status=ready_degraded，confidence=0.3667，core=av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00022397 TCL 65V8M：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00023850 酷开 50P31：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025500 红米 L32RA-RA：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025501 红米 L43RA-RA：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025519 红米 L55RA-RA：status=ready_degraded，confidence=0.4167，core=av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00025784 红米 L75MA-RA：status=ready_degraded，confidence=0.4833，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026064 小米 L55MA-SPL：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade，reasons=missing_or_partial_inputs
- TV00026065 小米 L65MA-SPL：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00026106 小米 L75MA-SPL：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026131 三星 QA85QNX9DAJ：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00026209 小米 L85MA-SPL：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade，reasons=missing_or_partial_inputs
- TV00026228 红米 L55RB-RA：status=ready_degraded，confidence=0.4333，core=low_price_core_experience_intact、same_price_core_config_gain，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026231 索尼 K-75XR70：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00026232 索尼 K-85XR70：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00026248 红米 L65RB-RA：status=ready_degraded，confidence=0.4333，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026857 长虹 85D7H MINI：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade，reasons=missing_or_partial_inputs
- TV00026874 创维 32H3GT：status=ready_degraded，confidence=0.3500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026886 VIDDA 32V1FD-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026941 VIDDA 55V1KD-R：status=ready_degraded，confidence=0.4333，core=low_price_core_experience_intact、same_price_core_config_gain，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00026983 TCL 75S11-JN：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027015 酷开 55P3DGT：status=ready_degraded，confidence=0.5000，core=low_price_core_experience_intact、same_price_core_config_gain、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00027027 小米 L65MB-SP：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00027028 小米 L75MB-SP：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00027029 小米 L85MB-SP：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00027039 小米 L100MB-SP：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00027055 TCL 75J7K-JN：status=ready_degraded，confidence=0.4833，core=same_size_picture_step_up、av_user_willing_to_pay_for_picture，reasons=low_profile_confidence,missing_or_partial_inputs
- TV00027077 酷开 100P3E MAX：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、low_price_core_experience_intact、same_price_core_config_gain、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs
- TV00027301 VIDDA 50V1ND-R：status=ready_degraded，confidence=0.5000，core=picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture，reasons=missing_or_partial_inputs

## 核心成交理由缺失清单（前 30）

- TV00009549 康佳 LED32E330CE：status=weak_expression_only，confidence=0.0500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00023850 酷开 50P31：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025500 红米 L32RA-RA：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00025501 红米 L43RA-RA：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026874 创维 32H3GT：status=ready_degraded，confidence=0.3500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026886 VIDDA 32V1FD-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00026983 TCL 75S11-JN：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027302 VIDDA 65V1Q-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027353 VIDDA 75V1Q-R：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027378 飞利浦 43PFF6590：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027443 红米 L55RB-RAE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027463 红米 L43RB-APE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027475 红米 L55RB-APE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027483 TCL 55V8L PRO：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027485 TCL 65V8L PRO：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027492 红米 L75RB-APE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027511 红米 L65RB-APE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027523 海信 55E5Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027524 海信 75E5Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027526 海信 85E5Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027541 海信 65E5Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027547 海信 100E5Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027551 海信 75E3Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027552 红米 L43RA-RAE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027615 红米 L75MA-RAE：status=ready_degraded，confidence=0.3500，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027638 长虹 85JD900F-G1：status=weak_expression_only，confidence=0.0700，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027737 红米 L50RB-RAE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027754 创维 55A3F：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027770 海信 85E8Q：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs
- TV00027774 红米 L70RB-RAE：status=ready_degraded，confidence=0.3000，core=-，reasons=core_payment_missing,low_profile_confidence,missing_or_partial_inputs

## 后续任务

- M12D-G09：在本草稿版本基础上执行发布版本与下游契约冻结。
- G09 前竞品智能体不得直接消费本草稿版本作为正式结论。
