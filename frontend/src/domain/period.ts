// 周期的 **UI 层** 计算（07 文档 §10 第 3 行）。
//
// 严格的分工：真实区间一律取接口返回的 `period.start` / `period.end` /
// `period.truncated_end` / `period.label`。这里只做两件后端管不到的事：
//   1. 日期箭头的加减（点"上一周"时该请求哪个 date）；
//   2. 判断"下一个周期"是否已经越过今天，好把箭头置灰。
//
// 前端**不重算聚合边界**。周起始日、月末、total 的展开都在 services/period.py，
// 那里要查库才知道"哪天有数据"。
import type { Coverage, CoverageGap } from '../types/api.d.ts';
import type { PeriodState } from '../core/store.ts';

export const MS_PER_DAY = 86_400_000;

export function todayISO(now: Date = new Date()): string {
  return toISO(now);
}

export function toISO(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function fromISO(text: string | null | undefined): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text || ''));
  if (!match) return null;
  // 用本地时间构造，避免 new Date('2026-09-02') 被当 UTC 而在东八区差一天。
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function addDays(day: string, count: number): string {
  const date = fromISO(day);
  if (!date) return day;
  date.setDate(date.getDate() + count);
  return toISO(date);
}

export function addMonths(day: string, count: number): string {
  const date = fromISO(day);
  if (!date) return day;
  const target = new Date(date.getFullYear(), date.getMonth() + count, 1);
  // 1 月 31 日 + 1 个月落在 2 月：钳到月末，而不是滑到 3 月 3 日。
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(date.getDate(), lastDay));
  return toISO(target);
}

export function addYears(day: string, count: number): string {
  const date = fromISO(day);
  if (!date) return day;
  const target = new Date(date.getFullYear() + count, date.getMonth(), 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(date.getDate(), lastDay));
  return toISO(target);
}

/**
 * 周期翻页。`anchor` 用响应里的 `period.anchor`（后端已把它规整过），
 * 没有响应时退回本地今天。
 */
export function shift(range: string, anchor: string | null | undefined, direction: number): string {
  const base = anchor || todayISO();
  switch (range) {
    case 'day':
      return addDays(base, direction);
    case 'week':
      return addDays(base, direction * 7);
    case 'month':
      return addMonths(base, direction);
    case 'year':
      return addYears(base, direction);
    default:
      return base; // total / custom 没有"上一个"
  }
}

/** 能不能往后翻。后端会把未来截断，但按钮该先置灰，而不是点了没反应。 */
export function canGoForward(
  range: string,
  anchor: string | null | undefined,
  today: string = todayISO(),
): boolean {
  if (range === 'total' || range === 'custom') return false;
  // 日与周/月/年同一条判据：下一个周期的锚点不晚于今天就还有得看。
  return shift(range, anchor, 1) <= today;
}

export function isPageable(range: string): boolean {
  return range !== 'total' && range !== 'custom';
}

/** 键盘时间分布的桶数（画骨架屏时要知道画几格）。 */
export function bucketCountHint(view: string): number {
  switch (view) {
    case 'hours':
      return 24;
    case 'days':
      return 365;
    case 'months':
      return 12;
    default:
      return 3;
  }
}

/**
 * `coverage.gaps` -> Set of days，图表按桶查它决定画不画斜纹。
 *
 * 每条 gap 形如 `{from, to, missing, reason, message}`（services/coverage.py）。
 * **必须按 `missing` 过滤**：时长图只关心 `foreground` 缺失，键盘图只关心 `keyboard`
 * 缺失。而 `key_position` 根本不是"没有数据"——它是"左右修饰键合并统计了"，
 * 口径变化，画成斜纹会告诉用户那几天没打字，那是错的。
 */
export function gapSet(
  coverage: Coverage | null | undefined,
  kinds: readonly string[] = ['foreground'],
): Set<string> {
  const wanted = new Set(kinds);
  const days = new Set<string>();
  for (const gap of coverage?.gaps || []) {
    if (!wanted.has(gap?.missing)) continue;
    const start = gap.from;
    const end = gap.to || start;
    if (!start) continue;
    let cursor = start;
    // 上限防御：坏数据不该让页面卡死在一个循环里。
    for (let index = 0; index < 4000 && cursor <= end; index += 1) {
      days.add(cursor);
      cursor = addDays(cursor, 1);
    }
  }
  return days;
}

export interface CaliberNote {
  from: string;
  to: string | null;
  message: string;
  reason: string;
}

/** 口径变化（不是缺数据）的说明，供图例注记用。 */
export function caliberNotes(coverage: Coverage | null | undefined): CaliberNote[] {
  return (coverage?.gaps || [])
    .filter((gap: CoverageGap) => gap?.missing === 'key_position')
    .map((gap) => ({ from: gap.from, to: gap.to, message: gap.message, reason: gap.reason }));
}

/** 桶 id -> 是否命中缺口。日桶精确匹配，月/年桶只要包含一天缺口就算。 */
export function bucketCoversGap(bucket: string, gaps: Set<string> | null | undefined): boolean {
  if (!gaps || gaps.size === 0) return false;
  const text = String(bucket || '');
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return gaps.has(text);
  if (/^\d{4}-\d{2}$/.test(text) || /^\d{4}$/.test(text)) {
    for (const day of gaps) if (day.startsWith(text)) return true;
  }
  return false;
}

/**
 * 周期状态 -> 查询参数（05 文档 §1.2）。custom 用 start/end，其余用 date。
 * 视图取数一律经它，于是"周期怎么变成参数"只有一份实现。
 */
export function periodParams(period: PeriodState): Record<string, string | null> {
  if (period.range === 'custom') {
    return { range: 'custom', start: period.start, end: period.end };
  }
  return { range: period.range, date: period.date };
}
