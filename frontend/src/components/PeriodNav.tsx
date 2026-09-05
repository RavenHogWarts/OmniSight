// 周期控件（17 文档 §4.1）。前身把它拆成**两条居中的定宽带**，我们照搬：
//
//     ‹ [查看日期 2026-09-04] ›  今天      420px  .datebar   ← DateBar
//     每天│每周│每月│每年│总计            520px  .rangebar  ← RangeBar
//
// 三处相对现状的改动：
//
// 1. **原生 `<input type="date">` 常驻**（前身就是这个）。原先是「翻页器 + 今天 +
//    『自定义…』按钮 + 两个日期框」，改一天要点两次；原生控件自带日历弹层与键盘输入。
// 2. **阅读顺序从粗到细**：哪一天 → 哪一段 → 看哪一类（视图带）→ 哪个指标（指标带）。
// 3. **视图级筛选插槽取消**。原先键盘的范围/指标、应用的搜索/排序都 portal 到周期栏
//    右段，那一行因此越挤越长；现在指标带是它自己的一条（`METRIC_SLOT_ID`），其余
//    筛选控件回到各自那张卡的卡头上——它们本来就只作用于那一块内容。
//
// **在所有视图间共享状态**——从总览切到键盘时选中的日期不变。这是旧版两个应用最割裂
// 的地方：各自维护独立的日期状态，切换程序等于重新选一次日期。
import { useEffect, useRef, useState } from 'react';
import { getState, setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { formatClock } from '../domain/format.ts';
import { RANGES } from '../domain/metrics.ts';
import { canGoForward, caliberNotes, isPageable, shift, todayISO } from '../domain/period.ts';
import { Icon } from './Icon.tsx';
import { Segmented } from './controls.tsx';

/** 指标带的 portal 目标（模板里的 `<div class="metricbar" id="metricbar">`）。 */
export const METRIC_SLOT_ID = 'metricbar';

/** 范围预设里不含 custom：它由日期控件右端那个小按钮进入，不占一个常驻档位。 */
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

/** 日期条。四格网格：翻页 / 日期 / 翻页 / 今天，与前身逐格对应。 */
export function DateBar() {
  const period = useSlice('period');
  const periodMeta = useSlice('periodMeta');
  const today = todayISO();
  const pageable = isPageable(period.range);
  const isCustom = period.range === 'custom';
  // 「总计」没有可翻的页，也没有可选的日期——前身在这一档把整条日期条置灰，照搬。
  const frozen = period.range === 'total';

  return (
    <>
      <button
        className="round-btn"
        type="button"
        aria-label="上一个周期"
        title="上一个周期"
        disabled={!pageable}
        onClick={() => step(-1)}
      >
        <Icon name="left" />
      </button>

      {isCustom ? (
        <CustomRange />
      ) : (
        <label className={frozen ? 'date-control date-control--disabled' : 'date-control'}>
          <span className="date-control__label">查看日期</span>
          <input
            type="date"
            max={today}
            disabled={frozen}
            aria-label="查看日期"
            value={anchorValue(period.date, periodMeta?.anchor)}
            onChange={(event) => {
              if (!event.target.value) return;
              setState('period', { ...period, date: event.target.value, start: null, end: null });
            }}
          />
          <RangeToggle active={false} />
        </label>
      )}

      <button
        className="round-btn"
        type="button"
        aria-label="下一个周期"
        title="下一个周期"
        disabled={!pageable || !canGoForward(period.range, anchorOf(), today)}
        onClick={() => step(1)}
      >
        <Icon name="right" />
      </button>

      <button
        className="pill-btn"
        type="button"
        disabled={frozen || Boolean(periodMeta?.is_current)}
        onClick={goToday}
      >
        今天
      </button>
    </>
  );
}

/** 日期框要一个 `YYYY-MM-DD`：后端规整过的锚点优先，否则用本地选择，最后退今天。 */
function anchorValue(date: string | null, anchor: string | null | undefined): string {
  return date || anchor || todayISO();
}

/**
 * 自定义区间的入口/出口（17 文档 §6.1）。
 *
 * 它是日期控件**里面**的一个小按钮，而不是控件带上的第五格：420px 的四格几何来自
 * 前身，为一个少数场景常驻两个日期框会把它顶开。前身没有自定义区间这个功能，所以
 * 这一处没有可照搬的形状——收进控件内部是"不破坏几何"与"不删功能"的交点。
 *
 * **用文字而不是图标**：`<input type="date">` 自带一个日历图标，再放一个日历图标在它
 * 右边就是两个日历并排，读者无从知道哪个开哪个。两个字反而没有歧义。
 */
function RangeToggle({ active }: { active: boolean }) {
  return (
    <button
      className="date-control__toggle"
      type="button"
      aria-pressed={active}
      aria-label={active ? '退出自定义区间' : '选择自定义区间'}
      title={active ? '退出自定义区间，回到按天翻页' : '改成自定义起止日期'}
      onClick={(event) => {
        // 它长在 <label> 里：不拦住冒泡的话点它会连带聚焦日期输入并弹出日历。
        event.preventDefault();
        event.stopPropagation();
        if (active) pickRange('day');
        else pickRange('custom');
      }}
    >
      区间
    </button>
  );
}

function CustomRange() {
  const period = useSlice('period');
  const today = todayISO();
  const apply = (start: string, end: string) => {
    if (!start || !end) return;
    setState('period', { range: 'custom', date: null, start, end });
  };
  return (
    <div className="date-control date-control--range">
      <input
        type="date"
        max={today}
        aria-label="起始日期"
        value={period.start || ''}
        onChange={(event) => apply(event.target.value, period.end || '')}
      />
      <span className="date-control__dash" aria-hidden="true">
        –
      </span>
      <input
        type="date"
        max={today}
        aria-label="结束日期"
        value={period.end || ''}
        onChange={(event) => apply(period.start || '', event.target.value)}
      />
      <RangeToggle active />
    </div>
  );
}

/**
 * 范围带 + 它下面那行口径注记。
 *
 * 注记存在的理由：日期控件里只有**一个**日期，而选「每周」时这一屏覆盖的是哪七天
 * 得有个落脚处——后端算好的 `periodMeta.label` 就放在这里（前端不自己算星期）。
 */
export function RangeBar() {
  const period = useSlice('period');
  const periodMeta = useSlice('periodMeta');
  const coverage = useSlice('coverage');
  const notes = caliberNotes(coverage);
  const label = period.range === 'day' ? '' : periodMeta?.label || '';

  return (
    <>
      <Segmented
        items={PRESETS}
        active={period.range}
        onPick={pickRange}
        variant="lg"
        label="时间范围"
      />
      {label || notes.length ? (
        <p className="periodnote" aria-live="polite">
          {label}
          {label && notes.length ? ' · ' : ''}
          {notes.length ? `${notes[0].from} 至 ${notes[0].to} 口径不同：${notes[0].message}` : ''}
        </p>
      ) : null}
    </>
  );
}

/**
 * 数据新鲜度（17 文档 §8 的 D9）。**常驻**：前身每一段标题右侧都有这行小字，而我们
 * 原先只在实时通道降级时才显示它（16 文档 §A6 的结论），于是屏幕上没有任何地方说得出
 * 这屏数字算于何时。SSE 正常时它每次重取都会更新，不是噪声。
 */
export function Updated() {
  const data = useSlice('data');
  const live = useSlice('live');
  const [fetchedAt, setFetchedAt] = useState<Date | null>(() => new Date());
  const first = useRef(true);

  useEffect(() => {
    // 首次挂载时 data 已经有内容了（首屏取数在挂载前发出），初值就是那一刻。
    if (first.current) {
      first.current = false;
      return;
    }
    setFetchedAt(new Date());
  }, [data]);

  if (!fetchedAt) return null;
  const suffix = live.mode === 'stream' ? '' : '（轮询）';
  return (
    <p className="updated">
      更新于 {formatClock(fetchedAt.toISOString())}
      {suffix}
    </p>
  );
}
