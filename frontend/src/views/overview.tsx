// 总览（06 文档 §5）。合并后最重要的界面：必须一眼看出时长与键盘的关系，
// 否则用户会觉得只是两个工具挤在一个窗口里。
//
// 取数：首屏只有 `/overview` 一个请求（05 文档 §2 的复合端点）。输入强度分布来自
// `/insights/app-keyboard`，作为**第二个独立请求**异步补齐——它有自己的骨架屏，
// 不阻塞首屏的指标卡与时间线（07 文档 §5.2）。
import { useState } from 'react';
import { Chart } from '../charts/Chart.tsx';
import { hideChartTooltip, showChartTooltip } from '../components/chart-hover.ts';
import { describePanelPair, drawPanelPair } from '../charts/panel-pair.ts';
import type { PanelPairData, PanelPairMode } from '../charts/panel-pair.ts';
import { AppRow } from '../components/AppRow.tsx';
import { Card } from '../components/Card.tsx';
import { Highlights } from '../components/Highlights.tsx';
import { StackBar } from '../components/StackBar.tsx';
import { StatCard } from '../components/StatCard.tsx';
import { Segmented } from '../components/controls.tsx';
import { capabilityOf, noticeFor } from '../components/degraded.tsx';
import {
  CapabilityNotice,
  EmptyState,
  ErrorState,
  GapLegend,
  SkeletonRows,
} from '../components/states.tsx';
import { getState, setState } from '../core/store.ts';
import { useResource, useSlice } from '../core/useStore.ts';
import { markGaps, stackByCategory } from '../domain/buckets.ts';
import { formatCount, formatDuration, formatPercent } from '../domain/format.ts';
import { gapSet, periodParams } from '../domain/period.ts';
import type { State } from '../core/store.ts';
import type { CategoryShare, DataRequest, OverviewResponse } from '../types/api.d.ts';

export const title = '总览';

export function needs(state: State): DataRequest[] {
  const period = periodParams(state.period);
  return [
    { key: 'overview', path: '/overview', params: period },
    { key: 'overviewIntensity', path: '/insights/app-keyboard', params: { ...period, limit: 8 } },
  ];
}

// 「双轴」被删掉了：两套刻度画在一张图里会编造相关性（14 文档 §2.1）。取而代之的
// 「强度」是把两个量放到一根轴上的合法做法——取派生量 KPM，一条线一套刻度。
const TIMELINE_MODES = [
  { id: 'both', name: '并排' },
  { id: 'seconds', name: '时长' },
  { id: 'presses', name: '按键' },
  { id: 'kpm', name: '强度' },
];

const GRAIN_NAMES: Record<string, string> = { hour: '小时', day: '天', month: '月', year: '年' };

/** 重取当前周期：把 period 原样写回去，触发 main 的取数订阅。 */
function reload(): void {
  setState('period', { ...getState().period });
}

export function View() {
  const [mode, setMode] = useState<PanelPairMode>('both');
  const { data: overview, loading, error } = useResource('overview');

  return (
    <>
      <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
        总览
      </h1>
      <Timeline overview={overview} mode={mode} onMode={setMode} />
      <div className="overview__pair">
        <Metrics overview={overview} loading={loading} />
      </div>
      <Card title="构成">
        <div className="overview__stacks">
          <div>
            <div className="overview__stack-label">时间去了哪些类别</div>
            <Categories overview={overview} />
          </div>
          <div>
            <div className="overview__stack-label">其中多少是在真的输入</div>
            <Intensity />
          </div>
        </div>
      </Card>
      <Card
        title="最常使用"
        controls={
          <button className="card__link" type="button" data-action="route:go" data-route="apps">
            查看全部
          </button>
        }
      >
        <div className="app-list">
          {error ? (
            <ErrorState message={error.message} onRetry={reload} />
          ) : (
            <TopApps overview={overview} loading={loading} />
          )}
        </div>
      </Card>
      <Card title="结论">
        {/* 每条结论可点开看计算口径（M4 判据 4），渲染实现与洞察视图共用一份。 */}
        <div className="highlights">
          <Highlights items={overview?.highlights} />
        </div>
      </Card>
    </>
  );
}

