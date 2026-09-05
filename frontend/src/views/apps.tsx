// 应用视图（06 文档 §6）。
//
// 取数（M4 起）：搜索走**服务端**——`/usage/period?q=` 在周期口径的折叠结果上过滤，
// 因此能跨过"一次取回 500 行"的上限，且搜索结果与列表是同一套数字（M3 已知限制 3
// 的修复）。无搜索词时仍一次取回整个周期的列表，排序/分页在前端做。
//
// 管理元数据（excluded / merged_into / category_source）来自 `/apps`，按 app_id 合并。
// 这是旧版完全没有的能力：分类规则原先硬编码在 web_app.py 与 app-categories.js 两处，
// 用户改不了。
import { Fragment, useEffect, useRef, useState } from 'react';
import { AppGrid, BigMark } from '../components/AppGrid.tsx';
import { AppRow } from '../components/AppRow.tsx';
import type { AppRowData } from '../components/AppRow.tsx';
import { Card, Section } from '../components/Card.tsx';
import { Updated } from '../components/PeriodNav.tsx';
import { Quad } from '../components/Quad.tsx';
import { Checkbox, Chip, SearchBox, Segmented, Switch } from '../components/controls.tsx';
import { capabilityOf, noticeFor } from '../components/degraded.tsx';
import { CapabilityNotice, EmptyState, ErrorState, SkeletonRows } from '../components/states.tsx';
import { fail, ok } from '../components/toast.tsx';
import { del, messageOf, patch, post } from '../core/api.ts';
import { fetchInto } from '../core/loader.ts';
import { prefersReducedMotion } from '../core/theme.ts';
import { getState, setState } from '../core/store.ts';
import { useResource, useSlice } from '../core/useStore.ts';
import { formatCount, formatPercent } from '../domain/format.ts';
import { periodParams } from '../domain/period.ts';
import type { State } from '../core/store.ts';
import type {
  AppDetailResponse,
  AppRecord,
  CategoryOption,
  DataRequest,
  SessionsResponse,
  UsagePeriodResponse,
} from '../types/api.d.ts';

export const title = '应用';

/** 每页 50 行（17 文档 §4.4）。前身没有分页；25 行在 1280px 宽的外壳里只占半屏。 */
const PAGE_SIZE = 50;
const SORTS = [
  { id: 'seconds', name: '时长' },
  { id: 'presses', name: '按键' },
  { id: 'sessions', name: '次数' },
  { id: 'name', name: '名称' },
  // "最近用过的排前面"（16 文档 §A4）。后端 `/usage/period?sort=last_seen` 是同一个
  // 语义，本地排序只是它的即时反馈。
  { id: 'last_seen', name: '最近' },
];
/** 搜索词变化到重取之间的间隔。本机请求毫秒级，防的是连打时的请求风暴。 */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * 影响**请求参数**的两个视图内状态。
 *
 * 它们放在模块作用域而不是组件里，因为 `needs(state)` 要读到它们——而 `needs` 是
 * 模块级导出（main.tsx 在组件之外调用它来编排取数）。类版本里这两个变量在
 * `create()` 的闭包里，`needs` 是实例方法，因此看得见；这里只是把同一个闭包抬到了
 * 模块上。**刻意不进 store**：它们是这一个视图的筛选态，不是全局状态（07 文档 §4.3）。
 */
const viewParams = { query: '', includeExcluded: false };

export function needs(state: State): DataRequest[] {
  const period = periodParams(state.period);
  const requests: DataRequest[] = [
    { key: 'appsPeriod', path: '/usage/period', params: { ...period, limit: 500, q: viewParams.query } },
    {
      key: 'appsMeta',
      path: '/apps',
      params: { limit: 500, include_excluded: viewParams.includeExcluded },
    },
    // 图标网格的「正在运行」分组（17 文档 §4.4）。前身 KeyTrace 要靠 TimeLens 的
    // 集成接口才拿得到这一份，我们自己就有。
    { key: 'appsRunning', path: '/apps/running' },
  ];
  if (state.selectedAppId) {
    requests.push({ key: 'appDetail', path: `/apps/${state.selectedAppId}` });
    requests.push({
      key: 'appSessions',
      path: '/usage/sessions',
      params: { ...period, app_id: state.selectedAppId, limit: 20 },
    });
  }
  return requests;
}

function num(value: unknown): number {
  return Number(value) || 0;
}

