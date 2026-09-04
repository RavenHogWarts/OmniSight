// 键盘热力图组件（06 文档 §7、07 文档 §6.4、14 文档 §2.4/§2.5/§4.4）。
//
// 着色写的是 `data-level`，颜色由 CSS 按档位选（现状 KeyTrace 的 blendHex() 在 JS 里
// 硬算颜色，无法适配主题）。**离散五档而不是连续插值**：图例的色块与键面渲染的因此是
// 同一组值，读者能把一个键的颜色对回一个值区间。
//
// 可访问性（07 文档 §9）：104 个键**不**全部进 Tab 序（会淹没导航），整块键盘是一个
// tabstop，方向键在键位间移动，当前键由 aria-activedescendant 指出。按键动画区
// aria-hidden 不适用（键面本身就是数据），但动画**不**进 live region——每秒数次播报
// 会让屏幕阅读器无法使用。
//
// **实时按压动画刻意绕过 React**（15 文档 §4.2 点明这一处）：`bus.on('key:press')`
// 直接往那一个键的节点上加 class。每秒数次的按键走 state 会让 104 个键的子树反复
// 参与调度，而它要表达的只是"这个键刚被按了一下"。节点从 ref 表里按 id 取。
import { useEffect, useMemo, useRef, useState } from 'react';
import { on as busOn } from '../core/bus.ts';
import { prefersReducedMotion } from '../core/theme.ts';
import { keyRows } from '../domain/keyboard-layout.ts';
import { KNOWN_SHAPES, isGap } from '../domain/keyboard-layout.ts';
import { formatCount, formatPercent } from '../domain/format.ts';
import {
  HEAT_BOUNDS,
  formatMetric,
  heatLevel,
  heatRatio,
  isSaturated,
  metricOf,
} from '../domain/metrics.ts';
import { Icon } from './Icon.tsx';
import { hide as hideTooltip, show as showTooltip } from './tooltip.tsx';
import type { HeatmapKey, HeatmapResponse, LayoutKey, LayoutResponse } from '../types/api.d.ts';

const PRESS_CLEAR_MS = 220;
/** 键面数值的字号地板。低于它宁可不印，也不印成 8px（14 文档 §2.5）。 */
const VALUE_MIN_PX = 11;
/** .key-cap__value 的字号系数，与 key-cap.css 里的 calc() 保持一致。 */
const VALUE_RATIO = 0.21;

export interface KeyboardViewProps {
  layout: LayoutResponse | null | undefined;
  /** `/keyboard/heatmap` 的响应。 */
  heatmap: HeatmapResponse | null | undefined;
  metric: string;
  /** 键盘密度（标准 / 紧凑）。标准优先保证 11px 数值，紧凑优先不横向滚动。 */
  density?: 'standard' | 'compact';
  onSelectKey?: ((keyId: string) => void) | null;
}

function clamp(value: number, low: number, high: number): number {
  if (high < low) return low;
  return Math.min(high, Math.max(low, value));
}