function Metrics({
  overview,
  loading,
}: {
  overview: OverviewResponse | undefined;
  loading: boolean;
}) {
  const time = overview?.screen_time;
  const keys = overview?.keyboard;
  // 两张卡共用一条对照序列（后端一次算好 seconds 与 presses），各取自己那一列：
  // 屏幕时间比时长、按键比次数，"这段时间算不算多"因此在两张卡上是同一把尺子。
  const context = overview?.context || null;
  const pending = !overview && loading;
  return (
    <>
      <StatCard
        label="屏幕时间"
        hint="前台应用的累计时长，已扣除空闲"
        hero
        series="time"
        metric="seconds"
        format={formatDuration}
        loading={pending}
        text={time?.total_formatted || formatDuration(time?.total_seconds || 0)}
        delta={time?.delta_vs_previous}
        context={context}
        footnote={`${time?.app_count || 0} 个应用，日均 ${formatDuration(time?.daily_average_seconds || 0)}`}
        onHover={showChartTooltip}
        onLeave={hideChartTooltip}
      />
      <StatCard
        label="按键"
        hint="按键次数。不记录按了什么内容"
        series="keys"
        metric="presses"
        format={(value) => `${formatCount(value)} 次`}
        loading={pending}
        text={`${formatCount(keys?.total_presses || 0)} 次`}
        delta={keys?.delta_vs_previous}
        context={context}
        footnote={`${keys?.active_keys || 0} 个活跃键，峰值 ${formatCount(keys?.kpm_peak || 0)} KPM`}
        onHover={showChartTooltip}
        onLeave={hideChartTooltip}
      />
    </>
  );
}

function Timeline({
  overview,
  mode,
  onMode,
}: {
  overview: OverviewResponse | undefined;
  mode: PanelPairMode;
  onMode: (mode: PanelPairMode) => void;
}) {
  const coverage = useSlice('coverage');
  const trend = overview?.trend;
  const granularity = trend?.granularity || 'hour';
  // 上下两个面板共享时间轴，缺口取两者的并集：任何一侧测不到，这个桶就不可信。
  const gaps = gapSet(coverage, ['foreground', 'keyboard']);
  const buckets = markGaps(
    stackByCategory(trend?.buckets, overview?.categories),
    granularity,
    gaps,
    overview?.period,
  );
  const data: PanelPairData = {
    buckets,
    mode,
    caption: '活动带',
    summary: `${overview?.period?.label || ''}，共 ${buckets.length} 个时间桶`,
  };
  const grain = GRAIN_NAMES[granularity] || '时间';
  // 两个系列必须有图例，且常驻（14 文档 §4.3）。上面板按类别着色，因此时长那一侧
  // 的图例就是类别本身——一个蓝色"屏幕时间"色块会与柱子的实际颜色对不上。
  const categories = (overview?.categories || []).filter((item) => (item.seconds || 0) > 0);
  const showTime = mode === 'both' || mode === 'seconds';

  return (
    <Card
      title="活动带"
      controls={
        <Segmented
          items={TIMELINE_MODES}
          active={mode}
          onPick={(id) => onMode(id as PanelPairMode)}
          small
          label="活动带指标"
        />
      }
      footer={
        <div className="card__hint">
          {overview?.period?.days || 0} 天，按{grain}聚合
        </div>
      }
    >
      <div>
        <div className="chart chart--tall">
          <Chart<PanelPairData>
            data={overview ? data : null}
            draw={drawPanelPair}
            describe={describePanelPair}
            height={220}
            label="活动带"
            onHover={showChartTooltip}
            onLeave={hideChartTooltip}
          />
        </div>
        <div className="chart__legend">
          {showTime && categories.length
            ? categories.map((item) => (
                <span className="chart__legend-item" data-category={item.id} key={item.id}>
                  <i />
                  <span>{item.name}</span>
                </span>
              ))
            : null}
          {showTime && !categories.length ? (
            <span className="chart__legend-item" data-series="time">
              <i />
              <span>屏幕时间</span>
            </span>
          ) : null}
          {mode === 'both' || mode === 'presses' || mode === 'kpm' ? (
            <span className="chart__legend-item" data-series="keys">
              <i />
              <span>{mode === 'kpm' ? '输入强度 KPM' : '按键'}</span>
            </span>
          ) : null}
        </div>
        <div>
          <GapLegend count={gaps.size} />
        </div>
      </div>
    </Card>
  );
}