function nameOf(row: AppRowData): string {
  return row.user_alias || row.display_name || row.process_name || '';
}

/** 把周期列表与管理元数据合并成一份。派生结果不入 store（07 文档 §4.3）。 */
export function joinApps(
  periodPayload: UsagePeriodResponse | undefined,
  appsPayload: { apps?: readonly AppRecord[] } | undefined,
  options: { includeExcluded: boolean },
): AppRowData[] {
  const meta = new Map<number, AppRecord>();
  for (const app of appsPayload?.apps || []) meta.set(app.app_id, app);
  const rows: AppRowData[] = [];
  for (const app of periodPayload?.apps || []) {
    rows.push({ ...(meta.get(app.app_id) || {}), ...app } as AppRowData);
  }
  if (options.includeExcluded) {
    // 被排除的应用在周期列表里不存在（AppLens 已经把它们折走）。要让用户能取消排除，
    // 必须从 /apps 那一侧补进来，时长按 0 显示。
    const seen = new Set(rows.map((row) => row.app_id));
    for (const app of meta.values()) {
      if (app.excluded && !seen.has(app.app_id)) {
        rows.push({ ...app, seconds: 0, presses: 0, percent: 0 } as AppRowData);
      }
    }
  }
  return rows;
}

export function applyFilters(
  rows: readonly AppRowData[],
  options: { query: string; category: string; sort: string },
): AppRowData[] {
  const needle = options.query.toLowerCase();
  let items = [...rows];
  if (needle) {
    items = items.filter((row) => {
      const name = (row.user_alias || row.display_name || '').toLowerCase();
      const process = (row.process_name || '').toLowerCase();
      return name.includes(needle) || process.includes(needle);
    });
  }
  if (options.category) {
    items = items.filter((row) => (row.category || 'uncategorized') === options.category);
  }
  items.sort((left, right) => {
    switch (options.sort) {
      case 'presses':
        return num(right.presses) - num(left.presses);
      case 'sessions':
        return num((right as { session_count?: number }).session_count) - num((left as { session_count?: number }).session_count);
      case 'name':
        return nameOf(left).localeCompare(nameOf(right), 'zh-CN');
      // ISO 时间戳按字符串倒序即时间倒序；没有时间的排最后而不是排最前。
      case 'last_seen':
        return String((right as { last_seen_at?: string }).last_seen_at || '').localeCompare(
          String((left as { last_seen_at?: string }).last_seen_at || ''),
        );
      default:
        return num(right.seconds) - num(left.seconds);
    }
  });
  return items;
}

/** 重取整屏。写操作之后必调：写操作会让缓存整体失效并递增 data_version。 */
function reload(): void {
  const state = getState();
  const period = periodParams(state.period);
  fetchInto('appsPeriod', '/usage/period', { ...period, limit: 500, q: viewParams.query });
  fetchInto('appsMeta', '/apps', { limit: 500, include_excluded: viewParams.includeExcluded });
  if (state.selectedAppId) loadDetail(state.selectedAppId);
}

function loadDetail(appId: number): void {
  fetchInto('appDetail', `/apps/${appId}`);
  fetchInto('appSessions', '/usage/sessions', {
    ...periodParams(getState().period),
    app_id: appId,
    limit: 20,
  });
}

