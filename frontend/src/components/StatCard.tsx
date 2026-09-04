// 指标卡（06 文档 §5.1、14 文档 §2.6/§3.4）。
//
// delta 的箭头**不做价值判断**：屏幕时间上升不一定是坏事，按键增多也不一定好。
// 统一用 --text-secondary，只有方向没有颜色。纯统计工具不该替用户下道德判断。
//
// 解剖来自键帽（14 文档 §3.4）：标签左上、数值右下、1px 描边、**无独立卡头**——标签
// 本身就是卡头。产品自己的器物是键帽，界面的形状语言从它推导，而不是再发明一种卡片。
import { Chart } from '../charts/Chart.tsx';
import { contextBarsDescribe, contextBarsDraw } from '../charts/context-bars.ts';
import type { ContextBarsData } from '../charts/context-bars.ts';
import { formatDelta } from '../domain/format.ts';
import { Icon } from './Icon.tsx';
import { Skeleton } from './states.tsx';
import type { ContextSeries, Delta } from '../types/api.d.ts';

export interface StatCardProps {
  label: string;
  hint?: string;
  hero?: boolean;
  series?: 'time' | 'keys';
  metric?: 'seconds' | 'presses';
  format?: (value: number) => string;
  /** 主数值。`loading` 为真时忽略它，画骨架。 */
  text?: string;
  loading?: boolean;
  delta?: Delta | null;
  /**
   * `/overview` 的 `context` 段：当前周期所在的上一档粒度序列
   * （日→近 7 天、周→近 8 周、月→近 12 个月、年→全部年份）。
   *
   * `range=total` 与 `custom` 没有可比的序列，后端整段不给——那时整块隐藏，
   * 而不是画一根孤零零的柱子充数（14 文档 §4.3）。
   */
  context?: ContextSeries | null;
  footnote?: string;
  onHover?: ((payload: unknown, x: number, y: number) => void) | null;
  onLeave?: (() => void) | null;
}

export function StatCard({
  label,
  hint = '',
  hero = false,
  series = 'time',
  metric = 'seconds',
  format = String,
  text = '—',
  loading = false,
  delta = null,
  context = null,
  footnote = '',
  onHover = null,
  onLeave = null,
}: StatCardProps) {
  const buckets = context?.buckets || [];
  const chartData: ContextBarsData = { buckets, current: context?.current || '' };

  return (
    <div className="card card--keycap metric" data-hero={hero ? 'true' : undefined}>
      <div className="metric__label">
        <span>{label}</span>
        {hint ? (
          <span className="card__hint" title={hint} aria-label={hint}>
            <Icon name="info" />
          </span>
        ) : null}
        <div className="metric__delta numeric">{!loading && delta ? formatDelta(delta) : ''}</div>
      </div>
      {/* 卡上那条迷你图是**对照条**，不是本周期内部的走势线：后者与卡上方的活动带
          同源，因此画两遍只是把同一件事说两次，而"这段时间算不算多"仍然没人回答
          （14 文档 §2.18）。 */}
      <div className="metric__context" hidden={loading || buckets.length === 0}>
        <Chart<ContextBarsData>
          data={chartData}
          draw={contextBarsDraw({ accent: series, metric })}
          describe={contextBarsDescribe({ metric, format, label: `${label}对照条` })}
          height={36}
          label={`${label}对照条`}
          onHover={onHover}
          onLeave={onLeave}
        />
      </div>
      {/* 大号独立数字用**比例数字**：44px 上的 tabular-nums 会让 121 这类数字看起来
          松散。tabular-nums 留给需要竖向对齐的列（14 文档 §3.3）。 */}
      <div className="metric__value">{loading ? <Skeleton kind="value" /> : text}</div>
      <div className="metric__foot">{loading ? '' : footnote}</div>
    </div>
  );
}
