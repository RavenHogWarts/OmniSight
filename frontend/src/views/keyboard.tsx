// 键盘视图（06 文档 §7）。
//
// 与旧 KeyTrace 的三处关键差异：
//   1. 键盘 DOM 由 `/keyboard/layout` 下发的数据生成，前端零坐标（旧版是 860 行硬编码）。
//   2. 范围切换（全部应用 / 某个应用）就在顶部，它是同一张热力图的两种范围，不是两个
//      功能——旧版把它塞在页面最下方一个独立面板里，还需要另外连上 TimeLens。
//   3. 时间分布四个粒度**一次请求取回**（`view=hours,days,months,years`），旧版首屏
//      为此发 4 个请求。
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { CalendarHeatmap } from '../charts/CalendarHeatmap.tsx';
import { Chart } from '../charts/Chart.tsx';
import { hideChartTooltip, showChartTooltip } from '../components/chart-hover.ts';
import { describePanelPair, drawPanelPair } from '../charts/panel-pair.ts';
import type { PanelPairData } from '../charts/panel-pair.ts';
import { AppPicker } from '../components/AppPicker.tsx';
import { Card } from '../components/Card.tsx';
import { Icon } from '../components/Icon.tsx';
import { KeyboardView } from '../components/KeyboardView.tsx';
import { FILTERS_SLOT_ID } from '../components/PeriodNav.tsx';
import { Segmented } from '../components/controls.tsx';
import { capabilityOf, noticeFor } from '../components/degraded.tsx';
import {
  CapabilityNotice,
  EmptyState,
  ErrorState,
  GapLegend,
  SkeletonRows,
} from '../components/states.tsx';
import { fetchInto } from '../core/loader.ts';
import { getState, setState } from '../core/store.ts';
import { useResource, useSlice } from '../core/useStore.ts';
import { markGaps } from '../domain/buckets.ts';
import { formatCount, formatPercent } from '../domain/format.ts';
import { METRICS, TIMELINE_VIEWS, formatMetric } from '../domain/metrics.ts';
import { caliberNotes, gapSet, periodParams } from '../domain/period.ts';
import type { State } from '../core/store.ts';
import type { Coverage, DataRequest, HeatmapKey, HeatmapResponse } from '../types/api.d.ts';

export const title = '键盘';

const TOP_KEYS = 10;
const DENSITIES = [
  { id: 'standard', name: '标准' },
  { id: 'compact', name: '紧凑' },
];
const GRAIN_NAMES: Record<string, string> = { hours: '小时', days: '天', months: '月', years: '年' };

/** 布局族：auto 时不传 family，让后端按平台默认值决定（05 文档 §7）。 */
function familyParam(state: State): Record<string, string> {
  const requested = state.prefs.keyboardLayout;
  return requested && requested !== 'auto' ? { family: requested } : {};
}

export function needs(state: State): DataRequest[] {
  const period = periodParams(state.period);
  const scope = state.scopeAppId ? { app_id: state.scopeAppId } : {};
  const requests: DataRequest[] = [
    { key: 'layout', path: '/keyboard/layout', params: familyParam(state) },
    { key: 'heatmap', path: '/keyboard/heatmap', params: { ...period, metric: state.metric, ...scope } },
    {
      key: 'timeline',
      path: '/keyboard/timeline',
      // 四个粒度一次取回：KeyTrace 首屏为此发 4 个请求（05 文档 §4）。
      params: { ...period, view: 'hours,days,months,years', metric: state.metric, ...scope },
    },
    { key: 'ergonomics', path: '/keyboard/ergonomics', params: { ...period, ...scope } },
    { key: 'appsMeta', path: '/apps', params: { limit: 300 } },
    // "正在运行"分组的数据源（← 前身 KeyTrace 要靠 TimeLens 的集成接口才拿得到）。
    { key: 'appsRunning', path: '/apps/running' },
  ];
  if (state.selectedKeyId) {
    // 与 loadKeyDetail 同一个口径：详情必须跟着热图的范围走。
    requests.push({
      key: 'keyDetail',
      path: `/keyboard/keys/${state.selectedKeyId}`,
      params: { ...period, ...scope },
    });
  }
  return requests;
}