export function View() {
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const selectedAppId = useSlice('selectedAppId');
  const period = useResource('appsPeriod');
  const meta = useResource('appsMeta');
  const [query, setQuery] = useState(viewParams.query);
  const [includeExcluded, setIncludeExcluded] = useState(viewParams.includeExcluded);
  const [category, setCategory] = useState('');
  const [sort, setSort] = useState('seconds');
  const [page, setPage] = useState(0);
  const searchTimer = useRef(0);

  // 选中的应用变了就取它的详情。**放在这里而不是点击处**：URL 里带着 `?app=12`
  // 直接进来时也要取（router 会把它写进 store，点击不曾发生）。
  useEffect(() => {
    if (selectedAppId) loadDetail(selectedAppId);
  }, [selectedAppId]);

  // 服务端搜索（M4）：debounce 后带着 q 重取周期列表。本地过滤仍然保留，作为请求
  // 往返期间的即时反馈——两边口径一致（后端在同样的折叠结果上过滤），双重过滤是幂等的。
  useEffect(() => {
    viewParams.query = query;
    window.clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => {
      fetchInto('appsPeriod', '/usage/period', {
        ...periodParams(getState().period),
        limit: 500,
        q: query,
      });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(searchTimer.current);
  }, [query]);

  useEffect(() => {
    viewParams.includeExcluded = includeExcluded;
    fetchInto('appsMeta', '/apps', { limit: 500, include_excluded: includeExcluded });
  }, [includeExcluded]);

  const error = period.error || meta.error;
  const catalog: readonly CategoryOption[] = meta.data?.categories || [];
  const rows = applyFilters(joinApps(period.data, meta.data, { includeExcluded }), {
    query,
    category,
    sort,
  });
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const slice = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);
  const maxSeconds = Math.max(0, ...rows.map((row) => num(row.seconds)));
  const maxKpm = Math.max(0, ...rows.map((row) => num(row.kpm)));
  const foregroundOk = capabilityOf(capabilities, 'foreground');
  const notice = noticeFor(degraded, 'foreground');

  return (
    <>
      <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
        应用
      </h1>

      {/* 图标网格面板（17 文档 §4.4）= KeyTrace 应用分类屏的主体。选应用是**认图标**，
          所以它是一整块常驻网格，而不是一个下拉框；弹层那一份留给键盘视图。 */}
      <Section title="应用" right={<Updated />} lead>
        {/* 这一块**没有卡头**：卡里第一行就是 42px 的选中应用头，再加一行"选择应用"
            等于把同一件事说两遍（KeyTrace 这张卡也没有标题）。 */}
        <div className="card">
          <AppPanel rows={rows} periodPayload={period.data} />
        </div>
      </Section>

      <Section
        title="所有使用"
        right={
          <p className="updated">
            {foregroundOk && period.data
              ? `${rows.length} 个应用，合计 ${period.data.total_seconds_formatted || ''}`
              : ''}
          </p>
        }
      >
      <Card
        title="明细与管理"
        subtitle="改名、合并、排除、改类别都在这里"
        controls={
          <>
            {/* 搜索 / 排序 / 含已排除改的是这张列表取哪一批，作用域就是这张卡——原先
                它们 portal 到周期栏右段，那一行因此越挤越长（17 文档 §4.1）。 */}
            <SearchBox placeholder="搜索应用" value={query} onInput={setQuery} />
            <Segmented
              items={SORTS}
              active={sort}
              onPick={(id) => {
                setSort(id);
                setPage(0);
              }}
              small
              label="排序"
            />
            <Checkbox
              label="显示已排除"
              checked={includeExcluded}
              onChange={(value) => {
                setIncludeExcluded(value);
                setPage(0);
              }}
            />
          </>
        }
        footer={
          <div className="row row--wrap">
            <div className="row row--wrap">
              {[{ id: '', name: '全部' }, ...catalog].map((item) => (
                <Chip
                  key={item.id || 'all'}
                  item={item}
                  active={category === item.id}
                  onPick={(id) => {
                    setCategory(id);
                    setPage(0);
                  }}
                />
              ))}
            </div>
            <span className="spacer" />
            <span className="apps__count">
              {foregroundOk && period.data
                ? `${rows.length} 个应用，合计 ${period.data.total_seconds_formatted || ''}`
                : ''}
            </span>
          </div>
        }
      >
        <div>
          <div className="app-list">
            {!foregroundOk ? (
              <CapabilityNotice
                title={notice?.title || '当前环境不支持识别前台应用'}
                detail={
                  notice?.detail || '键盘统计不受影响。这个面板依赖前台窗口信息，因此无法显示。'
                }
                hint={notice?.hint || ''}
              />
            ) : error ? (
              <ErrorState message={error.message} onRetry={reload} />
            ) : !period.data ? (
              period.loading ? <SkeletonRows count={6} /> : null
            ) : !slice.length ? (
              <EmptyState
                title={query ? '没有匹配的应用' : '这段时间没有使用记录'}
                detail={query ? '换一个关键词试试' : '把范围切到全部即可查看历史数据'}
              />
            ) : (
              /* 详情**紧跟被点的那一行**展开（06 文档 §6：同页展开、不跳转）。
                 原先它渲染在整张列表之后——点第 3 行、详情出现在第 50 行下面，屏幕上
                 看不到任何变化，读起来像"点了没反应"。手风琴的语义本来就在
                 `AppRow` 的 `aria-expanded` 上，缺的只是 DOM 位置。 */
              slice.map((row) => (
                <Fragment key={row.app_id}>
                  <AppRow
                    app={row}
                    maxSeconds={maxSeconds}
                    maxKpm={maxKpm}
                    expanded={selectedAppId === row.app_id}
                    onToggle={(appId) =>
                      setState('selectedAppId', getState().selectedAppId === appId ? null : appId)
                    }
                  />
                  {selectedAppId === row.app_id ? (
                    <AppDetail
                      appId={row.app_id}
                      category={row.category}
                      catalog={catalog}
                      rows={rows}
                    />
                  ) : null}
                </Fragment>
              ))
            )}
          </div>
          {pages > 1 ? (
            <div className="pager">
              <button
                className="button"
                type="button"
                disabled={current === 0}
                onClick={() => setPage(current - 1)}
              >
                上一页
              </button>
              <span>
                {current + 1} / {pages}
              </span>
              <button
                className="button"
                type="button"
                disabled={current >= pages - 1}
                onClick={() => setPage(current + 1)}
              >
                下一页
              </button>
            </div>
          ) : null}
        </div>
      </Card>
      </Section>
    </>
  );
}

