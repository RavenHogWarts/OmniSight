// 展示格式化。
//
// **接口已经给了 `*_formatted` 字段，能用就用**（07 文档 §10 / services/formatting.py）：
// 列表、指标卡里的时长一律直接显示后端的字符串。这里的实现只服务两类后端给不了的场合：
//   1. canvas 图表的 tooltip —— 桶数据里没有预格式化字段，为每个桶多带一个字符串不划算；
//   2. SSE 推来的实时计数器 —— 它每秒都在变，不可能走一次请求。
//
// 因此它必须与 Python 版**逐个边界一致**：0 -> 0秒、59.6 -> 59秒（截断）、3600 -> 1小时
// （不补零）。tests/frontend/format.test.ts 用与 tests/unit/test_formatting.py 相同的
// 表格固定这些值，两边同时改才可能改。
import type { Delta } from '../types/api.d.ts';

/** 人类可读时长。参数是秒。 */
export function formatDuration(seconds: number | null | undefined): string {
  const value = Number(seconds) || 0;
  if (value <= 0) return '0秒';
  if (value < 60) return `${Math.trunc(value)}秒`;
  const minutes = Math.trunc(value / 60);
  if (minutes < 60) return `${minutes}分钟`;
  const hours = Math.trunc(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours}小时` : `${hours}小时${rest}分钟`;
}

/** 紧凑时长，图表轴与窄列用。7h33m 而不是"7小时33分钟"。 */
export function formatDurationShort(seconds: number | null | undefined): string {
  const value = Number(seconds) || 0;
  if (value <= 0) return '0';
  if (value < 60) return `${Math.trunc(value)}s`;
  const minutes = Math.trunc(value / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.trunc(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours}h` : `${hours}h${rest}m`;
}

/** 千分位。按键数动辄六位，不分组读不出量级。 */
export function formatCount(value: number | null | undefined): string {
  return Math.trunc(Number(value) || 0).toLocaleString('zh-CN');
}

export function formatMs(ms: number | null | undefined): string {
  const value = Number(ms) || 0;
  if (value < 1000) return `${value.toFixed(value < 10 ? 1 : 0)}ms`;
  return `${(value / 1000).toFixed(2)}s`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  return `${(Number(value) || 0).toFixed(digits)}%`;
}

/** delta 只表示方向，不做价值判断——屏幕时间上升不一定是坏事（06 文档 §5.1）。 */
export function formatDelta(delta: Delta | null | undefined, unit = ''): string {
  if (!delta) return '';
  const percent = Number(delta.percent) || 0;
  if (percent === 0) return `持平${unit ? ` ${unit}` : ''}`;
  const arrow = percent > 0 ? '▲' : '▼';
  return `${arrow} ${Math.abs(percent).toFixed(1)}%`;
}

/**
 * ISO 时间戳 -> `M/D HH:MM`。"最近用过"这类副行要日期也要钟点：只给钟点的话
 * 昨天 18:32 与今天 18:32 长得一样。
 */
export function formatDayTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return '';
  return `${value.getMonth() + 1}/${value.getDate()} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

/** ISO 时间戳 -> `HH:MM`。后端给的是带时区偏移的字符串，Date 能正确解析。 */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatClockRange(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
): string {
  const start = formatClock(startIso);
  const end = formatClock(endIso);
  return start && end ? `${start}–${end}` : start || end;
}

/** `2026-09-02` -> `9/2`。周期标题一律用后端给的 period.label，这个只给轴用。 */
export function formatDayShort(day: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(day || ''));
  if (!match) return String(day || '');
  return `${Number(match[2])}/${Number(match[3])}`;
}

export function pad(value: number | string): string {
  return String(value).padStart(2, '0');
}

/** 首字母色块用（无图标时）。取第一个字符，中文与 emoji 都能正确取到。 */
export function initialOf(name: string | null | undefined): string {
  const text = String(name || '').trim();
  if (!text) return '?';
  return [...text][0].toUpperCase();
}
