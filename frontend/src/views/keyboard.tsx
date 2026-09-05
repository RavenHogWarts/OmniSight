// 键盘视图（06 文档 §7）= KeyTrace 键盘总览 ＋ TimeLens 按键面板（17 文档 §4.3）。
//
// 两个前身在这一屏是互补的：KeyTrace 给拟物机身与四张时间热力卡，TimeLens 给卡内图例
// 与每日日历。合起来正好是一屏：
//
//   按键跟踪                                    更新于 …   ← .section-heading + 范围选择器
//   ┌ 键盘热力图 · 颜色越深使用越多      少 ▢▢▢▢ 多 ┐
//   │ 拟物机身：42px 键帽 / 7px 间隙 / 键名 12px    │
//   │ 按键次数 · 活跃键位 · 平均时长 · 最长按压     │  ← 四格摘要（Quad）
//   时间热力图
//   ┌ 每日活跃度 2fr ┐ ┌ 最近 24 小时 1fr ┐
//   ┌ 按月 通栏 ┐ ┌ 按年 通栏 ┐
//   高频键位 Top 10 ｜ 手指负荷                    ← 我们独有，留在最后
//
// 与旧 KeyTrace 的关键差异（这些是"合并"的收益，不因为搬布局而放弃）：
//   1. 键盘 DOM 由 `/keyboard/layout` 下发的数据生成，前端零坐标（旧版是 860 行硬编码）。
//   2. 范围切换（全部应用 / 某个应用）就在段标题右侧，它是同一张热力图的两种范围，
//      不是两个功能——旧版把它塞在页面最下方一个独立面板里，还需要另外连上 TimeLens。
//   3. 时间分布四个粒度**一次请求取回**（`view=hours,days,months,years`），因此四张卡
//      同屏铺开不多一次往返——旧版首屏为此发 4 个请求，而我们原先只画当前选中的那一个。
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { CalendarHeatmap } from '../charts/CalendarHeatmap.tsx';
import { Chart } from '../charts/Chart.tsx';
import { scaleBarsDescribe, scaleBarsDraw } from '../charts/scale-bars.ts';
import type { ScaleBarsData } from '../charts/scale-bars.ts';
import { AppPicker } from '../components/AppPicker.tsx';
import { Card, Section } from '../components/Card.tsx';
import { hideChartTooltip, showChartTooltip } from '../components/chart-hover.ts';
import { HeatStrip } from '../components/HeatStrip.tsx';
import { Icon } from '../components/Icon.tsx';
import { HeatLegend, KeyboardView } from '../components/KeyboardView.tsx';
import { METRIC_SLOT_ID, Updated } from '../components/PeriodNav.tsx';
import { Quad } from '../components/Quad.tsx';
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
import { METRICS, TIMELINE_VIEWS, formatMetric, metricOf } from '../domain/metrics.ts';
import { gapSet, periodParams } from '../domain/period.ts';
import type { State } from '../core/store.ts';
import type { DataRequest, HeatmapKey, HeatmapResponse } from '../types/api.d.ts';

export const title = '键盘';

const TOP_KEYS = 10;
/** 时间尺度。四个粒度**一次请求取回**（见 needs），因此切换尺度不发请求。 */
type Grain = 'hours' | 'days' | 'months' | 'years';
const GRAIN_NAMES: Record<Grain, string> = {
  hours: '小时',
  days: '天',
  months: '月',
  years: '年',
};
/** markGaps 用的桶粒度命名（它按 hour/day/month/year 判断缺口映射）。 */
const GAP_GRAIN: Record<Grain, string> = {
  hours: 'hour',
  days: 'day',
  months: 'month',
  years: 'year',
};
const DENSITIES = [
  { id: 'standard', name: '标准' },
  { id: 'compact', name: '紧凑' },
];

/**
 * 时间分布的两种形式（18 文档 批 7）。**同一份数据两种读法**：柱状回答"多与少"（要比较
 * 具体数值时它更准），热力格回答"什么时候在打字"（一眼扫完形状）。
 *
 * 默认按尺度选：**日默认热力**（那是年历，365 根柱看不出星期与月份的位置——14 文档 §2.11），
 * 其余默认柱状。用户显式选过之后就按他选的来，切尺度也不再改回去。
 */
type Form = 'bars' | 'heat';
const FORMS = [
  { id: 'bars', name: '柱状' },
  { id: 'heat', name: '热力' },
];

function defaultForm(grain: Grain): Form {
  return grain === 'days' ? 'heat' : 'bars';
}

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

function Bar({ ratio }: { ratio: number }) {
  return (
    <div className="bar" style={{ '--fill': Math.max(0, Math.min(1, ratio || 0)) } as React.CSSProperties}>
      <i />
    </div>
  );
}