/**
 * 图标网格面板（KeyTrace 应用分类屏）。头部是选中应用的 42px 图标 + 名字 + 进程名，
 * 接着是四格摘要，然后是三分组 + 图标网格。
 *
 * 四格摘要显示的是**选中应用的**读数（KeyTrace 同口径）；没选时显示整个周期的合计，
 * 而不是四个横杠——那一格空着的时候这块面板看起来像坏了。
 */
function AppPanel({
  rows,
  periodPayload,
}: {
  rows: readonly AppRowData[];
  periodPayload: UsagePeriodResponse | undefined;
}) {
  const selectedAppId = useSlice('selectedAppId');
  const meta = useResource('appsMeta');
  const running = useResource('appsRunning');
  const detail = useResource('appDetail');
  const current = rows.find((row) => row.app_id === selectedAppId) || null;
  const profile =
    detail.data && detail.data.app.app_id === selectedAppId
      ? detail.data.keyboard?.profile_name || ''
      : '';

  const items = current
    ? [
        { label: '屏幕时长', value: current.seconds_formatted || '0秒' },
        { label: '按键次数', value: `${formatCount(current.presses)} 次` },
        { label: '输入强度', value: `${formatCount(current.kpm)} KPM` },
        { label: '画像', value: profile || '—' },
      ]
    : [
        { label: '应用数', value: `${rows.length} 个` },
        { label: '合计时长', value: periodPayload?.total_seconds_formatted || '0秒' },
        {
          label: '合计按键',
          value: `${formatCount(rows.reduce((sum, row) => sum + num(row.presses), 0))} 次`,
        },
        { label: '画像', value: '选一个应用查看' },
      ];

  return (
    <>
      <div className="app-grid__head">
        <BigMark app={current} />
        <div className="app-grid__copy">
          <div className="app-grid__name">
            {current ? nameOf(current) : '全部应用'}
          </div>
          <div className="app-grid__process">
            {current ? current.process_name || '' : '点一个图标只看它，再点一次回到全部'}
          </div>
        </div>
        <span className="spacer" />
        <span className="app-grid__scope">统计范围跟随上方周期</span>
      </div>
      <div className="app-grid__summary">
        <Quad items={items} />
      </div>
      <AppGrid
        apps={meta.data?.apps}
        runningIds={(running.data?.apps || [])
          .map((app) => app.app_id)
          .filter((id): id is number => typeof id === 'number')}
        selectedId={selectedAppId}
        onPick={(appId) =>
          setState('selectedAppId', getState().selectedAppId === appId ? null : appId)
        }
      />
    </>
  );
}

