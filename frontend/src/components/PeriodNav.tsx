// 周期栏（06 文档 §4.1、14 文档 §2.12/§4.1）。**在所有视图间共享状态**——从总览切到
// 键盘时选中的日期不变。这是旧版两个应用最割裂的地方：各自维护独立的日期状态，切换
// 程序等于重新选一次日期。
//
// 两处相对现状的改动：
//
// 1. **阅读顺序**。现状的挂载顺序是「翻页器 → 今天 → 自定义日期 → 范围预设」，也就是
//    用户最先要伸手的控件（范围预设）在最右边，而更细的自定义日期在它左边——先看到细
//    的、后看到粗的。现在是「范围 → 翻页器 → 今天 → 自定义…」，从粗到细。
// 2. **视图级筛选插槽**。键盘的范围/指标、应用的搜索/排序原本长在卡片头上，作用域却是
//    整个视图——看起来是那张卡的开关，实际改了整屏（14 文档 §2.8）。它们现在挂进这一
//    行的右段。界线：**改请求参数的控件在筛选行，改渲染方式的控件留在卡头。**
//
// 插槽的实现是 **portal**（`FILTERS_SLOT_ID`）：视图把自己的筛选控件 portal 到这里，
// 于是那些控件仍然长在视图自己的组件树里（能直接读写视图状态），而位置在周期栏上。
// 换成"把节点交给周期栏"的写法就得再造一个 store，且筛选控件会离开它所属的视图。
import { useEffect, useRef, useState } from 'react';
import { getState, setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { formatClock } from '../domain/format.ts';
import { RANGES } from '../domain/metrics.ts';
import { canGoForward, isPageable, shift, todayISO } from '../domain/period.ts';
import { Icon } from './Icon.tsx';
import { Segmented } from './controls.tsx';

/** 视图级筛选的 portal 目标。视图用 `createPortal(..., document.getElementById(...))`。 */
export const FILTERS_SLOT_ID = 'periodbar-filters';

/** 范围预设里不含 custom：它由「自定义…」按钮进入，不占一个常驻档位。 */
const PRESETS = RANGES.filter((range) => range.id !== 'custom');

/** 锚点优先用后端规整过的值，否则退回本地选择。 */
function anchorOf(): string {
  const { period, periodMeta } = getState();
  return periodMeta?.anchor || period.date || todayISO();
}

export function step(direction: number): void {
  const { period } = getState();
  if (!isPageable(period.range)) return;
  if (direction > 0 && !canGoForward(period.range, anchorOf(), todayISO())) return;
  setState('period', { ...period, date: shift(period.range, anchorOf(), direction) });
}

export function pickRange(id: string): void {
  const { periodMeta } = getState();
  if (id === 'custom') {
    const end = periodMeta?.truncated_end || todayISO();
    const start = periodMeta?.start || end;
    setState('period', { range: 'custom', date: null, start, end });
    return;
  }
  setState('period', { range: id, date: anchorOf(), start: null, end: null });
}

export function goToday(): void {
  setState('period', { ...getState().period, date: todayISO() });
}

export function PeriodNav() {
  const period = useSlice('period');
  const periodMeta = useSlice('periodMeta');
  const pageable = isPageable(period.range);
  const isCustom = period.range === 'custom';

  return (
    <>
      <Segmented items={PRESETS} active={period.range} onPick={pickRange} label="时间范围" />
      <div className="periodbar__nav">
        <button
          className="icon-button"
          type="button"
          aria-label="上一个周期"
          disabled={!pageable}
          onClick={() => step(-1)}
        >
          <Icon name="left" />
        </button>
        {/* 标题一律用后端给的 label：前端不会算"9月2日 周三"里的星期，也不该算。 */}
        <div className="period-label" aria-live="polite">
          {periodMeta?.label || '…'}
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="下一个周期"
          disabled={!pageable || !canGoForward(period.range, anchorOf(), todayISO())}
          onClick={() => step(1)}
        >
          <Icon name="right" />
        </button>
      </div>
      <button
        className="button"
        type="button"
        hidden={period.range === 'total' || Boolean(periodMeta?.is_current)}
        onClick={goToday}
      >
        今天
      </button>
      {/* 自定义收在一个按钮后面：它是少数场景，常驻两个日期框会把这一行挤满。 */}
      <button
        className="button"
        type="button"
        hidden={isCustom}
        aria-expanded={isCustom}
        onClick={() => pickRange('custom')}
      >
        自定义…
      </button>
      {isCustom ? <CustomRange /> : null}
      <span className="spacer" />
      <Freshness />
      <div className="periodbar__filters" id={FILTERS_SLOT_ID} />
    </>
  );
}

function CustomRange() {
  const period = useSlice('period');
  const apply = (start: string, end: string) => {
    if (!start || !end) return;
    setState('period', { range: 'custom', date: null, start, end });
  };
  return (
    <div className="period-custom">
      <input
        type="date"
        className="control"
        aria-label="起始日期"
        value={period.start || ''}
        onChange={(event) => apply(event.target.value, period.end || '')}
      />
      <span>–</span>
      <input
        type="date"
        className="control"
        aria-label="结束日期"
        value={period.end || ''}
        onChange={(event) => apply(period.start || '', event.target.value)}
      />
    </div>
  );
}

/**
 * 数据新鲜度（16 文档 §A6）。**只在实时通道断掉时出现**：SSE 正常时数据一变就重取，
 * 常驻一行"更新于 刚刚"是噪声；而退到 30 秒轮询后，屏幕上原本没有任何地方说得出
 * 这屏数字算于何时（前身 TimeLens 的 `.updated` 是常驻的，它没有实时通道）。
 */
function Freshness() {
  const data = useSlice('data');
  const live = useSlice('live');
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  // 首次挂载时 data 已经有内容了（首屏取数在挂载前发出），那一次不算"更新"。
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setFetchedAt(new Date());
  }, [data]);

  const stamp = live.mode === 'stream' ? null : fetchedAt;
  if (!stamp) return null;
  return (
    <span className="periodbar__freshness numeric">更新于 {formatClock(stamp.toISOString())}</span>
  );
}