function reload(): void {
  const state = getState();
  for (const request of needs(state)) fetchInto(request.key, request.path, request.params);
}

function grainOf(view: string): string {
  return view === 'hours' ? 'hour' : view === 'days' ? 'day' : view === 'months' ? 'month' : 'year';
}

function Bar({ ratio }: { ratio: number }) {
  return (
    <div className="bar" style={{ '--fill': Math.max(0, Math.min(1, ratio || 0)) } as React.CSSProperties}>
      <i />
    </div>
  );
}

/** 口径变化（左右修饰键合并）不是缺数据，用注记而不是斜纹表达。 */
function CaliberNotice({ coverage }: { coverage: Coverage | null }) {
  const notes = caliberNotes(coverage);
  if (!notes.length) return null;
  const note = notes[0];
  return (
    <div className="card__hint">
      {note.from} 至 {note.to} 的数据口径不同：{note.message}
    </div>
  );
}

export function View() {
  const metric = useSlice('metric');
  const timelineView = useSlice('timelineView');
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const coverage = useSlice('coverage');
  const selectedKeyId = useSlice('selectedKeyId');
  const layout = useResource('layout');
  const heatmap = useResource('heatmap');
  const appsMeta = useResource('appsMeta');
  const appsRunning = useResource('appsRunning');
  // 密度是真实的取舍：标准优先保证键面数值 ≥11px，紧凑优先让整块键盘不横向滚动
  // （14 文档 §4.4）。交给用户比替他猜好。它只改渲染，所以留在卡头。
  const [density, setDensity] = useState<'standard' | 'compact'>('standard');

  const slot = document.getElementById(FILTERS_SLOT_ID);
  const error = heatmap.error || layout.error;
  const keyboardOk = capabilityOf(capabilities, 'keyboard');
  const notice = noticeFor(degraded, 'keyboard');

  return (
    <>
      <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
        键盘
      </h1>

      {/* 视图级筛选：范围与指标改的是请求参数，作用域是整屏（14 文档 §4.1）。 */}
      {slot
        ? createPortal(
            <>
              <AppPicker
                apps={appsMeta.data?.apps}
                runningIds={(appsRunning.data?.apps || [])
                  .map((app) => app.app_id)
                  .filter((id): id is number => typeof id === 'number')}
              />
              <Segmented
                items={METRICS}
                active={metric}
                onPick={(id) => setState('metric', id)}
                small
                label="指标"
              />
            </>,
            slot,
          )
        : null}

      {/* 卡头上只剩密度开关：它改的是这张图怎么画，不改取哪一批数。范围与指标改的是
          请求参数、作用域是整屏，因此它们在筛选行里（14 文档 §2.8、§4.1）。 */}
      <Card
        title="键盘热力图"
        controls={
          keyboardOk ? (
            <Segmented
              items={DENSITIES}
              active={density}
              onPick={(id) => setDensity(id as 'standard' | 'compact')}
              small
              label="键盘密度"
            />
          ) : null
        }
        footer={keyboardOk && heatmap.data ? <Totals heatmap={heatmap.data} /> : null}
      >
        {/* 键盘采集不可用：整块面板换成说明块。这里绝不画一张全 0 的键盘——那会让用户
            以为自己没打字，而真相是这台机器测不到（06 文档 §4.2 规则 1）。 */}
        {!keyboardOk ? (
          <CapabilityNotice
            title={notice?.title || '当前环境无法采集键盘'}
            detail={notice?.detail || '应用时长统计不受影响。'}
            hint={notice?.hint || ''}
          />
        ) : (
          <div>
            <CaliberNotice coverage={coverage} />
            {error ? (
              <ErrorState message={error.message} onRetry={reload} />
            ) : !layout.data || !heatmap.data ? (
              <SkeletonRows count={1} />
            ) : (
              <KeyboardView
                layout={layout.data}
                heatmap={heatmap.data}
                metric={metric}
                density={density}
                onSelectKey={(keyId) => {
                  setState('selectedKeyId', keyId);
                  loadKeyDetail(keyId);
                }}
              />
            )}
          </div>
        )}
      </Card>

      {selectedKeyId ? <KeyDetail keyId={selectedKeyId} /> : null}

      <Card
        title="时间分布"
        controls={
          <Segmented
            items={TIMELINE_VIEWS}
            active={timelineView}
            onPick={(id) => setState('timelineView', id)}
            small
            label="时间粒度"
          />
        }
      >
        <Timeline grain={timelineView} height={150} label="按键时间分布" showNote />
      </Card>

      <div className="grid grid--2">
        <Card title={`高频键位 Top ${TOP_KEYS}`}>
          <div className="top-keys">
            <TopKeys heatmap={heatmap.data} metric={metric} />
          </div>
        </Card>
        <Card title="手指负荷">
          <Ergonomics />
        </Card>
      </div>

      <Card title="每日活跃度（近 365 天）">
        <Calendar />
      </Card>

      {/* 月与年常驻（16 文档 §A5）。四个粒度本来就是一次请求取回的（见 needs），
          所以多画两块不多一次往返；前身 KeyTrace 把 365 天 / 24 小时 / 月 / 年四张卡
          同屏铺开，而这里原先只有"当前选中的那一个粒度 + 常驻日历"。 */}
      <div className="grid grid--2">
        <Card title="按月">
          <Timeline grain="months" height={96} label="按月的按键分布" />
        </Card>
        <Card title="按年">
          <Timeline grain="years" height={96} label="按年的按键分布" />
        </Card>
      </div>
    </>
  );
}