function AppDetail({
  appId,
  category,
  catalog,
  rows,
}: {
  appId: number;
  /** 只为左侧那道类别色轨（见 app-row.css）。色值由 CSS 按 data-category 取。 */
  category?: string;
  catalog: readonly CategoryOption[];
  rows: readonly AppRowData[];
}) {
  const detail = useResource('appDetail');
  const sessions = useResource('appSessions');
  const host = useRef<HTMLDivElement | null>(null);

  // 点列表最后几行时，展开的详情整块落在折叠线以下——那和"点了没反应"是同一种体验。
  // `block: 'nearest'` 只在真的看不见时才滚，已经在视口里的话一动不动。
  useEffect(() => {
    host.current?.scrollIntoView({
      block: 'nearest',
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    });
  }, [appId]);

  if (!detail.data || detail.data.app.app_id !== appId) {
    return (
      <div className="app-detail" ref={host} data-category={category || 'uncategorized'}>
        <SkeletonRows count={3} />
      </div>
    );
  }
  const app = detail.data.app;
  return (
    <div className="app-detail" ref={host} data-category={category || 'uncategorized'}>
      {app.exe_path ? <div className="app-detail__path">{app.exe_path}</div> : null}
      <Totals totals={detail.data.totals} />
      <KeyboardSummary keyboard={detail.data.keyboard} />
      <Sessions payload={sessions.data} />
      <Editor app={app} catalog={catalog} rows={rows} />
    </div>
  );
}

function Totals({ totals }: { totals: AppDetailResponse['totals'] | undefined }) {
  const labels: readonly (readonly [string, string])[] = [
    ['day', '今天'],
    ['week', '本周'],
    ['month', '本月'],
    ['total', '总计'],
  ];
  const read = (key: string) =>
    (totals as unknown as Record<string, { seconds_formatted?: string; presses?: number }>)?.[key];
  return (
    <dl className="app-detail__totals">
      {labels.map(([key, label]) => {
        const part = read(key);
        return (
          <div className="app-detail__total" key={key}>
            <dt>{label}</dt>
            <dd>{part?.seconds_formatted || '0秒'}</dd>
            <div className="text-xs dim numeric">{formatCount(part?.presses || 0)} 次按键</div>
          </div>
        );
      })}
    </dl>
  );
}

function KeyboardSummary({ keyboard }: { keyboard: AppDetailResponse['keyboard'] | undefined }) {
  if (!keyboard) return null;
  const keys = keyboard.top_keys || [];
  const modifiers = keyboard.modifier_breakdown || [];
  return (
    <div>
      <div className="text-sm muted">
        键盘概况：{(keyboard.kpm || 0).toFixed(1)} KPM（{keyboard.profile_name || ''}）
      </div>
      <div className="app-detail__keys">
        {keys.map((key) => (
          <span className="key-chip" key={key.id || key.label}>
            <b>{key.label}</b>
            <span>{formatCount(key.press_count)}</span>
          </span>
        ))}
      </div>
      {/* 快捷键偏好（M4）：修饰键自身的细分。口径写明——不是和弦次数。 */}
      {modifiers.length ? (
        <div className="card__hint">
          修饰键偏好：
          {modifiers
            .slice(0, 4)
            .map((item) => `${item.label} ${formatPercent(item.percent)}`)
            .join(' · ')}
          （口径：修饰键自身被按下的次数）
        </div>
      ) : null}
      <button
        className="button"
        type="button"
        // 下钻到键盘视图并预设 app_id 过滤——原来这需要开两个程序（06 文档 §6）。
        onClick={() => {
          setState('scopeAppId', getState().selectedAppId);
          setState('route', 'keyboard');
        }}
      >
        查看完整键盘热力图
      </button>
    </div>
  );
}

function Sessions({ payload }: { payload: SessionsResponse | undefined }) {
  const sessions = payload?.sessions || [];
  if (!sessions.length) return null;
  const clock = (value: string | null | undefined) => String(value || '').slice(11, 16);
  return (
    <div>
      <div className="text-sm muted">最近 {sessions.length} 次访问</div>
      <div className="session-list">
        {/* 一次访问一行，不是一个心跳切段一行——后者在重度使用下是每 10 秒一条
            （03 文档的访问与会话段之分）。`/usage/sessions` 默认就按访问返回。 */}
        {sessions.map((session, index) => {
          const start = clock(session.start);
          const end = clock(session.end);
          return (
            <div className="session-row" key={`${session.start}-${index}`}>
              <span>{start && end ? `${start}-${end}` : start || end}</span>
              {/* 窗口标题只在 titles_included 为真时才有内容，后端决定，前端不猜。 */}
              <span className="truncate">{session.window_title || ''}</span>
              <span className="numeric">{session.seconds_formatted}</span>
            </div>
          );
        })}
      </div>
      {payload?.titles_included ? null : (
        <div className="card__hint">窗口标题未记录（隐私设置默认关闭）</div>
      )}
    </div>
  );
}

