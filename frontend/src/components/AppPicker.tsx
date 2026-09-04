// 应用范围选择器（06 文档 §7 改进 3、14 文档 §2.19 P3-4、§4.6 第 3 项）。
//
// "全部应用 / 某个应用"是同一张热力图的两种范围，不是两个功能。原 KeyTrace 把它放在
// 页面最下方一个独立面板里，还需要另外连上 TimeLens——合并后它只是筛选行上的一个按钮。
//
// **形式是图标网格而不是下拉框。** 选应用这件事本来是**认图标**而不是读文字：图标是
// 区分 Chrome 与 Edge 最快的线索，而 select 把它整个丢掉了。三个分组沿用前身 KeyTrace
// 的那三个（最近使用 / 最多使用 / 正在运行）——它们分别回答"我刚才在用的那个"
// "我一直在用的那个""现在开着的那个"。
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { assetUrl } from '../core/api.ts';
import { getState, setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { formatDayTime, formatDuration, initialOf } from '../domain/format.ts';
import { Icon } from './Icon.tsx';
import { SearchBox, Segmented } from './controls.tsx';

const GROUPS = [
  { id: 'recent', name: '最近使用' },
  { id: 'most_used', name: '最多使用' },
  { id: 'running', name: '正在运行' },
];
const FOCUSABLE = 'button:not([disabled]), input:not([disabled])';
/** 一屏最多铺多少格。再多就该用搜索，而不是往下滚一整屏图标。 */
const GRID_LIMIT = 60;

/** `/apps` 的行（带 icon_url / total_seconds / last_seen_at）。 */
export interface PickerApp {
  app_id: number;
  display_name?: string;
  user_alias?: string | null;
  process_name?: string;
  icon_url?: string | null;
  total_seconds?: number;
  total_seconds_formatted?: string;
  last_seen_at?: string | null;
}

export interface AppPickerProps {
  apps: readonly PickerApp[] | undefined;
  /** `/apps/running` 里**已记录**应用的 id 集合。 */
  runningIds?: Iterable<number>;
  onChange?: ((appId: number | null) => void) | null;
}

function num(value: unknown): number {
  return Number(value) || 0;
}

function stamp(app: PickerApp): string {
  return String(app.last_seen_at || '');
}

function haystack(app: PickerApp): string {
  return `${app.user_alias || ''} ${app.display_name || ''} ${app.process_name || ''}`.toLowerCase();
}

function emptyText(needle: string, group: string): string {
  if (needle) return '没有匹配的应用';
  return group === 'running' ? '当前没有已记录的应用在运行' : '这段时间还没有应用记录';
}

export function AppPicker({ apps, runningIds = [], onChange = null }: AppPickerProps) {
  const scopeAppId = useSlice('scopeAppId');
  const [open, setOpen] = useState(false);
  const [group, setGroup] = useState('recent');
  const [query, setQuery] = useState('');
  const root = useRef<HTMLDivElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  const list = apps || [];
  const running = new Set([...runningIds].filter((id) => typeof id === 'number'));

  // 选中的应用在新周期里不存在了：如实回落到全部，而不是显示一个空的过滤。
  useEffect(() => {
    const current = getState().scopeAppId;
    if (current && list.length && !list.some((app) => app.app_id === current)) {
      setState('scopeAppId', null);
    }
  }, [list]);

  // Esc 关闭、Tab 在弹层内循环——与抽屉同一套约定（06 文档 §13）。
  useEffect(() => {
    if (!open) return;
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        trigger.current?.focus();
        return;
      }
      if (event.key !== 'Tab') return;
      const host = panel.current;
      if (!host) return;
      const items = [...host.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (node) => node.offsetParent !== null,
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener('keydown', onKeydown, true);
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => {
      document.removeEventListener('keydown', onKeydown, true);
      document.removeEventListener('pointerdown', onPointerDown, true);
    };
  }, [open]);

  const pick = (appId: number | null) => {
    setState('scopeAppId', appId);
    setOpen(false);
    trigger.current?.focus();
    onChange?.(appId);
  };

  const ordered = () => {
    const copy = [...list];
    if (group === 'running') {
      // 只列**已记录过**的应用：running 里 app_id 为 null 的那些没有统计可看，
      // 拿它们去过滤热力图只会得到一张空图。
      return copy
        .filter((app) => running.has(app.app_id))
        .sort((left, right) => stamp(right).localeCompare(stamp(left)));
    }
    if (group === 'most_used') {
      return copy.sort((left, right) => num(right.total_seconds) - num(left.total_seconds));
    }
    return copy.sort((left, right) => stamp(right).localeCompare(stamp(left)));
  };

  /** 副行随分组变：三个分组各自回答的问题不同，副行必须跟着换（KeyTrace 也是这样）。 */
  const metaOf = (app: PickerApp): string => {
    if (group === 'running') return '窗口正在运行';
    if (group === 'most_used') {
      return app.total_seconds_formatted || formatDuration(num(app.total_seconds));
    }
    return app.last_seen_at ? `最近 ${formatDayTime(app.last_seen_at)}` : app.process_name || '';
  };

  const needle = query.toLowerCase();
  const matched = ordered().filter((app) => !needle || haystack(app).includes(needle));
  const current = list.find((app) => app.app_id === scopeAppId) || null;

  return (
    <div className="app-picker" ref={root}>
      <span className="muted text-sm">范围</span>
      <button
        className="button app-picker__trigger"
        type="button"
        ref={trigger}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          // 每次打开都从完整网格开始：上一次的搜索词留着会让"全部应用"那一格不在场
          // （搜索时它按设计隐藏），于是想切回全部的人找不到入口。
          if (!open) setQuery('');
          setOpen((value) => !value);
        }}
      >
        <span className="app-picker__mark">{current ? <Mark app={current} /> : null}</span>
        <span className="app-picker__name">
          {current ? current.user_alias || current.display_name : '全部应用'}
        </span>
        <Icon name="down" size={14} />
      </button>
      <div
        className="app-picker__panel"
        ref={panel}
        hidden={!open}
        role="dialog"
        aria-label="选择应用范围"
      >
        <div className="app-picker__head">
          {/* key 让搜索框在每次打开时重挂载，从而清掉上一次的输入。 */}
          <SearchBox key={open ? 'open' : 'closed'} placeholder="搜索应用" onInput={setQuery} />
          <Segmented items={GROUPS} active={group} onPick={setGroup} small label="应用分组" />
        </div>
        <div className="app-picker__grid">
          {needle ? null : (
            <Cell
              active={!scopeAppId}
              label="全部应用"
              meta={`${list.length} 个应用`}
              mark={<Icon name="apps" size={18} />}
              onPick={() => pick(null)}
            />
          )}
          {matched.slice(0, GRID_LIMIT).map((app) => (
            <Cell
              key={app.app_id}
              active={scopeAppId === app.app_id}
              label={app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`}
              meta={metaOf(app)}
              mark={<Mark app={app} />}
              onPick={() => pick(app.app_id)}
            />
          ))}
          {matched.length ? null : <div className="app-picker__empty">{emptyText(needle, group)}</div>}
          {matched.length > GRID_LIMIT ? (
            <div className="app-picker__empty">还有 {matched.length - GRID_LIMIT} 个，用搜索找</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Cell({
  active,
  label,
  meta,
  mark,
  onPick,
}: {
  active: boolean;
  label: string;
  meta: string;
  mark: ReactNode;
  onPick: () => void;
}) {
  return (
    <button className="app-picker__cell" type="button" aria-pressed={active} onClick={onPick}>
      {mark}
      <span className="app-picker__copy">
        <span className="app-picker__label">{label}</span>
        <span className="app-picker__meta">{meta}</span>
      </span>
    </button>
  );
}

/** 图标取不到就是首字母块——与应用列表同一条兜底路径。 */
function Mark({ app }: { app: PickerApp }) {
  const [broken, setBroken] = useState(false);
  const label = app.user_alias || app.display_name || '?';
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  if (!url || broken) return <span className="app-picker__initial">{initialOf(label)}</span>;
  return (
    <img
      className="app-picker__icon"
      src={url}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setBroken(true)}
    />
  );
}
