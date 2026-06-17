import type { Core3CompetitorBrief } from "../../types";
import { core3RoleOrder } from "./core3Pages";

export const core3RoleLabels: Record<string, string> = {
  direct: "正面对打",
  pressure: "价格/销量挤压",
  benchmark_potential: "高端标杆/潜在下探"
};

export const confidenceLabels: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低"
};

const businessLabels: Record<string, string> = {
  screen_size_inch: "屏幕尺寸",
  resolution_class: "分辨率档位",
  panel_type: "面板类型",
  display_technology: "显示技术",
  series_name: "产品系列",
  launch_period: "上市周期",
  native_refresh_rate_hz: "原生刷新率",
  system_refresh_rate_hz: "系统刷新率",
  refresh_rate_hz: "刷新率",
  peak_brightness_nits: "峰值亮度",
  instant_peak_brightness_nits: "瞬时峰值亮度",
  sustained_brightness_nits: "稳定亮度",
  sustained_peak_brightness_nits: "稳定峰值亮度",
  color_gamut_pct: "色域覆盖",
  color_gamut_standard: "色域标准",
  color_depth_bit: "色深",
  hdr_format_list: "高动态画面格式",
  picture_processor: "画质芯片/引擎",
  motion_compensation_flag: "运动补偿",
  mini_led_flag: "精细背光",
  oled_flag: "自发光显示",
  qled_flag: "量子点广色域",
  backlight_type: "背光类型",
  dimming_zones: "控光分区数",
  local_dimming_flag: "分区控光",
  halo_control_claim_flag: "光晕控制",
  hdmi_2_1_ports: "游戏高速接口数",
  full_bandwidth_hdmi_flag: "满带宽游戏接口",
  input_lag_ms: "输入延迟",
  vrr_flag: "可变刷新",
  speaker_power_w: "音响功率",
  speaker_channel: "声道配置",
  subwoofer_flag: "低音单元",
  dolby_atmos_flag: "沉浸声效",
  dts_flag: "影院音频",
  ram_gb: "运行内存",
  storage_gb: "存储容量",
  chipset_name: "芯片方案",
  os_name: "系统名称",
  voice_control_flag: "语音控制",
  far_field_voice_flag: "远场语音",
  startup_ads_risk_flag: "开机广告风险",
  low_blue_light_flag: "低蓝光护眼",
  flicker_free_flag: "无频闪",
  eye_dimming_freq_hz: "护眼调光频率",
  child_mode_flag: "儿童模式",
  anti_glare_flag: "防眩光",
  energy_efficiency_level: "能效等级",
  warranty_years: "质保年限",
  install_service_flag: "安装服务保障",
  CLAIM_DOLBY_CINEMA_AUDIO: "杜比影院音效",
  CLAIM_ELDER_FRIENDLY_SMART: "长辈友好",
  CLAIM_ENERGY_SAVING: "节能省电",
  CLAIM_EYE_CARE_COMFORT: "护眼舒适",
  CLAIM_FINE_LOCAL_DIMMING: "精细分区控光",
  CLAIM_GAMING_LOW_LATENCY: "游戏低延迟",
  CLAIM_HDMI_2_1_GAMING: "主机游戏接口",
  CLAIM_HIGH_BRIGHTNESS_HDR: "高亮高动态画质",
  CLAIM_HIGH_REFRESH_RATE: "高刷新率",
  CLAIM_IMMERSIVE_AUDIO: "沉浸音效",
  CLAIM_INSTALLATION_SERVICE_ASSURANCE: "送装售后保障",
  CLAIM_LARGE_SCREEN_IMMERSION: "大屏沉浸",
  CLAIM_MINI_LED_BACKLIGHT: "精细背光",
  CLAIM_NO_AD_OR_CLEAN_SYSTEM: "清爽系统",
  CLAIM_OLED_SELF_LIT: "像素级自发光",
  CLAIM_QLED_WIDE_COLOR: "量子点广色域",
  CLAIM_SMART_VOICE_EASE: "智能语音易用",
  CLAIM_SPORTS_MOTION_SMOOTH: "运动画面流畅",
  CLAIM_THIN_DESIGN: "超薄家居设计",
  CLAIM_VALUE_FOR_MONEY: "高性价比",
  TASK_BEDROOM_SECOND_TV: "卧室副屏",
  TASK_CHILD_EYE_CARE: "儿童护眼",
  TASK_GAMING_ENTERTAINMENT: "游戏娱乐",
  TASK_LARGE_SCREEN_REPLACEMENT: "大屏换新",
  TASK_LIVING_ROOM_CINEMA: "客厅影院",
  TASK_NEW_HOME_DECORATION: "新家装修",
  TASK_PREMIUM_PICTURE_AV: "高端画质影音",
  TASK_SENIOR_EASY_USE: "长辈易用",
  TASK_SPORTS_WATCHING: "体育赛事观看",
  TASK_VALUE_PURCHASE: "性价比购买",
  TG_AV_QUALITY_SEEKER: "画质影音用户",
  TG_BEDROOM_SECOND_TV: "卧室副屏用户",
  TG_CHILD_FAMILY: "儿童家庭用户",
  TG_FAMILY_UPGRADE: "家庭换新用户",
  TG_GAMER: "游戏用户",
  TG_NEW_HOME_DECORATOR: "新家装修用户",
  TG_SENIOR_FAMILY: "长辈家庭用户",
  TG_SPORTS_FAN: "体育观看用户",
  TG_VALUE_BUYER: "性价比用户",
  TOPIC_AUDIO_QUALITY: "音质体验",
  TOPIC_BRIGHTNESS_HDR: "亮度与高动态画质",
  TOPIC_CHILD_FAMILY: "儿童家庭",
  TOPIC_DARK_SCENE_CONTRAST: "暗场对比",
  TOPIC_DURABILITY_QUALITY: "做工耐用",
  TOPIC_EASE_OF_USE: "操作易用",
  TOPIC_EYE_COMFORT: "护眼舒适",
  TOPIC_GAMING_SMOOTHNESS: "游戏流畅",
  TOPIC_INSTALLATION_SERVICE: "安装服务",
  TOPIC_INTERFACE_CONNECTIVITY: "接口连接",
  TOPIC_PICTURE_QUALITY: "画质体验",
  TOPIC_PRICE_VALUE: "价格价值感",
  TOPIC_SENIOR_FRIENDLY: "长辈友好",
  TOPIC_SIZE_SPACE_FIT: "尺寸与空间适配",
  TOPIC_SPORTS_WATCHING: "体育观看",
  TOPIC_SYSTEM_ADS_PERFORMANCE: "系统广告与流畅度",
  BF_CINEMA_AUDIO_IMMERSION: "影院音效战场",
  BF_DESIGN_HOME_FIT: "家居美学战场",
  BF_FAMILY_EYE_CARE: "家庭护眼战场",
  BF_FAMILY_VIEWING_UPGRADE: "家庭观影升级战场",
  BF_GAMING_SPORTS: "游戏体育战场",
  BF_LARGE_SCREEN_VALUE: "大屏性价比战场",
  BF_PREMIUM_PICTURE: "高端画质战场",
  BF_SENIOR_EASE_OF_USE: "长辈易用战场",
  BF_SERVICE_ASSURANCE: "服务保障战场",
  BF_SMART_SYSTEM_EXPERIENCE: "智能系统体验战场",
  price_similarity: "价格接近度",
  channel_overlap: "渠道重合度",
  size_similarity: "尺寸一致性",
  claim_similarity: "卖点相似度",
  task_similarity: "使用任务相似度",
  battlefield_similarity: "价值战场相似度",
  task_battlefield_similarity: "任务战场相似度",
  price_advantage: "价格优势",
  sales_strength: "销量强度",
  weak_profile: "画像证据不足",
  weak_params: "参数证据不足",
  weak_claims: "卖点证据不足",
  weak_comments: "评论证据不足",
  weak_gaming: "游戏体育证据不足",
  weak_premium: "高端画质证据不足",
  weak_benchmark_potential: "缺少高端标杆/潜在下探证据",
  raw_master: "主数据",
  raw_param: "参数表",
  raw_claim: "卖点表",
  raw_comment: "评论表",
  market_fact: "量价事实",
  derived_profile: "画像推断",
  comment_text: "评论文本",
  claim_text: "卖点文本",
  raw_value: "原始取值"
};

