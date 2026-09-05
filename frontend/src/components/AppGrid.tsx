// 应用图标网格（17 文档 §4.4，KeyTrace 应用分类屏的主体）。
//
// 选应用这件事本来是**认图标**而不是读文字：图标是区分 Chrome 与 Edge 最快的线索，
// 而 `<select>` 把它整个丢掉了。三个分组沿用前身的那三个（最近使用 / 最多使用 /
// 正在运行）——它们分别回答"我刚才在用的那个""我一直在用的那个""现在开着的那个"。
//
// **一份实现服务两处**（这是它从 AppPicker 里抽出来的理由）：
//   应用视图  一整块常驻面板，就是 KeyTrace 的那一屏
//   键盘视图  收在 AppPicker 的弹层里（那一屏没有空间放整块网格）
import { useState } from 'react';
import { assetUrl } from '../core/api.ts';
import { setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { formatDayTime, formatDuration, initialOf } from '../domain/format.ts';
import { Icon } from './Icon.tsx';
import { SearchBox, Segmented } from './controls.tsx';

export const GROUPS = [
  { id: 'recent', name: '最近使用' },
  { id: 'most_used', name: '最多使用' },
  { id: 'running', name: '正在运行' },
];

/** 一屏最多铺多少格。再多就该用搜索，而不是往下滚一整屏图标。 */
const GRID_LIMIT = 60;

/** `/apps` 的行（带 icon_url / total_seconds / last_seen_at）。 */
export interface PickerApp {
  app_id: number;
  display_name?: string;
  user_alias?: string | null;
  process_name?: string;
  category?: string;
  icon_url?: string | null;
  total_seconds?: number;
  total_seconds_formatted?: string;
  last_seen_at?: string | null;
}

export interface AppGridProps {
  apps: readonly PickerApp[] | undefined;
  /** `/apps/running` 里**已记录**应用的 id 集合。 */
  runningIds?: Iterable<number>;
  /** 当前选中的应用；`null` = 全部应用。 */
  selectedId: number | null;
  onPick: (appId: number | null) => void;
  /** 是否给出「全部应用」那一格。应用视图给，键盘视图的弹层也给。 */
  allowAll?: boolean;
  /** 搜索框重挂载的钥匙：弹层每次打开都要清掉上一次的输入。 */
  searchKey?: string;
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

export function AppGrid({
  apps,
  runningIds = [],
  selectedId,
  onPick,
  allowAll = true,
  searchKey = 'grid',
}: AppGridProps) {
  // 分组是**共享**的（core/store.ts 的 appsGroup）：同一份网格出现在应用面板与键盘
  // 视图的弹层里，在一处切了分组、另一处不该退回默认。搜索词相反——它是这一次打开
  // 这一个网格的临时输入，因此仍是本地 state。
  const group = useSlice('appsGroup');
  const setGroup = (id: string) => setState('appsGroup', id);
  const [query, setQuery] = useState('');
  const list = apps || [];
  const running = new Set([...runningIds].filter((id) => typeof id === 'number'));

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

  /** 副行随分组变：三个分组各自回答的问题不同，副行必须跟着换（前身也是这样）。 */
  const metaOf = (app: PickerApp): string => {
    if (group === 'running') return '窗口正在运行';
    if (group === 'most_used') {
      return app.total_seconds_formatted || formatDuration(num(app.total_seconds));
    }
    return app.last_seen_at ? `最近 ${formatDayTime(app.last_seen_at)}` : app.process_name || '';
  };

  const needle = query.toLowerCase();
  const matched = ordered().filter((app) => !needle || haystack(app).includes(needle));

  return (
    <>
      <div className="app-grid__filters">
        {/* key 让搜索框在每次打开时重挂载，从而清掉上一次的输入。 */}
        <SearchBox key={searchKey} placeholder="搜索应用" onInput={setQuery} />
        <div className="app-grid__groups">
          <Segmented
            items={GROUPS}
            active={group}
            onPick={setGroup}
            variant="lg"
            label="应用分组"
          />
        </div>
      </div>
      <div className="app-grid">
        {/* 搜索时「全部应用」按设计隐藏，所以搜索框清空后它必须回来——否则想切回全部
            的人找不到入口。 */}
        {allowAll && !needle ? (
          <Cell
            active={!selectedId}
            label="全部应用"
            meta={`${list.length} 个应用`}
            mark={<Icon name="apps" size={18} />}
            onPick={() => onPick(null)}
          />
        ) : null}
        {matched.slice(0, GRID_LIMIT).map((app) => (
          <Cell
            key={app.app_id}
            active={selectedId === app.app_id}
            category={app.category}
            label={app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`}
            meta={metaOf(app)}
            mark={<Mark app={app} />}
            onPick={() => onPick(app.app_id)}
          />
        ))}
        {matched.length ? null : (
          <div className="app-grid__empty">{emptyText(needle, group)}</div>
        )}
        {matched.length > GRID_LIMIT ? (
          <div className="app-grid__empty">还有 {matched.length - GRID_LIMIT} 个，用搜索找</div>
        ) : null}
      </div>
    </>
  );
}

function Cell({
  active,
  label,
  meta,
  mark,
  category,
  onPick,
}: {
  active: boolean;
  label: string;
  meta: string;
  mark: React.ReactNode;
  category?: string;
  onPick: () => void;
}) {
  return (
    <button
      className="app-grid__cell"
      type="button"
      aria-pressed={active}
      data-category={category}
      onClick={onPick}
    >
      {mark}
      <span className="app-grid__cell-copy">
        <span className="app-grid__label" title={label}>
          {label}
        </span>
        <span className="app-grid__meta">{meta}</span>
      </span>
    </button>
  );
}

/** 图标取不到就是首字母块——与使用列表同一条兜底路径。 */
export function Mark({ app }: { app: PickerApp }) {
  const [broken, setBroken] = useState(false);
  const label = app.user_alias || app.display_name || '?';
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  if (!url || broken) return <span className="app-grid__initial">{initialOf(label)}</span>;
  return (
    <img
      className="app-grid__icon"
      src={url}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setBroken(true)}
    />
  );
}

/**
 * 42px 的选中应用头像（应用视图的面板头）。与 `Mark` 同一条兜底路径，只是更大。
 *
 * `app` 为 null 是「全部应用」那一态，**不是取图标失败**——所以它画网格图标而不是
 * 一个 `?` 首字母块（后者读起来像出错了）。
 */
export function BigMark({ app }: { app: PickerApp | null }) {
  const [broken, setBroken] = useState(false);
  const url = app?.icon_url ? assetUrl(app.icon_url) : '';
  if (!app) {
    return (
      <span className="app-grid__mark-initial app-grid__mark-initial--all">
        <Icon name="apps" size={22} />
      </span>
    );
  }
  if (!url || broken) {
    return (
      <span className="app-grid__mark-initial">
        {initialOf(app.user_alias || app.display_name || '?')}
      </span>
    );
  }
  return (
    <img
      className="app-grid__mark"
      src={url}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setBroken(true)}
    />
  );
}
