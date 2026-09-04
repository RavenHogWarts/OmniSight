// 365 天日历热图。**DOM 而非 canvas**：一次渲染 + CSS 变量着色，于是主题切换零成本、
// 悬停命中由浏览器负责、屏幕阅读器能逐格读到 aria-label（06 文档 §14 的
// "365 天日历渲染 < 50ms"）。
//
// React 化之后 keyed 更新由 React 的 key 负责（原先是 core/dom.js 的 renderKeyed）。
// 365 个格子在一次提交里创建，之后每次数据变化只改 data-level 与 aria-label 两个属性
// ——React 的 diff 恰好只会写这两个，与手写 renderKeyed 的结果一致。
import { useMemo } from 'react';
import { formatCount } from '../domain/format.ts';
import { fromISO } from '../domain/period.ts';
import { heatLevel, heatRatio } from '../domain/metrics.ts';
import type { BucketScale } from '../types/api.d.ts';

/**
 * 日历只需要"桶 id"加"被读的那个指标字段"。刻意不收 `TrendBucket`：键盘的时间线桶
 * （`KeyTimelineBucket`）没有 seconds/presses/categories，而这张日历两处都要画
 * （总览按天、键盘按天）。
 */
export interface CalendarBucket {
  bucket: string;
  /** 被 `metric` 指名的那个字段。声明成可选数字而不是索引签名：
   *  索引签名会要求实参类型自己也带一个，而后端的响应接口都是具名字段。 */
  press_count?: number;
  duration_total_ms?: number;
  duration_avg_ms?: number;
  seconds?: number;
  presses?: number;
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

/** 补位格子没有数据，只占一个网格位置，让第一列从"周起始日"开始。 */
interface Cell {
  key: string;
  bucket?: string;
  empty?: boolean;
  value?: number;
}

export interface CalendarHeatmapProps {
  buckets: readonly CalendarBucket[] | undefined;
  scale: BucketScale | null | undefined;
  gaps?: Set<string> | null;
  /** 与后端 ui.week_starts_on 同义（0 = 周一）。 */
  weekStartsOn?: number;
  metric?: string;
  onSelect?: ((bucket: string) => void) | null;
}

export function CalendarHeatmap({
  buckets,
  scale,
  gaps,
  weekStartsOn = 0,
  metric = 'press_count',
  onSelect = null,
}: CalendarHeatmapProps) {
  const cells = useMemo(() => padToWeeks(buckets || [], weekStartsOn, metric), [buckets, weekStartsOn, metric]);
  const months = useMemo(() => monthMarks(cells), [cells]);

  return (
    <div className="calendar">
      <div className="weekday-axis">
        {Array.from({ length: 7 }, (_unused, index) => (
          <span key={index}>{index % 2 === 0 ? WEEKDAYS[(index + weekStartsOn) % 7] : ''}</span>
        ))}
      </div>
      <div className="calendar__body">
        {/* 月份轴：365 个格子没有刻度就看不出六月在哪（14 文档 §5.2）。 */}
        <div className="heatgrid__months" aria-hidden="true">
          {months.map((mark) => (
            <span
              key={mark.column}
              className="heatgrid__month"
              style={{ gridColumn: mark.column }}
            >
              {mark.label}
            </span>
          ))}
        </div>
        <div
          className="heatgrid"
          role="group"
          aria-label="每日活跃度"
          onClick={
            onSelect
              ? (event) => {
                  const cell = (event.target as HTMLElement).closest('.heat-cell');
                  const bucket = (cell as HTMLElement | null)?.dataset.bucket;
                  if (bucket) onSelect(bucket);
                }
              : undefined
          }
        >
          {cells.map((cell) => (
            <HeatCell key={cell.key} cell={cell} scale={scale} gap={Boolean(cell.bucket && gaps?.has(cell.bucket))} />
          ))}
        </div>
      </div>
    </div>
  );
}

function HeatCell({
  cell,
  scale,
  gap,
}: {
  cell: Cell;
  scale: BucketScale | null | undefined;
  gap: boolean;
}) {
  if (cell.empty) return <div className="heat-cell" data-empty="true" />;
  const ratio = gap ? 0 : heatRatio(cell.value, scale);
  return (
    <div
      className="heat-cell"
      data-bucket={cell.bucket}
      data-level={heatLevel(ratio)}
      data-gap={gap ? 'true' : undefined}
      aria-label={gap ? `${cell.bucket}：无记录` : `${cell.bucket}：${formatCount(cell.value)} 次`}
    />
  );
}

/** 首尾补空格子，让第一列从"周起始日"开始，否则整张图会错位一天。 */
function padToWeeks(
  buckets: readonly CalendarBucket[],
  weekStartsOn: number,
  metric: string,
): Cell[] {
  if (!buckets.length) return [];
  const read = (item: CalendarBucket) =>
    Number((item as unknown as Record<string, unknown>)[metric]) || 0;
  const first = fromISO(buckets[0].bucket);
  if (!first) return buckets.map((item) => ({ key: item.bucket, bucket: item.bucket, value: read(item) }));
  // getDay(): 0 = 周日。转成"周一 = 0"再套用 weekStartsOn。
  const mondayIndex = (first.getDay() + 6) % 7;
  const offset = (mondayIndex - weekStartsOn + 7) % 7;
  const padded: Cell[] = [];
  for (let index = 0; index < offset; index += 1) padded.push({ key: `pad-${index}`, empty: true });
  for (const item of buckets) padded.push({ key: item.bucket, bucket: item.bucket, value: read(item) });
  return padded;
}

/**
 * 月份标签落在哪一列。
 *
 * 格子是按列填的（`grid-auto-flow: column`，每列 7 天），所以第 n 个格子在第
 * `floor(n / 7) + 1` 列——每个月的第一天落在哪一列，标签就放在哪一列。
 */
function monthMarks(cells: readonly Cell[]): { column: number; label: string }[] {
  const marks: { column: number; label: string }[] = [];
  let previous = '';
  cells.forEach((cell, index) => {
    if (cell.empty || !cell.bucket) return;
    const month = cell.bucket.slice(0, 7);
    if (month === previous) return;
    previous = month;
    marks.push({ column: Math.floor(index / 7) + 1, label: `${Number(month.slice(5, 7))} 月` });
  });
  // 相邻标签挨得太近会叠在一起（一个月约 4.3 列，标签约 3 列宽）。
  return marks.filter((mark, index) => index === 0 || mark.column - marks[index - 1].column >= 4);
}