/**
 * 管理操作。写操作会让缓存整体失效并递增 data_version，因此改完立刻能看到新名字。
 *
 * "合并到…"（M3 已知限制 4 的补齐）：候选来自当前周期的列表——被排除的应用不在
 * 列表里，但它们本来也不该作为合并目标。
 */
function Editor({
  app,
  catalog,
  rows,
}: {
  app: AppDetailResponse['app'];
  catalog: readonly CategoryOption[];
  rows: readonly AppRowData[];
}) {
  const [alias, setAlias] = useState(app.user_alias || '');
  const [category, setCategory] = useState(app.category || '');
  const [target, setTarget] = useState('');

  // 切到另一个应用时把编辑框重置成它的值：组件复用同一个实例（key 是 appId 之外的）。
  useEffect(() => {
    setAlias(app.user_alias || '');
    setCategory(app.category || '');
    setTarget('');
  }, [app.app_id, app.user_alias, app.category]);

  const write = async (body: Record<string, unknown>, message: string) => {
    try {
      await patch(`/apps/${app.app_id}`, body);
      ok(message);
      reload();
    } catch (error) {
      // field 由后端给（05 文档 §9），直接显示比"操作失败"有用得多。
      fail(messageOf(error));
    }
  };

  const mergeInto = async () => {
    const into = Number.parseInt(target, 10);
    if (!Number.isFinite(into) || into <= 0) {
      fail('先选择要合并到的应用');
      return;
    }
    try {
      await post(`/apps/${app.app_id}/merge`, { into_app_id: into });
      ok('已合并，两边的统计从此算作一个应用');
      reload();
    } catch (error) {
      fail(messageOf(error));
    }
  };

  const unmerge = async () => {
    try {
      await del(`/apps/${app.app_id}/merge`);
      ok('已取消合并');
      reload();
    } catch (error) {
      fail(messageOf(error));
    }
  };

  // 合并目标：排除自己与已并进来的成员。合并是**单向**的（本应用的统计归入目标），
  // 目标之后再并入第三个应用时链条由 AppLens.root() 解析。
  const members = new Set([app.app_id, ...(app.merged_members || [])]);
  const candidates = rows.filter(
    (row) => !members.has(row.app_id) && !(row as { merged_into?: number }).merged_into,
  );

  return (
    <div className="actions">
      <label className="row">
        <span className="text-sm muted">别名</span>
        <input
          className="control"
          type="text"
          value={alias}
          placeholder={app.display_name || ''}
          aria-label="自定义名称"
          maxLength={120}
          onChange={(event) => setAlias(event.target.value)}
        />
      </label>
      {/* **不是主按钮**：这一排里「保存别名」「保存分类」「合并」三件事同等重要，把其中
          一个染成主色只会把视线拉到一个并不特殊的地方。主色留给"这个对话框只有一个动作"
          那种场合（确认框、导入向导、首启说明）。 */}
      <button
        className="button"
        type="button"
        onClick={() => write({ user_alias: alias.trim() || null }, '已更新名称')}
      >
        保存别名
      </button>
      <label className="row">
        <span className="text-sm muted">分类</span>
        <select
          className="control"
          aria-label="分类"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
        >
          {catalog.map((item) => (
            <option value={item.id} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <button className="button" type="button" onClick={() => write({ category }, '已更新分类')}>
        保存分类
      </button>
      <label className="row">
        <span className="text-sm muted">排除</span>
        <Switch
          checked={Boolean(app.excluded)}
          label="排除此应用"
          onChange={(value) => write({ excluded: value }, value ? '已排除' : '已取消排除')}
        />
      </label>
      {app.merged_into ? (
        <button className="button" type="button" onClick={unmerge}>
          取消合并
        </button>
      ) : null}
      {app.merged_members?.length ? (
        <span className="text-xs dim">已合并 {app.merged_members.length} 个来源</span>
      ) : null}
      {!app.merged_into ? (
        <div className="app-merge">
          <span className="text-sm muted">合并到…</span>
          <select
            className="control"
            aria-label="合并到哪个应用"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
          >
            <option value="">选择目标应用…</option>
            {candidates.map((row) => (
              <option value={String(row.app_id)} key={row.app_id}>
                {nameOf(row)}
              </option>
            ))}
          </select>
          <button className="button" type="button" onClick={mergeInto}>
            合并
          </button>
          <span className="text-xs dim">
            两个进程的统计从此算作一个应用（如 Code.exe 与 Code - Insiders.exe）
          </span>
        </div>
      ) : null}
    </div>
  );
}
