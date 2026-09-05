// 每小时应用图标带（16 文档 §A1，前身 TimeLens 的「每小时」面板）。
//
// **为什么它不能被类别堆叠替代**：堆叠柱回答"这一小时是哪一类"，图标带回答"是哪一
// 个"。一天里 Code / Cursor / 终端同属"开发"，在堆叠柱上是一根同色柱子，而"上午在
// Cursor、下午在终端"恰是用户要看的那件事。
//
// **几何与前身逐格一致**（`refer/TimeLens/src/static/style.css` 的 `.hourly-icon-*`、
// `templates/dashboard.html` 的 `renderHourlyIconList`）：单列 24 行、小时列 54px、行高
// 45px、每行一条上边线、图标 28px、槽宽 36px、`+N` 38px。一度加过的第三列（这一小时的
// 合计）与两列 12 行的对折都已撤回——前身那一块是通栏单列，它待在整页宽的 `.all-section`
// 里，不是副列里的窄卡。
//
// 仍与前身不同的三处，都不在几何上：
//   1. 悬浮用我们的 tooltip（时长 + 占这一小时，两行），前身用原生 `title`：原生提示
//      延迟约半秒、不能分行，样式也不受控。
//   2. 图标地址由后端的 `icon_url` 给（前端不拼），它是 null 时直接首字母块——不发一个
//      注定 204 的请求（04 文档 §6 结尾）。前身总是先发请求、失败再把 `<img>` 撤掉。
//   3. `+N` 的时长与后端的 `other_seconds` 同源，不在前端二次求和：前身的 hourly 接口
//      不限个数，我们每小时最多回 20 个，少了这一项就会静默少报。
import { useEffect, useRef, useState } from 'react';
import { assetUrl } from '../core/api.ts';
import { formatDurationShort, formatPercent, initialOf } from '../domain/format.ts';
import { hide as hideTooltip, show as showTooltip } from './tooltip.tsx';

/** 一个图标槽的宽度（图标 28px + 间距 8px），与 hour-band.css 里的值一致；前身同值。 */
const ICON_SLOT = 36;
/** `+N` 那一格占掉的宽度（38px + 8px 间距）。 */
const MORE_SLOT = 46;
/** 还没量到宽度时的容量（面板隐藏、或 ResizeObserver 第一次回调之前）。
 *
 *  通栏一行的图标格宽约 1036 − 28（卡内边距）− 54 − 12 ≈ 940px，即 26 个图标槽，比后端
 *  `top=20` 还多——所以兜底值给 8 只是"先画一部分"，量到宽度之后立刻补齐。 */
const CAPACITY_FALLBACK = 8;
const HOURS = Array.from({ length: 24 }, (_unused, hour) => hour);

interface HourApp {
  app_id: number;
  display_name?: string;
  icon_url?: string | null;
  seconds?: number;
  percent?: number;
}

export interface HourEntry {
  hour: number;
  total_seconds?: number;
  other_seconds?: number;
  apps?: readonly HourApp[];
}

export interface HourBandProps {
  /** 直接来自 `/usage/timeline`。 */
  hours: readonly HourEntry[] | undefined;
  /**
   * `app_id → 类别 id`。`/usage/timeline` 的小时行**不带类别**，而首字母兜底块要按类别
   * 上色（与「所有使用」一致）——所以由调用方从同一屏已经取到的应用列表里给一张表，
   * 而不是为这一个色块多发一个请求，也不是在后端加字段。
   */
  categories?: ReadonlyMap<number, string> | null;
  /** 为真时整块换成说明，绝不画一片 0。 */
  gap?: boolean;
}

function num(value: unknown): number {
  return Number(value) || 0;
}

