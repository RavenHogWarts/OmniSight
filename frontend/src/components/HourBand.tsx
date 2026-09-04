// 每小时应用图标带（16 文档 §A1，前身 TimeLens 的「每小时」面板）。
//
// **为什么它不能被类别堆叠替代**：堆叠柱回答"这一小时是哪一类"，图标带回答"是哪一
// 个"。一天里 Code / Cursor / 终端同属"开发"，在堆叠柱上是一根同色柱子，而"上午在
// Cursor、下午在终端"恰是用户要看的那件事。
//
// 与前身的三处差异：
//   1. 不做 3D 翻转。前身把它藏在「所有使用」卡的背面、靠右键翻面（14 文档 §4.1 末
//      已否掉那个交互：窄屏妥协，且 prefers-reduced-motion 下无从降级）。
//   2. 图标地址由后端的 `icon_url` 给（前端不拼），它是 null 时直接首字母块——不发
//      一个注定 204 的请求（04 文档 §6 结尾）。
//   3. `+N` 的时长与后端的 `other_seconds` 同源，不在前端二次求和。
import { useEffect, useRef, useState } from 'react';
import { assetUrl } from '../core/api.ts';
import { formatDurationShort, formatPercent, initialOf } from '../domain/format.ts';
import { hide as hideTooltip, show as showTooltip } from './tooltip.tsx';

/** 一个图标槽的宽度（图标 26px + 间距 8px），与 hour-band.css 里的值一致。 */
const ICON_SLOT = 34;
/** `+N` 那一格预留的宽度。 */
const MORE_SLOT = 40;
/** 还没量到宽度时的容量（面板隐藏、或 ResizeObserver 第一次回调之前）。 */
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
  /** 为真时整块换成说明，绝不画一片 0。 */
  gap?: boolean;
}

function num(value: unknown): number {
  return Number(value) || 0;
}

export function HourBand({ hours, gap = false }: HourBandProps) {
  const root = useRef<HTMLDivElement | null>(null);
  const [capacity, setCapacity] = useState(CAPACITY_FALLBACK);

  // 一行放几个图标要按实测宽度算，因此宽度一变就得重算（前身在 resize 里做同一件事）。
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const measure = () => {
      // 容量按 apps 列的宽度算：整行减去小时标签那一列（CSS 里是 52px + 8px 间距）。
      // 量不到宽度时用兜底值而不是算出 NaN——面板在隐藏容器里渲染是常态（切视图的
      // 那一帧），而 NaN 会让整行的图标全折进 `+N`。
      const width = Math.max(0, (node.clientWidth || 0) - 60);
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
        />
      ))}
    </div>
  );
}

function HourRow({ item, capacity }: { item: HourEntry; capacity: number }) {
  const list = [...(item.apps || [])].sort((left, right) => num(right.seconds) - num(left.seconds));
  const visible = list.slice(0, capacity);
  const hiddenCount = Math.max(0, list.length - visible.length);
  const otherSeconds = num(item.other_seconds);
  // `+N` 同时代表"这一行装不下的"和"后端 top 之外的"：两者都是"还有别的应用"，
  // 分成两个记号只会让人以为是两件事。
  const moreCount = hiddenCount + (otherSeconds > 0 ? 1 : 0);
  const moreSeconds =
    list.slice(capacity).reduce((sum, app) => sum + num(app.seconds), 0) + otherSeconds;

  return (
    <div className="hour-band__row" data-empty={String(!(num(item.total_seconds) > 0))}>
      <span className="hour-band__hour numeric">{String(item.hour).padStart(2, '0')}:00</span>
      <div className="hour-band__apps">
        {visible.map((app) => (
          <IconCell key={app.app_id} app={app} hour={item.hour} />
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
function IconCell({ app, hour }: { app: HourApp; hour: number }) {
  const [broken, setBroken] = useState(false);
  const label = app.display_name || `应用 ${app.app_id}`;
  const duration = formatDurationShort(num(app.seconds));
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  return (
    <span
      className="hour-band__app"
      data-app-id={app.app_id}
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
