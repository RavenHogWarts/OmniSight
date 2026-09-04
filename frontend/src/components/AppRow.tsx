// 应用列表行（06 文档 §6，07 文档 §6.2）。
//
// keyed 更新原先是 core/dom.js 的 renderKeyed 以 app_id 复用节点；React 化之后由
// `key={app.app_id}` 负责，效果一致——**目的没变**：现状两个项目都用
// `innerHTML = rows.join('')` 全量重建，代价是图标每次刷新都重新发请求并闪烁、
// 滚动位置重置、无法做展开态。
import { useState } from 'react';
import { assetUrl } from '../core/api.ts';
import { formatCount, formatDuration, initialOf } from '../domain/format.ts';

/** 周期行与 /apps 元数据合并后的结果（见 views/apps.tsx 的 joinApps）。 */
export interface AppRowData {
  app_id: number;
  display_name?: string;
  user_alias?: string | null;
  process_name?: string;
  category?: string;
  category_name?: string | null;
  icon_url?: string | null;
  is_running?: boolean;
  seconds?: number;
  total_seconds?: number;
  seconds_formatted?: string;
  total_seconds_formatted?: string;
  percent?: number | null;
  presses?: number;
  total_presses?: number;
  kpm?: number;
}

export interface AppRowProps {
  app: AppRowData;
  maxSeconds?: number;
  maxKpm?: number;
  expanded?: boolean;
  onToggle?: ((appId: number) => void) | null;
}

export function AppRow({ app, maxSeconds = 0, maxKpm = 0, expanded = false, onToggle = null }: AppRowProps) {
  const label = app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`;
  const seconds = Number(app.seconds ?? app.total_seconds ?? 0);
  const pressCount = Number(app.presses ?? app.total_presses ?? 0);
  const kpm = Number(app.kpm || 0);
  const meta = [app.process_name, app.category_name || null].filter(Boolean).join(' · ');

  return (
    <div
      className="app-row"
      data-app-id={app.app_id}
      data-category={app.category || 'uncategorized'}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={() => onToggle?.(app.app_id)}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        onToggle?.(app.app_id);
      }}
    >
      <AppIcon iconUrl={app.icon_url} label={label} />
      <div className="app-row__main">
        <div className="app-row__name">
          <span className="truncate">{label}</span>
          {app.is_running ? <span className="app-row__running" title="正在运行" /> : null}
        </div>
        <span className="app-row__meta">{meta}</span>
        <div className="bar app-row__bar" style={{ '--fill': maxSeconds ? seconds / maxSeconds : 0 } as React.CSSProperties}>
          <i />
        </div>
      </div>
      <div className="app-row__stats">
        <span className="app-row__duration">
          {app.seconds_formatted || app.total_seconds_formatted || formatDuration(seconds)}
        </span>
        <span className="app-row__percent">
          {app.percent === undefined || app.percent === null ? '' : `${app.percent.toFixed(1)}%`}
        </span>
        <span className="app-row__presses">{formatCount(pressCount)} 次</span>
        <div className="bar bar--kpm" style={{ '--fill': maxKpm ? kpm / maxKpm : 0 } as React.CSSProperties}>
          <i />
        </div>
        <span className="text-xs muted numeric">{kpm ? `${kpm.toFixed(0)} KPM` : ''}</span>
      </div>
    </div>
  );
}

/**
 * 图标：`icon_url` 由后端给，204 表示"没有图标"（不是 404，应用是存在的）。
 * 取不到就显示首字母色块——这条路径在 icons 能力缺失的机器上是常态。
 */
function AppIcon({ iconUrl, label }: { iconUrl: string | null | undefined; label: string }) {
  const [broken, setBroken] = useState(false);
  const url = iconUrl ? assetUrl(iconUrl) : '';
  if (!url || broken) return <span className="app-row__initial">{initialOf(label)}</span>;
  return (
    <img
      className="app-row__icon"
      src={url}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setBroken(true)}
    />
  );
}