/**
 * 单键详情的取数。带上 scope：范围切到某个应用时，热图是那个应用的，单键详情也必须
 * 是——现状这个请求不带 app_id，于是热图与详情来自两个不同的口径，界面上没有任何
 * 提示（14 文档 §2.8）。
 */
function loadKeyDetail(keyId: string): void {
  const state = getState();
  const scope = state.scopeAppId ? { app_id: state.scopeAppId } : {};
  fetchInto('keyDetail', `/keyboard/keys/${keyId}`, {
    ...periodParams(state.period),
    ...scope,
  });
}

function Totals({ heatmap }: { heatmap: HeatmapResponse }) {
  const totals = heatmap.totals;
  const scope = heatmap.scope;
  const items: readonly (readonly [string, string])[] = [
    ['按键次数', formatCount(totals?.press_count || 0)],
    ['活跃键位', `${totals?.active_keys || 0} 个`],
    ['平均时长', formatMetric('duration_avg_ms', totals?.duration_avg_ms || 0)],
    ['最长按压', formatMetric('duration_max_ms', totals?.duration_max_ms || 0)],
  ];
  return (
    <div className="keyboard-totals">
      {items.map(([label, value]) => (
        <div key={label}>
          <div className="keyboard-total__label">{label}</div>
          <div className="keyboard-total__value numeric">{value}</div>
        </div>
      ))}
      {scope?.type === 'app' ? (
        <div className="card__hint">范围：{scope.display_name || ''}</div>
      ) : null}
    </div>
  );
}

function TopKeys({
  heatmap,
  metric,
}: {
  heatmap: HeatmapResponse | undefined;
  metric: string;
}) {
  if (!heatmap) return <SkeletonRows count={3} />;
  const read = (key: HeatmapKey) => Number((key as unknown as Record<string, unknown>)[metric]) || 0;
  const keys = (heatmap.keys || [])
    .filter((key) => read(key) > 0)
    .sort((left, right) => read(right) - read(left))
    .slice(0, TOP_KEYS);
  if (!keys.length) {
    return <EmptyState title="这段时间没有按键记录" mark={<Icon name="keyboard" size={28} />} />;
  }
  const top = read(keys[0]) || 1;
  return (
    <>
      {keys.map((key, index) => (
        <div className="top-key" key={key.id}>
          <span className="rank">{index + 1}</span>
          <span className="top-key__label">{key.label}</span>
          <Bar ratio={read(key) / top} />
          <span className="top-key__count">{formatMetric(metric, read(key))}</span>
          <span className="top-key__percent">{formatPercent(key.percent)}</span>
        </div>
      ))}
    </>
  );
}