export function orderCore3Roles<T extends { role: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => roleIndex(a.role) - roleIndex(b.role));
}

export function roleIndex(role: string): number {
  const index = core3RoleOrder.findIndex((item) => item === role);
  return index >= 0 ? index : 99;
}

export function formatPercent(value: unknown): string {
  const number = asNumber(value);
  if (number === undefined) {
    return "-";
  }
  return `${Math.round(number * 100)}%`;
}

export function formatNumber(value: unknown, digits = 2): string {
  const number = asNumber(value);
  if (number === undefined) {
    return "-";
  }
  return number.toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: number % 1 === 0 ? 0 : Math.min(2, digits)
  });
}

export function competitorLabel(value: Core3CompetitorBrief | Record<string, unknown> | null | undefined): string {
  if (!value) {
    return "未命中";
  }
  const skuCode = getValue(value, "competitor_sku_code") ?? getValue(value, "sku_code");
  const brand = getValue(value, "competitor_brand") ?? getValue(value, "brand");
  const model = getValue(value, "competitor_model_name") ?? getValue(value, "model_name");
  return [brand, model, skuCode].filter(Boolean).join(" · ") || "未命中";
}

export function confidenceLabel(level: string | undefined): string {
  return confidenceLabels[level ?? ""] ?? "低";
}

