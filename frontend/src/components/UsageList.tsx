// 只读的紧凑使用列表（17 文档 §4.2，TimeLens 的 `.usage-list`）。
//
// 与 `AppRow` 的分工：这里是**看**（30px 图标、54px 行高、行内一条 4px 占比条），
// 应用视图那边是**管**（可展开、可改名/合并/排除）。两者形状不同是因为职责不同——
// 总览的「所有使用」要在两列里放下整段时间的全部应用，应用视图要在一行里放下四个
// 管理入口。
//
// 占比条的填充色仍是**类别色**（`data-category` → bar.css 的 `--bar-color`）。前身用
// 一条与数据无关的灰渐变，而我们的类别色本来就在承载"这是哪一类"（17 文档 §5.0）。
import { useState } from 'react';
import { assetUrl } from '../core/api.ts';
import { initialOf } from '../domain/format.ts';
import type { AppUsageRow } from '../types/api.d.ts';

export interface UsageListProps {
  apps: readonly AppUsageRow[];
  /** 条长的基准。默认取本批最大值——列表里最长的那条铺满，其余按比例。 */
  maxSeconds?: number;
  /** 两列通栏（TimeLens 的「所有使用」）。 */
  split?: boolean;
  /** 空态由调用方给：不同位置的空态说法不同。 */
  empty?: React.ReactNode;
}

export function UsageList({
  apps,
  maxSeconds,
  split = false,
  empty = null,
}: UsageListProps) {
  const classes = ['usage-list'];
  if (split) classes.push('usage-list--split');
  const top = maxSeconds ?? Math.max(1, ...apps.map((app) => app.seconds || 0));

  return (
    <div className={classes.join(' ')}>
      {apps.length ? apps.map((app) => <Row key={app.app_id} app={app} top={top} />) : empty}
    </div>
  );
}

function Row({ app, top }: { app: AppUsageRow; top: number }) {
  const name = app.user_alias || app.display_name || app.process_name;
  // 最小 3%：0 秒之外的应用都要留一道可见的条，否则"用了 4 秒"与"没用过"长得一样。
  const width = top > 0 ? Math.max(3, Math.round(((app.seconds || 0) / top) * 100)) : 0;

  return (
    <div className="usage-row" data-category={app.category || 'uncategorized'}>
      <Mark app={app} name={name} />
      <div className="usage-row__main">
        <div className="usage-row__title">
          <span className="usage-row__name" title={name}>
            {name}
          </span>
          <small className="usage-row__value">{app.seconds_formatted}</small>
        </div>
        <div
          className="usage-row__track"
          title={`${(app.percent || 0).toFixed(1)}%`}
          role="img"
          aria-label={`${name}：${app.seconds_formatted}，占 ${(app.percent || 0).toFixed(1)}%`}
        >
          <div className="usage-row__fill" style={{ width: `${width}%` }} />
        </div>
      </div>
      <span className="usage-row__tail">
        {app.is_running ? (
          <i className="usage-row__running" title="正在运行" aria-label="正在运行" />
        ) : null}
      </span>
    </div>
  );
}

/** 图标取不到就是首字母块——204 而不是 404 的那条路径（05 文档 §6）。 */
function Mark({ app, name }: { app: AppUsageRow; name: string }) {
  const [broken, setBroken] = useState(false);
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  if (!url || broken) return <span className="usage-row__initial">{initialOf(name)}</span>;
  return (
    <img
      className="usage-row__icon"
      src={url}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setBroken(true)}
    />
  );
}
