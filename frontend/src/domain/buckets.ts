// 把 coverage.gaps 映射到趋势桶上。
//
// 存在的理由只有一条：**"这天没打字"和"这天测不到"在图表上必须长得不一样**
// （06 文档 §4.2 规则 1）。桶粒度与 gap 粒度不同（gap 总是按天），所以映射要分情况：
//
//   hour   单日视图。这一天是缺口 -> 24 个桶全是缺口。
//   day    桶 id 就是日期，直接查。
//   month  桶覆盖多天，只要含一天缺口就标记（保守：宁可提示也不要静默）。
//   year   同上。
import { bucketCoversGap } from './period.ts';
import type { CategoryShare, TrendBucket } from '../types/api.d.ts';

/** 带缺口标记与堆叠段的桶。两个字段都是前端加的，后端不给。 */
export interface MarkedBucket extends TrendBucket {
  gap?: boolean;
  parts?: { category: string; seconds: number; name: string }[];
}

/** 这个函数只读 `bucket` 一个字段，所以它对桶的其余形状不作要求。 */
interface Bucketed {
  bucket: string;
}

/** 只需要一个"这一段从哪天开始"。`PeriodMeta` 与键盘时间线的 `{start, end}` 都满足。 */
interface PeriodStart {
  start?: string | null;
  anchor?: string | null;
}

/**
 * **泛型而不是收 `TrendBucket`**：键盘时间线的桶（`KeyTimelineBucket`）没有
 * seconds / presses / categories，而它同样要标缺口。写成泛型之后调用点不必 `as`
 * 一下——那种转型会把"这里的类型其实对不上"这件事藏起来。
 */
export function markGaps<T extends Bucketed>(
  buckets: readonly T[] | undefined,
  granularity: string,
  gaps: Set<string> | null | undefined,
  period?: PeriodStart | null,
): (T & { gap?: boolean })[] {
  if (!buckets?.length || !gaps || gaps.size === 0) return [...(buckets || [])];
  if (granularity === 'hour') {
    const day = period?.start || period?.anchor;
    const missing = Boolean(day && gaps.has(day));
    return buckets.map((bucket) => (missing ? { ...bucket, gap: true } : bucket));
  }
  return buckets.map((bucket) => {
    const hit =
      granularity === 'day' ? gaps.has(bucket.bucket) : bucketCoversGap(bucket.bucket, gaps);
    return hit ? { ...bucket, gap: true } : bucket;
  });
}

/** 缺口天数，供图例注记用（"3 天没有采集记录"）。 */
export function gapDayCount(gaps: Set<string> | null | undefined): number {
  return gaps ? gaps.size : 0;
}

/**
 * 把趋势桶的 `categories` 展成活动带上面板要的 `parts`（14 文档 §4.3）。
 *
 * 键序即后端序（按类别 id 排），所以同一个类别在每个周期都堆在同一层——这与「构成」
 * 卡的槽位规则是同一条（14 文档 §2.10）。后端保证各值之和恒等于 `seconds`，因此
 * 堆叠段加起来正好是柱高；没有 `categories` 的响应（旧版本或裁剪过的 include）
 * 退化成单色柱而不是空柱。
 */
export function stackByCategory(
  buckets: readonly MarkedBucket[] | undefined,
  catalog: readonly CategoryShare[] | undefined,
): MarkedBucket[] {
  const names = new Map((catalog || []).map((item) => [item.id, item.name]));
  return (buckets || []).map((bucket) => {
    const entries = Object.entries(bucket.categories || {}).filter(
      ([, seconds]) => (seconds || 0) > 0,
    );
    if (!entries.length) return bucket;
    return {
      ...bucket,
      parts: entries.map(([category, seconds]) => ({
        category,
        seconds,
        name: names.get(category) || category,
      })),
    };
  });
}