export function KeyboardView({
  layout,
  heatmap,
  metric,
  density = 'standard',
  onSelectKey = null,
}: KeyboardViewProps) {
  const board = useRef<HTMLDivElement | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const caps = useRef(new Map<string, HTMLElement>());
  const [cursor, setCursor] = useState({ row: 0, col: 0 });
  const [valuesVisible, setValuesVisible] = useState(true);

  const rows = useMemo(() => keyRows(layout), [layout]);
  const values = useMemo(
    () => new Map((heatmap?.keys || []).map((key) => [key.id, key])),
    [heatmap],
  );
  const scale = heatmap?.scale || null;
  const total = Number(heatmap?.totals?.press_count) || 0;
  const definition = metricOf(metric);

  // 布局换了（ANSI -> ISO）就从头开始导航，否则光标会指到一个不存在的键。
  useEffect(() => setCursor({ row: 0, col: 0 }), [layout]);

  useEffect(() => {
    const reduced = prefersReducedMotion();
    return busOn<string[]>('key:press', (keys) => {
      for (const keyId of keys) {
        const cap = caps.current.get(keyId);
        if (!cap) continue;
        cap.classList.add('is-pressed');
        // 动画类在下一帧后移除。reduced-motion 下 CSS 已把过渡关掉，类照加不影响。
        window.setTimeout(() => cap.classList.remove('is-pressed'), reduced ? 60 : PRESS_CLEAR_MS);
      }
    });
  }, []);

  /**
   * 键面装不下 11px 的数值就整体藏起来（14 文档 §2.5）。
   *
   * 现状的判据是"窗口 < 1024px"，但真正决定字号的是 --u：1280px 窗口下键面数值只有
   * 8.6px、1100px 下 7.4px，都低于全站 11px 的下限，而窗口宽度那条规则一个都拦不住。
   * 这里改成按实际 --u 算，同一条规则管所有宽度。值印不下时，表格视图仍然给得出。
   */
  useEffect(() => {
    const node = board.current;
    if (!node) return;
    const measure = () => {
      const host = root.current;
      if (!host) return;
      const unit = Number.parseFloat(getComputedStyle(host).getPropertyValue('--u')) || 0;
      // CSS 的 max() 会把字号托到 11px，但托上去就装不下——所以这里判断的是
      // "自然字号够不够 11px"，不够就不印。
      setValuesVisible(unit * VALUE_RATIO >= VALUE_MIN_PX);
    };
    measure();
    // --u 由 clamp(…, 3.0vw, …) 决定，窗口变化会改字号，因此值可见性要跟着重算。
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [layout, density]);

  useEffect(() => () => hideTooltip(), []);

  const currentKey = rows[cursor.row]?.[cursor.col] || null;

  const handleKeydown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
    };
    if (event.key === 'Enter' || event.key === ' ') {
      if (currentKey && onSelectKey) {
        onSelectKey(currentKey);
        event.preventDefault();
      }
      return;
    }
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    const nextRow = clamp(cursor.row + move[0], 0, rows.length - 1);
    const rowKeys = rows[nextRow] || [];
    setCursor({ row: nextRow, col: clamp(cursor.col + move[1], 0, rowKeys.length - 1) });
  };

  return (
    <>
      <div className="keyboard-wrap" ref={board}>
        <div
          className="keyboard"
          ref={root}
          data-family={layout?.family || 'unknown'}
          data-density={density === 'compact' ? 'compact' : undefined}
          data-values={valuesVisible ? 'on' : 'off'}
          role="group"
          aria-label={`键盘热力图（${layout?.name || '未知布局'}）`}
          tabIndex={0}
          aria-activedescendant={currentKey ? `key-${currentKey}` : undefined}
          onKeyDown={handleKeydown}
        >
          {(layout?.rows || []).map((row, rowIndex) => (
            <div className="keyboard__row" key={rowIndex}>
              {row.map((slot, slotIndex) =>
                isGap(slot) ? (
                  <Spacer key={`gap-${slotIndex}`} width={slot?.w} />
                ) : (
                  <KeyCap
                    key={slot.id}
                    slot={slot}
                    entry={values.get(slot.id)}
                    metric={metric}
                    scale={scale}
                    total={total}
                    current={slot.id === currentKey}
                    register={(node) => {
                      if (node) caps.current.set(slot.id, node);
                      else caps.current.delete(slot.id);
                    }}
                    onActivate={onSelectKey}
                  />
                ),
              )}
            </div>
          ))}
        </div>
      </div>
      <Legend definition={definition} scale={scale} />
      <Orphans keys={heatmap?.orphan_keys} metric={metric} />
      <KeyTable values={values} metric={metric} />
    </>
  );
}

function Spacer({ width }: { width?: number }) {
  return (
    <span
      className="key-spacer"
      aria-hidden="true"
      style={{ '--w': width ?? 1 } as React.CSSProperties}
    />
  );
}

interface KeyCapProps {
  slot: LayoutKey;
  entry: HeatmapKey | undefined;
  metric: string;
  scale: HeatmapResponse['scale'] | null;
  total: number;
  current: boolean;
  register: (node: HTMLElement | null) => void;
  onActivate: ((keyId: string) => void) | null;
}