/**
 * 时间分布。四个粒度共用这一个组件：数据是同一次请求取回的四个视图之一。
 *
 * `available: false` 是"该视图在当前设置下拿不到"，不是"值为 0"。原始事件被关掉时
 * 按小时的应用维度分布就属于这一类（services/keyboard.py 的 _hours_view）。
 */
function Timeline({
  grain,
  height,
  label,
  showNote = false,
}: {
  grain: string;
  height: number;
  label: string;
  showNote?: boolean;
}) {
  const metric = useSlice('metric');
  const coverage = useSlice('coverage');
  const { data: payload, loading } = useResource('timeline');
  if (!payload) return loading ? <SkeletonRows count={1} /> : null;

  const view = payload.views?.[grain];
  if (!view || view.available === false) {
    if (!showNote) return null;
    return (
      <CapabilityNotice
        title="该视图在当前设置下不可用"
        detail={payload.warnings?.[0]?.message || '按小时的应用维度分布需要保留原始按键事件。'}
        hint='设置中开启"保存原始按键事件"后，此后的数据可用'
      />
    );
  }

  const gaps = gapSet(coverage, ['keyboard']);
  const buckets = markGaps(view.buckets || [], grainOf(grain), gaps, view.period);
  const data: PanelPairData = {
    // 指标可切，而 panel-pair 的下面板画的是 `presses`——把当前指标的值搬到那个字段上，
    // 图表因此不必知道"指标"这件事。
    buckets: buckets.map((bucket) => ({
      ...bucket,
      presses: Number((bucket as unknown as Record<string, unknown>)[metric]) || 0,
    })),
    mode: 'presses',
    caption: label,
    summary: `按${GRAIN_NAMES[grain] || '时间'}的按键分布，共 ${buckets.length} 个桶`,
  };
  return (
    <div>
      <div className={height > 120 ? 'chart chart--medium' : 'chart chart--short'}>
        <Chart<PanelPairData>
          data={data}
          draw={drawPanelPair}
          describe={describePanelPair}
          height={height}
          label={label}
          onHover={showChartTooltip}
          onLeave={hideChartTooltip}
        />
      </div>
      {showNote ? <GapLegend count={gaps.size} /> : null}
    </div>
  );
}

function Calendar() {
  const coverage = useSlice('coverage');
  const prefs = useSlice('prefs');
  const { data: payload } = useResource('timeline');
  const view = payload?.views?.days;
  if (!view || view.available === false) return null;
  const gaps = gapSet(coverage, ['keyboard']);
  return (
    <div>
      <CalendarHeatmap
        buckets={view.buckets}
        scale={view.scale}
        gaps={gaps}
        weekStartsOn={prefs.weekStartsOn}
        metric="press_count"
      />
      <GapLegend count={gaps.size} />
    </div>
  );
}