export function confidenceColor(level: string | undefined): string {
  if (level === "high") {
    return "green";
  }
  if (level === "medium") {
    return "gold";
  }
  return "red";
}

export function businessLabel(code: unknown): string {
  if (typeof code !== "string" || code.length === 0) {
    return "-";
  }
  return businessLabels[code] ?? code;
}

export function businessLabelsFor(codes: unknown): string {
  if (!Array.isArray(codes)) {
    return "-";
  }
  return codes.map((code) => businessLabel(code)).join(" / ") || "-";
}

export function businessText(value: unknown): string {
  let text = String(value ?? "-");
  const entries = Object.entries(businessLabels).sort((a, b) => b[0].length - a[0].length);
  for (const [code, label] of entries) {
    text = text.split(code).join(label);
  }
  return text
    .replace(/\bCore3\b/g, "三竞品")
    .replace(/\bMVP\b/g, "演示版")
    .replace(/\bSKU\b/g, "商品")
    .replace(/\bdirect\b/g, "正面对打")
    .replace(/\bpressure\b/g, "价格/销量挤压")
    .replace(/\bbenchmark_potential\b/g, "高端标杆/潜在下探")
    .replace(/目标 商品/g, "目标商品")
    .replace(/目标商品 在/g, "目标商品在")
    .replace(/目标商品 面向/g, "目标商品面向")
    .replace(/商品 或/g, "商品或")
    .replace(/可比较 商品/g, "可比较商品")
    .replace(/战场 战场/g, "战场")
    .replace(/高端标杆\/潜在下探 未/g, "高端标杆/潜在下探未")
    .replace(/彩电核心三竞品 演示版 演示/g, "彩电三竞品演示批次")
    .replace(/([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])/g, "$1$2");
}

export function businessValue(value: unknown): string {
  if (value === true) {
    return "是";
  }
  if (value === false) {
    return "否";
  }
  if (Array.isArray(value)) {
    return value.map((item) => businessLabel(item)).join("、") || "-";
  }
  if (typeof value === "string") {
    return businessText(value);
  }
  return String(value ?? "-");
}

export function parseJsonl(text: string): unknown[] {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line));
}

export function csvHeader(text: string): string[] {
  const firstLine = text.split(/\r?\n/, 1)[0] ?? "";
  return firstLine.split(",");
}

export function getValue(row: object, key: string): unknown {
  return (row as Record<string, unknown>)[key];
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}