function KeyCap({ slot, entry, metric, scale, total, current, register, onActivate }: KeyCapProps) {
  const shape = slot.shape && KNOWN_SHAPES.has(slot.shape) ? slot.shape : undefined;
  if (slot.shape && !shape) {
    // 后端加了本前端不认识的形状。画成矩形仍然可用，但要留下痕迹。
    console.warn(`未知键形 ${slot.shape}（${slot.id}），按矩形渲染`);
  }
  const definition = metricOf(metric);
  const value = entry ? Number((entry as unknown as Record<string, unknown>)[metric]) || 0 : 0;
  const ratio = heatRatio(value, scale);
  const label = slot.label || slot.id;
  const share =
    total && metric === 'press_count' ? `，占比 ${formatPercent((value / total) * 100)}` : '';

  return (
    <div
      // role="img" 而不是 button：104 个键全进 Tab 序会淹没导航，整块键盘是一个
      // tabstop，方向键在键位间移动（07 文档 §9）。
      role="img"
      id={`key-${slot.id}`}
      ref={register}
      className={current ? 'key-cap is-current' : 'key-cap'}
      data-key-id={slot.id}
      // 档位直接决定颜色（CSS 按 data-level 选色）。0 是零态：键面不填色，
      // 于是"按过一次"与"从没按过"差 2.4:1 而不是 1.07:1（14 文档 §2.4）。
      data-level={heatLevel(ratio)}
      data-saturated={isSaturated(value, scale) ? 'true' : undefined}
      data-shape={shape}
      aria-label={`${label}，${definition.name} ${definition.format(value)}${share}`}
      style={{ '--w': slot.w ?? 1, '--h': slot.h ?? 1 } as React.CSSProperties}
      onPointerEnter={(event) =>
        showTooltip({
          title: label,
          rows: entry
            ? [
                ['次数', formatCount(entry.press_count)],
                ['占比', formatPercent(entry.percent)],
                ['均时长', formatMetric('duration_avg_ms', entry.duration_avg_ms)],
              ]
            : [['次数', '0']],
          x: event.clientX,
          y: event.clientY,
        })
      }
      onPointerLeave={() => hideTooltip()}
      onClick={onActivate ? () => onActivate(slot.id) : undefined}
    >
      <span className="key-cap__label">{label}</span>
      {/* 键面上除填色外还印数值：色盲用户与打印场景都要可读（06 文档 §7 改进 2）。 */}
      <span className="key-cap__value">{value ? definition.format(value) : ''}</span>
    </div>
  );
}

function Legend({
  definition,
  scale,
}: {
  definition: ReturnType<typeof metricOf>;
  scale: HeatmapResponse['scale'] | null;
}) {
  const top = Number(scale?.p95) || 0;
  const max = Number(scale?.max) || 0;
  return (
    <div className="heat-legend">
      <span>未按过</span>
      <span className="heat-legend__scale" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5].map((level) => (
          <span
            key={level}
            className="heat-legend__step"
            data-level={level}
            // 标出每一档的值区间上界：色块与键面是同一组变量，读者由此能把一个键的
            // 颜色对回一个值区间——这是离散五档相对连续插值的全部意义（14 文档 §2.4）。
            title={level ? `≤ ${definition.format(top * HEAT_BOUNDS[level])}` : '未按过'}
          />
        ))}
      </span>
      <span>{definition.format(top)}</span>
      {/* p95 归一而不是最大值归一：空格键通常是第二名的 3 倍，用最大值会把其余键
          压成一片浅色，热力图读不出差异（06 文档 §7 改进 1）。 */}
      <span
        className="card__hint"
        title={`色阶按 p95（${definition.format(top)}）归一，超出的键饱和到最深并在右上角切一个缺口。最大值 ${definition.format(max)}。`}
        aria-label={`色阶按 p95 归一，最大值 ${definition.format(max)}`}
      >
        <span>p95 归一 </span>
        <Icon name="info" size={13} />
      </span>
    </div>
  );
}

/** 布局里没有的键（后端的 orphan_keys）。不渲染它们，键盘总数就与指标卡不一致。 */
function Orphans({ keys, metric }: { keys: readonly HeatmapKey[] | undefined; metric: string }) {
  if (!keys?.length) return null;
  return (
    <div className="orphans">
      <div className="orphans__title">不在当前布局中的键（{keys.length}）</div>
      <div className="orphans__list">
        {keys.map((key) => {
          const record = key as unknown as Record<string, unknown>;
          return (
            <span className="key-chip" key={key.id}>
              <b>{key.label || key.id}</b>
              <span>{formatMetric(metric, Number(record[metric] ?? key.press_count ?? 0))}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

/**
 * 表格孪生：每个键的完整读数，可复制（14 文档 §4.4）。
 *
 * 键盘是 DOM 而不是 canvas，所以它没有走 charts/Chart.tsx 的 sr-only 表格路径。
 * 这张折叠表补上，同时兜住"键面数值印不下"的场景。
 */
function KeyTable({ values, metric }: { values: Map<string, HeatmapKey>; metric: string }) {
  const definition = metricOf(metric);
  const read = (entry: HeatmapKey) =>
    Number((entry as unknown as Record<string, unknown>)[metric]) || 0;
  const list = [...values.values()].filter((entry) => read(entry) > 0).sort((a, b) => read(b) - read(a));
  return (
    <details className="keyboard-table">
      <summary>表格视图</summary>
      <div className="keyboard-table__scroll">
        <table className="table">
          <thead>
            <tr>
              <th>键位</th>
              <th>次数</th>
              <th>占比</th>
              <th>均时长</th>
            </tr>
          </thead>
          <tbody>
            {list.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.label || entry.id}</td>
                <td className="numeric">{definition.format(read(entry))}</td>
                <td className="numeric">{formatPercent(entry.percent)}</td>
                <td className="numeric">{formatMetric('duration_avg_ms', entry.duration_avg_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
