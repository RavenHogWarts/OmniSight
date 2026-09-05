// 一维格子条（18 文档 批 7）：时间分布里小时 / 月 / 年三个尺度的**第二种形式**。
//
// **为什么值得有第二种形式。** 柱状图回答"多与少"，格子条回答"什么时候在打字"：24 根柱要
// 逐根比高度，而 24 个格子的深浅在一眼里就扫完一整天的形状——这正是日尺度上那张年历好用的
// 理由，只是把它压成一行。两种形式读的是同一份数据（四个粒度一次请求取回），所以切形式不
// 发请求，也不会出现"两张图对不上"。
//
// 着色与年历、键面完全同源（`heatRatio` + `heatLevel` + `.heat-cell` 的五档），因此"颜色越
// 深用得越多"这条约定在整个界面里只需要学一次。缺口同理走 `data-gap` 的斜纹：**无数据不是
// 零**（06 文档 §4.2 规则 1）。
//
// 提示走单例 tooltip 而不是原生 `title`：原生的延迟约半秒、不能分两行，也不受主题控制
// （与 HourBand 同一个理由）。因此这个组件住在 components/ 而不是 charts/——charts 那一层
// 不许 import components（07 文档 §3 的分层规则）。
import { heatLevel, heatRatio } from '../domain/metrics.ts';
import type { BucketScale } from '../types/api.d.ts';
import { hide as hideTooltip, show as showTooltip } from './tooltip.tsx';

export interface StripBucket {
  bucket: string;
  /** 轴上那行小字（"08 时"、"3 月"、"2026"）。 */
  label?: string;
  value: number;
  /** 这一段没有采集覆盖（斜纹），而不是值为 0。 */
  gap?: boolean;
}

export interface HeatStripProps {
  buckets: readonly StripBucket[];
  scale: BucketScale | null | undefined;
  /** 提示里那一行的名字（"按键次数"）。 */
  valueLabel: string;
  format: (value: number) => string;
  /** 整条的无障碍名字。 */
  label: string;
}

/**
 * 轴上标签的间隔。12 个以内全标（月、年），再多就抽稀——24 个小时标签在一条格子上会挤成
 * 一片灰。抽稀后仍然落在"每 3 小时"这种整齐的位置上，因为 step 是整除出来的。
 */
function labelStep(count: number): number {
  return count <= 12 ? 1 : Math.ceil(count / 8);
}

export function HeatStrip({ buckets, scale, valueLabel, format, label }: HeatStripProps) {
  const step = labelStep(buckets.length);
  return (
    <div className="heatstrip" role="group" aria-label={label}>
      {buckets.map((bucket, index) => {
        const ratio = bucket.gap ? 0 : heatRatio(bucket.value, scale);
        const title = bucket.label || bucket.bucket;
        return (
          <div className="heatstrip__slot" key={bucket.bucket}>
            <div
              className="heat-cell"
              data-level={heatLevel(ratio)}
              data-gap={bucket.gap ? 'true' : undefined}
              aria-label={
                bucket.gap ? `${title}：无记录` : `${title}：${format(bucket.value)}`
              }
              onPointerMove={(event) =>
                showTooltip({
                  title,
                  rows: [[valueLabel, bucket.gap ? '无记录' : format(bucket.value)]],
                  note: bucket.gap ? '这一段没有采集覆盖' : undefined,
                  x: event.clientX,
                  y: event.clientY,
                })
              }
              onPointerLeave={hideTooltip}
            />
            <span className="heatstrip__label">
              {index % step === 0 ? title : ''}
            </span>
          </div>
        );
      })}
    </div>
  );
}