function CategoryRow({
  item,
  percent,
  kind = 'category',
}: {
  item: { id: string; name: string; seconds_formatted?: string };
  percent: number;
  kind?: 'category' | 'profile';
}) {
  return (
    <div
      className="category-row"
      data-category={kind === 'category' ? item.id : undefined}
      data-profile={kind === 'profile' ? item.id : undefined}
    >
      <span className="swatch" aria-hidden="true" />
      <span className="truncate">{item.name}</span>
      <span className="category-row__percent">{formatPercent(percent)}</span>
      <span className="category-row__value">{item.seconds_formatted}</span>
    </div>
  );
}

function Categories({ overview }: { overview: OverviewResponse | undefined }) {
  const categories: readonly CategoryShare[] = overview?.categories || [];
  return (
    <>
      {/* 槽位顺序 = 后端下发的顺序，不按大小排：相邻关系因此确定、可事先校验，
          且同一个类别在每个周期都在同一个位置（14 文档 §2.10）。 */}
      <StackBar
        label="类别构成"
        segments={categories.map((item) => ({
          id: item.id,
          name: item.name,
          percent: item.percent,
          formatted: item.seconds_formatted,
        }))}
      />
      <div className="category-list">
        {categories.map((item) => (
          <CategoryRow key={item.id} item={item} percent={item.percent} />
        ))}
        {categories.length ? null : (
          <EmptyState title="这段时间没有应用记录" detail="换一个日期，或确认采集正在运行" />
        )}
      </div>
    </>
  );
}

function TopApps({
  overview,
  loading,
}: {
  overview: OverviewResponse | undefined;
  loading: boolean;
}) {
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');

  if (!overview) return loading ? <SkeletonRows count={4} /> : null;

  // 归因不可用时，显示"0 个应用"是错的说法：面板正文换成能力说明块，
  // 且**不给重试按钮**——重试不会改变结果（06 文档 §4.2 第二级、§10.1）。
  if (!capabilityOf(capabilities, 'foreground')) {
    const notice = noticeFor(degraded, 'foreground');
    return (
      <CapabilityNotice
        title={notice?.title || '当前环境不支持识别前台应用'}
        detail={notice?.detail || '键盘统计不受影响，但无法按应用拆分时长。'}
        hint={notice?.hint || ''}
      />
    );
  }

  const apps = overview.top_apps || [];
  if (!apps.length) {
    return <EmptyState title="这段时间没有使用记录" detail="把范围切到全部即可查看历史数据" />;
  }
  const maxSeconds = Math.max(...apps.map((app) => app.seconds || 0));
  const maxKpm = Math.max(...apps.map((app) => app.kpm || 0));
  return (
    <>
      {apps.slice(0, 6).map((app) => (
        <AppRow key={app.app_id} app={app} maxSeconds={maxSeconds} maxKpm={maxKpm} />
      ))}
    </>
  );
}

function Intensity() {
  const { data: payload, loading } = useResource('overviewIntensity');
  if (!payload) return loading ? <SkeletonRows count={2} /> : null;
  const distribution = payload.distribution;
  const buckets = distribution?.buckets || [];
  const total = Number(distribution?.total_seconds) || 0;
  const share = (seconds: number | undefined) => (total ? ((seconds || 0) / total) * 100 : 0);

  return (
    <>
      {/* 与类别构成条上下对齐、共用同一条 100% 宽度基准：同一张卡回答"时间去了哪些
          类别"和"其中多少是在真的输入"（14 文档 §4.3）。 */}
      <StackBar
        label="输入强度构成"
        segments={buckets.map((item) => ({
          id: item.id,
          name: item.name,
          percent: share(item.seconds),
          formatted: item.seconds_formatted,
        }))}
      />
      <div className="category-list">
        {buckets.map((item) => (
          <CategoryRow key={item.id} item={item} percent={share(item.seconds)} kind="profile" />
        ))}
        {/* 总量守恒：没有归因的按键必须显示出来，否则各应用之和与指标卡对不上而用户
            无从发现原因（04 文档 §2.2 的 app_id = 0）。 */}
        {payload.unattributed_presses ? (
          <div className="card__hint">
            另有 {formatCount(payload.unattributed_presses)} 次按键没有应用归因
          </div>
        ) : null}
      </div>
    </>
  );
}
