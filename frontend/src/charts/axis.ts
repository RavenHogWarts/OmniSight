// 时间轴标签：抽稀、末桶保号、边缘贴边（14 文档 §5.1 的记号规格延伸到轴这一层）。
//
// **为什么单独一支**：`panel-pair` / `scale-bars` / `stacked-bar` 三处各写了一遍同一段
// `index % stride`，而三处的密度常数不同（48 / 44 / 44 px）。于是同一份数据在同样宽度
// 下，招牌卡里的堆叠柱与洞察里的活动带会给出不同数量的标签——读者没有理由猜到那是两个
// 硬编码数字的差别。合成一支之后密度只有一条规则。
//
// 三条改进，都是原先那段抽稀做不到的：
//
// 1. **按实测文字宽度抽稀，而不是按一个常数。** 原先固定 44px 一格：`9/4` 只要 20px，
//    被判成放不下；`2026年12月` 要 70px，被判成放得下然后叠在一起。`measureText` 知道
//    真实宽度，而字体串已经统一在 `cssFont()`（canvas.ts）。
// 2. **末桶一定有标签。** `index % stride` 从 0 起跳，31 天 stride=4 时最后一个标签落在
//    第 28 天，右边三天没有任何刻度——图的右端说不出自己在哪结束。末桶补上之后若与前一
//    个挨得太近，丢掉前一个（丢一个中间刻度比丢右端边界便宜）。
// 3. **首末标签贴边而不是居中。** 居中的话首标签会往 y 轴刻度区里探出半个字宽、末标签
//    探出画布右缘。原先没有这个问题只是因为末桶通常没标签——第 2 条把它暴露出来了。
//
// 不做的一件事：把 stride 圆到"整齐的数"（日粒度取 5 的倍数、小时取 6 的倍数）。那需要
// 轴知道粒度，而三个调用点里只有两个知道；且当前桶数最多 31（周期最长是月），实测宽度
// 抽稀之后标签本来就落在 1/5/10 这类位置上。真要做的时机是引入 365 桶的形式时。

/** 相邻标签之间至少留这么多空白。低于 6px 时两个日期读起来像一个长词。 */
const LABEL_GAP = 10;

/**
 * y 轴刻度文字的留白宽度。**三张带轴的图共用这一个数。**
 *
 * 原先各写一个（52 / 48 / 44），三处注释说的却是同一件事："放得下最宽的刻度文字"。
 * 代价不是不好看，是**标签密度会不一致**：capacity 取的是 `floor(plot.w / minGap)`，
 * 而 stride 是整数，所以在边界附近 8px 的内边距差会让标签数折半。实测（1024px、24 个
 * 小时桶、画布同为 942px）：`plot.w` 882 → capacity 23 → 12 个标签，890 → capacity 24
 * → 24 个标签。同一屏的上下两张图于是给出两种密度。
 *
 * 取三者最大的 52：另两处本来就在赌"刻度文字不会更宽"（按键数到五位数、时长到
 * "1h23m" 都逼近它们的估值），而多出的 8px 在 942px 画布上是 0.9%。
 *
 * 不含 y 轴的图（`context-bars` 那条卡上的迷你对照条）不用它。
 */
export const AXIS_LEFT = 52;

/** 一个算好位置的轴标签。`align` 由边缘裁剪决定，因此调用方每次都要写回 ctx。 */
export interface AxisTick {
  /** 它是第几个桶。命中区与它无关，但调试时要对得上。 */
  index: number;
  text: string;
  x: number;
  align: CanvasTextAlign;
}

/** 轴所在的横向区间。与各图的 `plot` 同形，因此调用点直接传 plot。 */
export interface AxisSpan {
  x: number;
  w: number;
}

/**
 * 该画哪些标签、画在哪。
 *
 * `measure` 由调用方注入（真实实现是 `ctx.measureText(t).width`），于是这个函数是纯的
 * ——`tests/frontend/axis.test.ts` 用一个"每字符 7px"的假尺子就能钉住抽稀与保号规则，
 * 不需要 canvas。
 */
export function timeAxisTicks(
  labels: readonly string[],
  plot: AxisSpan,
  measure: (text: string) => number,
): AxisTick[] {
  const count = labels.length;
  if (!count || plot.w <= 0) return [];

  const widths = labels.map((text) => Math.max(0, measure(text)));
  // 用最宽的那个定间距：按平均值定会让最宽的那两个仍然叠在一起，而叠字是不可读，
  // 少画一个标签只是少一个刻度。
  const minGap = Math.max(1, Math.max(...widths) + LABEL_GAP);
  const slot = plot.w / count;
  // 至少留两个（首与末）：宽度再窄也要说出这根轴从哪到哪。
  const capacity = Math.max(2, Math.floor(plot.w / minGap));
  const stride = Math.max(1, Math.ceil(count / capacity));

  const centre = (index: number) => plot.x + slot * (index + 0.5);

  const chosen: number[] = [];
  for (let index = 0; index < count; index += stride) chosen.push(index);

  // 末桶保号。stride * slot ≥ minGap（由 capacity 的定义保证），所以最多丢一个就够。
  const last = count - 1;
  if (chosen[chosen.length - 1] !== last) {
    const previous = chosen[chosen.length - 1];
    if (centre(last) - centre(previous) < minGap) chosen.pop();
    chosen.push(last);
  }

  const right = plot.x + plot.w;
  return chosen.map((index) => {
    const half = widths[index] / 2;
    const middle = centre(index);
    // 贴边判断按"居中会不会探出去"做，而不是按"是不是第一个/最后一个"：中间那些桶
    // 在极窄的画布上同样会探出去。
    if (middle - half < plot.x) return { index, text: labels[index], x: plot.x, align: 'left' };
    if (middle + half > right) return { index, text: labels[index], x: right, align: 'right' };
    return { index, text: labels[index], x: middle, align: 'center' };
  });
}

/**
 * 画一根时间轴的标签。`baseline` 是文字顶沿的 y（三个调用点都用 `textBaseline: 'top'`）。
 *
 * **字体必须在调用前设好**：抽稀要量文字宽度，而宽度取决于当前的 `ctx.font`。三个调用点
 * 本来就在画 y 轴刻度时设过 `cssFont(11)`，所以这里不再设一次——重复设置会掩盖"某处忘了
 * 设"这件事（`stacked-bar` 就曾经漏成 `10px sans-serif`）。
 */
export function drawTimeAxis(
  ctx: CanvasRenderingContext2D,
  labels: readonly string[],
  plot: AxisSpan,
  baseline: number,
  color: string,
): void {
  const ticks = timeAxisTicks(labels, plot, (text) => ctx.measureText(text).width);
  if (!ticks.length) return;
  ctx.fillStyle = color;
  ctx.textBaseline = 'top';
  for (const tick of ticks) {
    ctx.textAlign = tick.align;
    ctx.fillText(tick.text, tick.x, baseline);
  }
}
