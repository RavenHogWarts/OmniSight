// 指标定义与色阶映射。**唯一允许出现"指标该怎么显示"的地方**。
import { formatCount, formatMs } from './format.js';

/** 与 services/keyboard.py 的 METRICS 一一对应。顺序即 UI 顺序。 */
export const METRICS = [
  { id: 'press_count', name: '次数', short: '次', format: formatCount },
  { id: 'duration_total_ms', name: '总时长', short: '总', format: formatMs },
  { id: 'duration_avg_ms', name: '均时长', short: '均', format: formatMs },
  { id: 'duration_max_ms', name: '最长', short: '最长', format: formatMs },
];

const BY_ID = new Map(METRICS.map((metric) => [metric.id, metric]));

export function metricOf(id) {
  return BY_ID.get(id) || METRICS[0];
}

export function formatMetric(id, value) {
  return metricOf(id).format(value);
}

/** 周期范围。API 的 range 取值（services/period.py 的 RANGES）。 */
export const RANGES = [
  { id: 'day', name: '日' },
  { id: 'week', name: '周' },
  { id: 'month', name: '月' },
  { id: 'year', name: '年' },
  { id: 'total', name: '全部' },
  { id: 'custom', name: '自定义' },
];

/** config 的 ui.default_view 用 daily/weekly/... 命名，API 的 range 用 day/week/...。 */
const VIEW_TO_RANGE = {
  daily: 'day',
  weekly: 'week',
  monthly: 'month',
  yearly: 'year',
  total: 'total',
};

export function rangeFromDefaultView(view) {
  return VIEW_TO_RANGE[view] || 'day';
}

/** 键盘时间分布的四个视图（services/keyboard.py 的 TIMELINE_VIEWS）。 */
export const TIMELINE_VIEWS = [
  { id: 'hours', name: '时' },
  { id: 'days', name: '日' },
  { id: 'months', name: '月' },
  { id: 'years', name: '年' },
];

/** 应用画像。id 与 services/apps.py 的 PROFILE_NAMES 对齐，色由 CSS 按 data-profile 给。 */
export const PROFILES = ['input_heavy', 'interactive', 'passive', 'idle_open'];

/**
 * 热力比例。**p95 归一而不是最大值归一**（06 文档 §7 改进 1）：空格键通常是第二名的
 * 3 倍，用最大值会把其余所有键压成一片浅色。超出 p95 的键饱和到 1 并单独标记。
 */
export function heatRatio(value, scale) {
  const top = Number(scale?.p95) || Number(scale?.max) || 0;
  if (top <= 0) return 0;
  const ratio = (Number(value) || 0) / top;
  return ratio > 1 ? 1 : ratio;
}

export function isSaturated(value, scale) {
  const top = Number(scale?.p95) || 0;
  const max = Number(scale?.max) || 0;
  return top > 0 && max > top && (Number(value) || 0) > top;
}

/**
 * 离散档位。**这就是键面与格子实际渲染的那一档**（14 文档 §2.4）——不是"另外算一个
 * 供图例用的近似"。现状是 `color-mix` 在 heat-0 与 heat-5 之间连续插值，图例摆 6 个
 * 离散色块、键面画连续量，读者无法把一个键的颜色对回一个值区间。
 *
 * 0 是零态（没按过），不属于色阶的任何一档：它是承载面本身。
 */
export function heatLevel(ratio) {
  if (ratio <= 0) return 0;
  if (ratio < 0.2) return 1;
  if (ratio < 0.4) return 2;
  if (ratio < 0.6) return 3;
  if (ratio < 0.8) return 4;
  return 5;
}

/** 每一档对应的比例区间上界，供图例标出"这一档到多少"。 */
export const HEAT_BOUNDS = [0, 0.2, 0.4, 0.6, 0.8, 1];

export const CATEGORY_FALLBACK = 'uncategorized';