export function HourBand({ hours, categories = null, gap = false }: HourBandProps) {
  const root = useRef<HTMLDivElement | null>(null);
  const [capacity, setCapacity] = useState(CAPACITY_FALLBACK);

  // 一行放几个图标要按实测宽度算，因此宽度一变就得重算（前身在 resize 里做同一件事）。
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const measure = () => {
      // **量真正的 apps 单元格**，不是"整行减去一个写死的数字"（前身是后者：
      // `listWidth - 66`）。小时列的宽度在 CSS 里，在 JS 里复述一遍必然有一天对不上。
      // 量不到宽度时用兜底值而不是算出 NaN——面板在隐藏容器里渲染是常态（切视图的那一
      // 帧），而 NaN 会让整行的图标全折进 `+N`。
      const cell = node.querySelector('.hour-band__apps');
      const width = cell ? cell.clientWidth : 0;
      setCapacity(width ? Math.max(1, Math.floor((width - MORE_SLOT) / ICON_SLOT)) : CAPACITY_FALLBACK);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => () => hideTooltip(), []);

  if (gap) {
    return (
      <div className="hour-band" ref={root}>
        <div className="hour-band__gap">该时段没有采集记录（不是 0）</div>
      </div>
    );
  }

  const byHour = new Map((hours || []).map((item) => [item.hour, item]));
  return (
    <div className="hour-band" ref={root} onPointerLeave={() => hideTooltip()}>
      {HOURS.map((hour) => (
        <HourRow
          key={hour}
          item={byHour.get(hour) || { hour, total_seconds: 0, apps: [], other_seconds: 0 }}
          capacity={capacity}
          categories={categories}
        />
      ))}
    </div>
  );
}

function HourRow({
  item,
  capacity,
  categories,
}: {
  item: HourEntry;
  capacity: number;
  categories: ReadonlyMap<number, string> | null;
}) {
  const list = [...(item.apps || [])].sort((left, right) => num(right.seconds) - num(left.seconds));
  const visible = list.slice(0, capacity);
  const hiddenCount = Math.max(0, list.length - visible.length);
  const otherSeconds = num(item.other_seconds);
  // `+N` 同时代表"这一行装不下的"和"后端 top 之外的"：两者都是"还有别的应用"，
  // 分成两个记号只会让人以为是两件事。
  const moreCount = hiddenCount + (otherSeconds > 0 ? 1 : 0);
  const moreSeconds =
    list.slice(capacity).reduce((sum, app) => sum + num(app.seconds), 0) + otherSeconds;

  // 空行什么都不画——它靠自己那条上边线在场（前身如此）。24 行一行不少："这一小时什么
  // 都没干"本身是信息，跳过它会让读者以为那一小时不存在。
  return (
    <div className="hour-band__row">
      <span className="hour-band__hour">{String(item.hour).padStart(2, '0')}:00</span>
      <div className="hour-band__apps">
        {visible.map((app) => (
          <IconCell
            key={app.app_id}
            app={app}
            hour={item.hour}
            category={categories?.get(app.app_id)}
          />
        ))}
        {moreCount ? (
          <span
            className="hour-band__more"
            onPointerEnter={(event) =>
              showTooltip({
                title: `另外 ${moreCount} 个应用`,
                rows: [['时长', formatDurationShort(moreSeconds)]],
                x: event.clientX,
                y: event.clientY,
              })
            }
          >
            +{moreCount}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/** 图标取不到就是首字母块——`icons` 能力缺失的机器上这是常态，不是异常。 */
function IconCell({
  app,
  hour,
  category,
}: {
  app: HourApp;
  hour: number;
  category?: string;
}) {
  const [broken, setBroken] = useState(false);
  const label = app.display_name || `应用 ${app.app_id}`;
  const duration = formatDurationShort(num(app.seconds));
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  return (
    <span
      className="hour-band__app"
      data-app-id={app.app_id}
      data-category={category}
      aria-label={`${String(hour).padStart(2, '0')}:00 ${label} ${duration}`}
      onPointerEnter={(event) =>
        showTooltip({
          title: label,
          rows: [
            ['时长', duration],
            ['占这一小时', formatPercent(num(app.percent))],
          ],
          x: event.clientX,
          y: event.clientY,
        })
      }
    >
      {!url || broken ? (
        <span className="hour-band__initial">{initialOf(label)}</span>
      ) : (
        <img
          className="hour-band__icon"
          src={url}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setBroken(true)}
        />
      )}
    </span>
  );
}