export function View() {
  const metric = useSlice('metric');
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const selectedKeyId = useSlice('selectedKeyId');
  const layout = useResource('layout');
  const heatmap = useResource('heatmap');
  const appsMeta = useResource('appsMeta');
  const appsRunning = useResource('appsRunning');
  // 密度是真实的取舍：标准优先保证键面数值 ≥11px，紧凑优先让整块键盘不横向滚动
  // （14 文档 §4.4）。交给用户比替他猜好。它只改渲染，所以留在卡头。
  const [density, setDensity] = useState<'standard' | 'compact'>('standard');
  // 时间尺度**只改这一张图怎么画**，不改取哪一批数（四个粒度是同一次请求取回的），
  // 因此它是视图内部状态、留在卡头，不进 store 也不进 URL（14 文档 §4.1 的分界）。
  const [grain, setGrain] = useState<Grain>('days');
  // 形式：null = 跟着尺度的默认值（见 defaultForm）。选过一次之后就一直按用户选的来。
  const [form, setForm] = useState<Form | null>(null);
  const shownForm = form ?? defaultForm(grain);

  const metricSlot = document.getElementById(METRIC_SLOT_ID);
  const error = heatmap.error || layout.error;
  const keyboardOk = capabilityOf(capabilities, 'keyboard');
  const notice = noticeFor(degraded, 'keyboard');

  return (
    <>
      <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
        键盘
      </h1>

      {/* 指标带（17 文档 §4.1）：它是漏斗的第四层，居中 300px 常驻，与前身一致。
          原先它挤在周期栏右段的筛选行里，读起来像"某张卡的开关"。 */}
      {metricSlot
        ? createPortal(
            <Segmented
              items={METRICS}
              active={metric}
              onPick={(id) => setState('metric', id)}
              variant="switch"
              label="统计指标"
            />,
            metricSlot,
          )
        : null}

      <Section
        title="按键跟踪"
        sub="只统计键位次数，不保存输入内容"
        lead
        right={
          <div className="keyboard-view__scope">
            <AppPicker
              apps={appsMeta.data?.apps}
              runningIds={(appsRunning.data?.apps || [])
                .map((app) => app.app_id)
                .filter((id): id is number => typeof id === 'number')}
            />
            <Updated />
          </div>
        }
      >
        <Card
          title="键盘热力图"
          subtitle="颜色越深，使用次数越多"
          controls={
            keyboardOk ? (
              <>
                <HeatLegend metric={metric} scale={heatmap.data?.scale} />
                <Segmented
                  items={DENSITIES}
                  active={density}
                  onPick={(id) => setDensity(id as 'standard' | 'compact')}
                  small
                  label="键盘密度"
                />
              </>
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
          ) : error ? (
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
        </Card>
      </Section>

      {selectedKeyId ? <KeyDetail keyId={selectedKeyId} /> : null}

      {/* 时间分布。**尺度是一个筛选**，不是四张卡同屏：四个粒度里一次只看一个，而每一个
          都值得占满整张卡的宽度——12 个月挤在 12 个 72px 的格子里、3 个年份铺成三块砖，
          都比一根轴上的一组柱难读。数据仍然是一次请求取回的，所以切尺度不发请求。

          形式按维度选（14 文档 §2.11）：**日是二维的**（7 行 × 53 列 + 月份轴），一维序列
          用柱。这也把 D4 那条"一维也用格子"的妥协收回来了——它当初的理由是"四卡同屏才像
          KeyTrace"，而四卡同屏已经不在了。 */}
      <Section
        title="时间分布"
        sub={`按${GRAIN_NAMES[grain]}聚合 · ${metricName(metric)}`}
        right={
          <div className="keyboard-view__scope">
            <Segmented
              items={TIMELINE_VIEWS}
              active={grain}
              onPick={(id) => setGrain(id as Grain)}
              small
              label="时间尺度"
            />
            <Segmented
              items={FORMS}
              active={shownForm}
              onPick={(id) => setForm(id as Form)}
              small
              label="展示形式"
            />
          </div>
        }
      >
        <div className="card">
          {shownForm === 'heat' ? (
            grain === 'days' ? (
              <Calendar />
            ) : (
              <HeatScale grain={grain} />
            )
          ) : (
            <ScaleBars grain={grain} />
          )}
        </div>
      </Section>

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
    </>
  );
}

function metricName(metric: string): string {
  return METRICS.find((item) => item.id === metric)?.name || '';
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

/** 四格总计。几何来自 KeyTrace 应用屏的四格摘要，不是原先那一行裸文字（17 文档 §4.3）。 */
function Totals({ heatmap }: { heatmap: HeatmapResponse }) {
  const totals = heatmap.totals;
  const scope = heatmap.scope;
  return (
    <div className="keyboard-totals">
      <Quad
        items={[
          { label: '按键次数', value: formatCount(totals?.press_count || 0) },
          { label: '活跃键位', value: `${totals?.active_keys || 0} 个` },
          { label: '平均时长', value: formatMetric('duration_avg_ms', totals?.duration_avg_ms || 0) },
          { label: '最长按压', value: formatMetric('duration_max_ms', totals?.duration_max_ms || 0) },
        ]}
      />
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
 * 小时 / 月 / 年的热力格形式。与 :func:`ScaleBars` 读的是同一个 `timeline` 资源、同一个
 * 指标、同一套缺口标记——**只有画法不同**，因此两种形式之间切换不会出现"两张图对不上"。
 *
 * 日尺度不走这里：那一档的热力形式就是年历（`Calendar`），它是二维的。
 */
function HeatScale({ grain }: { grain: Grain }) {
  const metric = useSlice('metric');
  const coverage = useSlice('coverage');
  const { data: payload, loading } = useResource('timeline');
  if (!payload) return loading ? <SkeletonRows count={1} /> : null;
  const view = payload.views?.[grain];
  if (!view || view.available === false) return <TimelineUnavailable payload={payload} />;

  const gaps = gapSet(coverage, ['keyboard']);
  const definition = metricOf(metric);
  const marked = markGaps(view.buckets, GAP_GRAIN[grain], gaps, view.period);
  return (
    <div>
      <HeatStrip
        buckets={marked.map((bucket) => ({
          bucket: bucket.bucket,
          label: bucket.label,
          value: Number((bucket as unknown as Record<string, unknown>)[metric]) || 0,
          gap: bucket.gap,
        }))}
        scale={view.scale}
        valueLabel={definition.name}
        format={(value) => formatMetric(metric, value)}
        label={`按${GRAIN_NAMES[grain]}的${definition.name}`}
      />
      <GapLegend count={gaps.size} />
    </div>
  );
}

/** 「该视图在当前设置下不可用」。两种形式共用一份措辞：说两遍就会有一天只改了一遍。 */
function TimelineUnavailable({ payload }: { payload: { warnings?: readonly { message?: string }[] } }) {
  return (
    <CapabilityNotice
      title="该视图在当前设置下不可用"
      detail={payload.warnings?.[0]?.message || '按小时的分布需要保留原始按键事件。'}
      hint='设置中开启"保存原始按键事件"后，此后的数据可用'
    />
  );
}

/**
 * 小时 / 月 / 年：一根轴上的一组柱。三个尺度共用这一个组件——它们都是一维序列，
 * 差别只在桶数（24 / 12 / 若干）与标签。
 *
 * `available: false` 是"该视图在当前设置下拿不到"，不是"值为 0"。原始事件被关掉时
 * 按小时的分布就属于这一类（services/keyboard.py 的 _hours_view）。
 */
function ScaleBars({ grain }: { grain: Grain }) {
  const metric = useSlice('metric');
  const coverage = useSlice('coverage');
  const { data: payload, loading } = useResource('timeline');
  if (!payload) return loading ? <SkeletonRows count={1} /> : null;

  const view = payload.views?.[grain];
  if (!view || view.available === false) return <TimelineUnavailable payload={payload} />;

  const gaps = gapSet(coverage, ['keyboard']);
  const definition = metricOf(metric);
  const format = (value: number) => formatMetric(metric, value);
  const marked = markGaps(view.buckets, GAP_GRAIN[grain], gaps, view.period);
  const data: ScaleBarsData = {
    buckets: marked.map((bucket) => ({
      bucket: bucket.bucket,
      label: bucket.label,
      value: Number((bucket as unknown as Record<string, unknown>)[metric]) || 0,
      gap: bucket.gap,
    })),
    valueLabel: definition.name,
    caption: `按${GRAIN_NAMES[grain]}的${definition.name}`,
    summary: `按${GRAIN_NAMES[grain]}的${definition.name}，共 ${view.buckets.length} 个桶`,
  };

  return (
    <div>
      <div className="chart chart--scale">
        <Chart<ScaleBarsData>
          data={data}
          draw={scaleBarsDraw({ format, accent: 'keys' })}
          describe={scaleBarsDescribe({ format })}
          height={190}
          label={data.summary}
          onHover={showChartTooltip}
          onLeave={hideChartTooltip}
        />
      </div>
      <GapLegend count={gaps.size} />
    </div>
  );
}

/**
 * 「日」这一档。365 天是**二维**的（7 行 × 53 列），因此它是日历而不是柱：一年 365 根
 * 柱各占 2px，看不出星期与月份的位置，而"周末在不在打字"恰是这个尺度上最该看出的事
 * （14 文档 §2.11 / §5.2）。月份轴与星期轴也是我们比两个前身都强的地方。
 */
function Calendar() {
  const coverage = useSlice('coverage');
  const prefs = useSlice('prefs');
  const metric = useSlice('metric');
  const { data: payload, loading } = useResource('timeline');
  const view = payload?.views?.days;
  if (!view) return loading ? <SkeletonRows count={1} /> : null;
  if (view.available === false) return null;
  const gaps = gapSet(coverage, ['keyboard']);
  return (
    <div>
      <CalendarHeatmap
        buckets={view.buckets}
        scale={view.scale}
        gaps={gaps}
        weekStartsOn={prefs.weekStartsOn}
        metric={metric}
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