function Ergonomics() {
  const capabilities = useSlice('capabilities');
  const { data: payload, loading } = useResource('ergonomics');
  if (!payload) return loading ? <SkeletonRows count={3} /> : null;

  const hands = payload.hands;
  const left = Number(hands?.left) || 0;
  const right = Number(hands?.right) || 0;
  const both = left + right;
  const fingers = payload.fingers || [];
  const top = Math.max(1, ...fingers.map((finger) => Number(finger.press_count) || 0));
  const rows = payload.rows || [];
  const rowTop = Math.max(1, ...rows.map((row) => Number(row.press_count) || 0));

  return (
    <>
      <div className="hands">
        <span>左手 {formatPercent(both ? (left / both) * 100 : 0)}</span>
        <div
          className="hands__bar"
          style={{ '--left': both ? left / both : 0.5 } as React.CSSProperties}
        >
          <i />
          <i />
        </div>
        <span>右手 {formatPercent(both ? (right / both) * 100 : 0)}</span>
      </div>
      <div className="fingers">
        {fingers.map((finger) => (
          <div className="finger-row" key={finger.id || finger.name}>
            <span className="finger-row__name">{finger.name}</span>
            <Bar ratio={(Number(finger.press_count) || 0) / top} />
            <span className="finger-row__percent">{formatPercent(finger.percent)}</span>
          </div>
        ))}
      </div>
      {/* 行分布（M4 人体工学交付物）：哪一排承担了多少输入。与手指负荷同一份数据，
          只是换了切法——服务端已按 keymap 的静态行归属算好。 */}
      <div className="text-sm muted">行分布</div>
      <div className="fingers">
        {rows.map((row) => (
          <div className="finger-row" key={row.id || row.name}>
            <span className="finger-row__name">{row.name}</span>
            <Bar ratio={(Number(row.press_count) || 0) / rowTop} />
            <span className="finger-row__percent">{formatPercent(row.percent)}</span>
          </div>
        ))}
      </div>
      {/* 修饰键占比的口径必须写明：数的是修饰键**自身**被按下的次数，不是"按某个键时
          按住了修饰键"——后者需要和弦信息，而我们不记录按键顺序（08 文档 §2）。 */}
      {payload.modifier_ratio ? (
        <div className="card__hint">
          修饰键占比 {formatPercent(payload.modifier_ratio.percent)}，口径：修饰键自身被按下的次数
        </div>
      ) : null}
      {/* 左右修饰键无法区分时，手指负荷的左右分布会失真——如实说明。 */}
      {capabilityOf(capabilities, 'key_position_stable') ? null : (
        <div className="card__hint">当前后端无法区分左右修饰键，左右手分布仅供参考</div>
      )}
    </>
  );
}

function KeyDetail({ keyId }: { keyId: string }) {
  const { data: payload } = useResource('keyDetail');
  if (!payload || payload.key.id !== keyId) {
    return (
      <Card title="键位详情">
        <SkeletonRows count={2} />
      </Card>
    );
  }
  const key = payload.key;
  const totals = payload.totals;
  const byApp = payload.by_app || [];
  const scope = payload.scope;
  const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));

  return (
    <Card
      title={`键位详情：${key.label}`}
      controls={
        <button className="button" type="button" onClick={() => setState('selectedKeyId', null)}>
          关闭
        </button>
      }
    >
      <div className="stack">
        {/* 范围必须写在详情里：读者要能一眼确认这些数字和上面那张热图同源。 */}
        <div className="card__hint">
          {scope?.type === 'app' ? `范围：${scope.display_name || ''}` : '范围：全部应用'}
        </div>
        <dl className="kv-list">
          <dt>按下次数</dt>
          <dd>{formatCount(totals?.press_count || 0)}</dd>
          <dt>平均时长</dt>
          <dd>{formatMetric('duration_avg_ms', totals?.duration_avg_ms || 0)}</dd>
          <dt>手指</dt>
          <dd>{key.finger_name || '-'}</dd>
          <dt>所在行</dt>
          <dd>{key.row_name || '-'}</dd>
          <dt>在当前布局中</dt>
          <dd>{key.in_layout ? '是' : '否'}</dd>
        </dl>
        {byApp.length ? (
          <div className="key-app-split">
            <div className="text-sm muted">主要来自这些应用</div>
            {byApp.slice(0, 8).map((item) => (
              <div className="top-key" key={item.app_id}>
                <span className="rank" />
                <span className="truncate">{item.display_name}</span>
                <Bar ratio={(Number(item.press_count) || 0) / top} />
                <span className="top-key__count">{formatCount(item.press_count)}</span>
                <span className="top-key__percent">{formatPercent(item.percent)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="card__hint">这个键没有按应用拆分的数据</div>
        )}
      </div>
    </Card>
  );
}
