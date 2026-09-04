// 洞察视图（06 文档 §8 + 12 文档 M4、14 文档 §2.9/§2.11/§4.5）。
// **合并才可能实现的分析**——这是"为什么要升级"的答案。
//
// 面板与数据来源：
//   输入强度排行  /insights/app-keyboard        —— 这一屏的头条；应用名可下钻到该应用的键盘热图
//   键位 x 应用   /keyboard/keys/{id}          —— 键位选择器按当前周期高频键动态生成（M3-6）
//   节奏对比      /insights/rhythm 的 hourly    —— 打字最密集时段 vs 屏幕最长时段（M4）
//   每小时去向    /usage/timeline               —— stacked-bar（分类堆叠，M3 遗留图表的消费者）
//   专注与作息    /insights/rhythm
//
// **"结论"与"时间去向"归总览**：两个视图各画一份同源数据，用户不知道该看哪一个
// （14 文档 §2.9）。总览回答"这段时间发生了什么"，洞察只做交叉分析。
import { createPortal } from 'react-dom';
import { Chart } from '../charts/Chart.tsx';
import { hideChartTooltip, showChartTooltip } from '../components/chart-hover.ts';
import { describePanelPair, drawPanelPair } from '../charts/panel-pair.ts';
import type { PanelPairData } from '../charts/panel-pair.ts';
import { describeStackedBar, drawStackedBar } from '../charts/stacked-bar.ts';
import type { StackedBarData } from '../charts/stacked-bar.ts';
import { Card } from '../components/Card.tsx';
import { HourBand } from '../components/HourBand.tsx';
import { FILTERS_SLOT_ID } from '../components/PeriodNav.tsx';
import { capabilityOf, noticeFor } from '../components/degraded.tsx';
import { CapabilityNotice, EmptyState, ErrorState, SkeletonRows } from '../components/states.tsx';
import { fetchInto } from '../core/loader.ts';
import { getState, setState } from '../core/store.ts';
import { useResource, useSlice } from '../core/useStore.ts';
import { formatClock, formatCount, formatDurationShort, formatPercent } from '../domain/format.ts';
import { gapSet, periodParams } from '../domain/period.ts';
import type { State } from '../core/store.ts';
import type {
  AppKeyboardResponse,
  DataRequest,
  KeyDetailResponse,
  RhythmResponse,
} from '../types/api.d.ts';

export const title = '洞察';

/** 键位选择器最多列几个高频键。太多就失去了"挑一个看看"的意义。 */
const KEY_CHOICES_LIMIT = 12;

/** 周期切换后，已选键位可能在本周期一次都没被按——仍然查询它，让空态自己说明。 */
function keyIdFor(state: State): string {
  if (state.selectedKeyId) return state.selectedKeyId;
  const heatmap = state.data.insightHeatmap;
  const top = (heatmap?.keys || [])
    .filter((key) => (Number(key.press_count) || 0) > 0)
    .sort((left, right) => (Number(right.press_count) || 0) - (Number(left.press_count) || 0))[0];
  return top ? top.id : 'space';
}

export function needs(state: State): DataRequest[] {
  const period = periodParams(state.period);
  // "结论"归总览独占，因此这里不再取 /overview（14 文档 §2.9）——少一个请求。
  return [
    { key: 'insightKeyboard', path: '/insights/app-keyboard', params: { ...period, limit: 20 } },
    { key: 'insightRhythm', path: '/insights/rhythm', params: period },
    // top=10：图标带一行装得下十来个，取 5 会让 `+N` 把大半个下午都吞掉。
    { key: 'insightTimeline', path: '/usage/timeline', params: { ...period, top: 10 } },
    // 高频键选择器的数据源（M3-6 给出的两个方案之一：让洞察视图也取一次 heatmap）。
    { key: 'insightHeatmap', path: '/keyboard/heatmap', params: period },
    { key: 'insightKey', path: `/keyboard/keys/${keyIdFor(state)}`, params: period },
  ];
}

function reload(): void {
  const state = getState();
  for (const request of needs(state)) fetchInto(request.key, request.path, request.params);
}

function Bar({ ratio, profile }: { ratio: number; profile?: string }) {
  return (
    <div
      className="bar"
      data-profile={profile}
      style={{ '--fill': Math.max(0, Math.min(1, ratio || 0)) } as React.CSSProperties}
    >
      <i />
    </div>
  );
}

/** 下钻：同一张键盘热力图换一个范围（06 文档 §7 的"范围切换"）。 */
function drillTo(appId: number): void {
  setState('scopeAppId', appId);
  setState('route', 'keyboard');
}

export function View() {
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const keyboard = useResource('insightKeyboard');
  const rhythm = useResource('insightRhythm');
  const error = keyboard.error || rhythm.error;
  const foregroundOk = capabilityOf(capabilities, 'foreground');
  const notice = noticeFor(degraded, 'foreground');

  // 洞察整体依赖应用归因：没有归因就只剩"某个键被按了多少次"，那不是洞察。
  if (!foregroundOk) {
    return (
      <>
        <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
          洞察
        </h1>
        <Card title="输入强度排行">
          <CapabilityNotice
            title={notice?.title || '当前环境不支持识别前台应用'}
            detail={notice?.detail || '交叉分析需要把按键归到应用上，键盘总量统计不受影响。'}
            hint={notice?.hint || ''}
          />
        </Card>
      </>
    );
  }

  return (
    <>
      <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
        洞察
      </h1>
      <Card
        title="输入强度排行"
        footer={<div className="card__hint">{rankNote(keyboard.data)}</div>}
      >
        <div>
          <AttributionNotice />
          <div className="data-table__scroll">
            {error ? (
              <ErrorState message={error.message} onRetry={reload} />
            ) : !keyboard.data ? (
              keyboard.loading ? <SkeletonRows count={5} /> : null
            ) : (
              <Ranking payload={keyboard.data} />
            )}
          </div>
        </div>
      </Card>

      <Card title="键位与应用">
        <KeySplit />
      </Card>

      <Card title="节奏对比">
        <RhythmContrast rhythm={rhythm.data} loading={rhythm.loading} />
      </Card>

      <Card title="每小时时间去向">
        <Hourly />
      </Card>

      <div className="grid grid--2">
        <Card title="专注度">
          <Focus rhythm={rhythm.data} loading={rhythm.loading} />
        </Card>
        <Card title="作息">
          <Rhythm rhythm={rhythm.data} loading={rhythm.loading} />
        </Card>
      </div>
    </>
  );
}

function rankNote(payload: AppKeyboardResponse | undefined): string {
  if (!payload) return '';
  const parts = [payload.kpm_basis ? `KPM 口径：${payload.kpm_basis}` : ''];
  if (payload.unattributed_presses) {
    parts.push(`另有 ${formatCount(payload.unattributed_presses)} 次按键没有应用归因`);
  }
  return parts.filter(Boolean).join('。');
}

/**
 * 无应用归因的时段必须明说，不能让用户把"测不到"当成"没按键"（M4 判据 3）。
 * 两种来源：coverage.gaps 里 missing=foreground 的段（能力缺失/迁移数据），
 * 以及响应里单列的 unattributed_presses（空闲、锁屏、被排除应用期间的按键）。
 */
function AttributionNotice() {
  const coverage = useSlice('coverage');
  const unattributed = (coverage?.gaps || []).filter((gap) => gap?.missing === 'foreground');
  if (!unattributed.length) return null;
  return (
    <>
      {unattributed.map((gap) => (
        <div className="card__hint" key={`${gap.from}-${gap.to}`}>
          {gap.from === gap.to ? gap.from : `${gap.from} 至 ${gap.to}`} 无应用归因：
          该时段的按键不计入任何应用（{gap.message || '该环境不支持应用归因'}），不是零
        </div>
      ))}
    </>
  );
}

function Ranking({ payload }: { payload: AppKeyboardResponse }) {
  const apps = payload.apps || [];
  if (!apps.length) {
    // 空列表有两种含义：真的没有使用，或按键都归不到应用上。后者要明说（判据 3）。
    const unattributed = Number(payload.unattributed_presses) || 0;
    return (
      <EmptyState
        title={unattributed ? '该时段的按键没有应用归因' : '这段时间没有可分析的应用'}
        detail={
          unattributed
            ? `${formatCount(unattributed)} 次按键发生在无法识别前台应用的时段，未计入任何应用`
            : ''
        }
        mark="·"
      />
    );
  }
  const maxKpm = Math.max(1, ...apps.map((app) => Number(app.kpm) || 0));
  return (
    // 真实 table 而不是 div 堆叠：屏幕阅读器需要行列关系（06 文档 §13）。
    <table className="data-table">
      <caption className="sr-only">各应用的输入强度</caption>
      <thead>
        <tr>
          <th>应用</th>
          <th className="numeric">前台时长</th>
          <th className="numeric">按键</th>
          <th className="numeric">KPM</th>
          <th className="numeric">修饰键</th>
          <th>画像</th>
        </tr>
      </thead>
      <tbody>
        {apps.map((app) => (
          <tr key={app.app_id}>
            <td className="wide">
              {/* 应用视图的详情里已有同款入口，这里让"输入强度排行"也能直达。 */}
              <button
                className="link rank__app"
                type="button"
                title={`在键盘中查看 ${app.display_name}`}
                onClick={() => drillTo(app.app_id)}
              >
                {app.display_name}
              </button>
              <div className="rank__keys text-xs dim">
                <TopKeysLine keys={app.top_keys} />
              </div>
            </td>
            <td className="numeric">{app.seconds_formatted}</td>
            <td className="numeric">{formatCount(app.presses)}</td>
            <td className="numeric">{(Number(app.kpm) || 0).toFixed(1)}</td>
            <td className="numeric">{formatPercent(app.modifier_percent)}</td>
            <td>
              <span className="profile-tag" data-profile={app.profile}>
                <span className="profile-tag__bar">
                  <Bar ratio={(Number(app.kpm) || 0) / maxKpm} profile={app.profile} />
                </span>
                <span>{app.profile_name}</span>
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 常用键一行小字：Space 980 · E 820 · 左Ctrl 610（M4 应用 × 键盘交付物）。 */
function TopKeysLine({ keys }: { keys: AppKeyboardResponse['apps'][number]['top_keys'] }) {
  const list = keys || [];
  if (!list.length) return <span>没有按键记录</span>;
  return (
    <span>
      {list.slice(0, 3).map((key, index) => (
        <span key={key.id || key.label}>
          {index ? <span> · </span> : null}
          <b>{key.label}</b>
          <span> {formatCount(key.press_count)}</span>
        </span>
      ))}
    </span>
  );
}

/** 每小时时间去向：按应用类别堆叠的 24 小时柱（stacked-bar 的第一个消费者，M3-5）。 */
function Hourly() {
  const coverage = useSlice('coverage');
  const { data: payload, loading } = useResource('insightTimeline');
  if (!payload) return loading ? <SkeletonRows count={3} /> : null;

  const hours = payload.hours || [];
  const gaps = gapSet(coverage, ['foreground']);
  const period = payload.period;
  const data: StackedBarData = {
    buckets: hours.map((hour) => ({
      bucket: String(hour.hour),
      label: `${hour.hour}:00`,
      seconds: hour.total_seconds,
      presses: hour.presses,
      categories: hour.categories || {},
      total: hour.total_seconds,
      parts: Object.entries(hour.categories || {}).map(([category, seconds]) => ({
        category,
        seconds,
        name: category,
      })),
    })),
    caption: '每小时时间去向',
    summary: '按应用类别分层的每小时前台时长，共 24 个小时',
  };

  return (
    <div>
      <div className="chart chart--medium">
        <Chart<StackedBarData>
          data={data}
          draw={drawStackedBar}
          describe={describeStackedBar}
          height={170}
          label="每小时时间去向"
          onHover={showChartTooltip}
          onLeave={hideChartTooltip}
        />
      </div>
      {gaps.size ? (
        <div className="card__hint">{gaps.size} 天无应用归因，这些天的时长未计入各小时</div>
      ) : null}
      {/* 堆叠柱答"哪一类"，图标带答"是哪一个"——同一张卡两层，不再是两个面板
          （16 文档 §A1；前身把后者藏在另一张卡的背面）。 */}
      <div className="text-sm muted">这些小时里用的是哪些应用</div>
      {/* 图标带的缺口只在"看的就是这一天、而这一天测不到"时才成立：多天聚合里某天
          缺失不该让 24 行全画斜纹，那种情况由上面那行注记说明。 */}
      <HourBand
        hours={hours}
        gap={(period?.days || 0) <= 1 && gaps.has(period?.start || '')}
      />
    </div>
  );
}

/**
 * 节奏对比（M4）：一天中打字最密集的时段 vs 屏幕时间最长的时段。
 * 上面一条 24 小时的 KPM 柱给"密度长什么样"，下面两行结论给出两个峰值的答案。
 */
function RhythmContrast({
  rhythm,
  loading,
}: {
  rhythm: RhythmResponse | undefined;
  loading: boolean;
}) {
  if (!rhythm) return loading ? <SkeletonRows count={2} /> : null;
  const hourly = rhythm.hourly || [];
  // panel-pair 的 kpm 模式自己按 presses/seconds 算，所以这里如实给两个原始量。
  const data: PanelPairData = {
    buckets: hourly.map((item) => ({
      bucket: String(item.hour).padStart(2, '0'),
      label: `${item.hour}:00`,
      seconds: item.seconds,
      presses: item.presses,
      categories: {},
    })),
    mode: 'kpm',
    caption: '每小时输入强度',
    summary: '一天 24 小时的输入强度（KPM）',
  };
  const peaks = rhythm.hour_peaks;
  const typing = peaks?.typing;
  const screen = peaks?.screen;

  return (
    <div>
      {/* 24 小时的 KPM 是一维时间序列，默认形式是柱不是格子——格子热图适合"网格上
          比大小"（日历的 7×53），不适合一维序列（14 文档 §2.11）。 */}
      <div className="chart chart--medium">
        <Chart<PanelPairData>
          data={data}
          draw={drawPanelPair}
          describe={describePanelPair}
          height={150}
          label="每小时输入强度"
          onHover={showChartTooltip}
          onLeave={hideChartTooltip}
        />
      </div>
      <div className="stack">
        <dl className="kv-list">
          <dt>打字最密集</dt>
          <dd>{typing ? `${typing.hour}:00（${(Number(typing.kpm) || 0).toFixed(1)} KPM）` : '—'}</dd>
          <dt>屏幕时间最长</dt>
          <dd>{screen ? `${screen.hour}:00（${formatDurationShort(screen.seconds)}）` : '—'}</dd>
          {typing && screen ? <dt>是否同一时段</dt> : null}
          {typing && screen ? (
            <dd>
              {peaks?.same_hour
                ? '是——这段时间真正用在了输入上'
                : '否——屏幕最长的那小时更多在阅读或观看'}
            </dd>
          ) : null}
        </dl>
        {typing || screen ? (
          <div className="card__hint">
            口径：{peaks?.typing_basis || rhythm.hourly_basis || ''}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Focus({ rhythm, loading }: { rhythm: RhythmResponse | undefined; loading: boolean }) {
  if (!rhythm) return loading ? <SkeletonRows count={2} /> : null;
  const blocks = rhythm.focus_blocks || [];
  return (
    <div className="stack">
      <dl className="kv-list">
        <dt>应用切换</dt>
        <dd>{formatCount(rhythm.switch_count)} 次</dd>
        <dt>每小时切换</dt>
        <dd>{(Number(rhythm.switches_per_hour) || 0).toFixed(1)}</dd>
        <dt>最长专注</dt>
        <dd>{(Number(rhythm.longest_focus_minutes) || 0).toFixed(0)} 分钟</dd>
      </dl>
      {/* 切换次数的口径要写明：心跳切段不是切换，只有 end_reason = switch 才算
          （否则这个数字会大两个数量级，见 03 文档的访问与会话段之分）。 */}
      {rhythm.switches_basis ? (
        <div className="card__hint">口径：{rhythm.switches_basis}</div>
      ) : null}
      {blocks.length ? (
        <div className="focus-blocks">
          <div className="text-sm muted">最长的几段专注</div>
          {blocks.slice(0, 6).map((block) => (
            <div className="focus-block" key={`${block.start}-${block.display_name}`}>
              <span>
                {formatClock(block.start)}-{formatClock(block.end)}
              </span>
              <span className="truncate">{block.display_name}</span>
              <span className="numeric">{(Number(block.minutes) || 0).toFixed(0)} 分钟</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="card__hint">这段时间没有足够长的连续使用</div>
      )}
    </div>
  );
}

function Rhythm({ rhythm, loading }: { rhythm: RhythmResponse | undefined; loading: boolean }) {
  if (!rhythm) return loading ? <SkeletonRows count={2} /> : null;
  const active = rhythm.active_hours;
  const peak = rhythm.peak_kpm;
  return (
    <div className="stack">
      <dl className="kv-list">
        <dt>首次活动</dt>
        <dd>{active?.first || '-'}</dd>
        <dt>末次活动</dt>
        <dd>{active?.last || '-'}</dd>
        <dt>活跃跨度</dt>
        <dd>{(Number(active?.span_hours) || 0).toFixed(1)} 小时</dd>
        <dt>峰值 KPM</dt>
        <dd>{formatCount(peak?.value || 0)}</dd>
        <dt>峰值时刻</dt>
        <dd>{peak?.at ? formatClock(peak.at) : '-'}</dd>
      </dl>
    </div>
  );
}

/**
 * 键位 × 应用。选择器按当前周期的高频键动态生成（M3-6），不再硬编码 6 个键。
 *
 * 选择器 portal 到周期栏：它改的是请求参数（14 文档 §4.1）。
 */
function KeySplit() {
  const selectedKeyId = useSlice('selectedKeyId');
  const heatmap = useResource('insightHeatmap');
  const detail = useResource('insightKey');
  const slot = document.getElementById(FILTERS_SLOT_ID);

  const ranked = (heatmap.data?.keys || [])
    .filter((key) => (Number(key.press_count) || 0) > 0)
    .sort((left, right) => (Number(right.press_count) || 0) - (Number(left.press_count) || 0))
    .slice(0, KEY_CHOICES_LIMIT);
  const choices = ranked.map((key) => ({
    id: key.id,
    label: `${key.label} · ${formatCount(key.press_count)}`,
  }));
  // 用户从键盘视图带过来的选择可能不在高频榜里——保底追加，而不是悄悄换掉。
  if (selectedKeyId && !choices.some((choice) => choice.id === selectedKeyId)) {
    const known = (heatmap.data?.keys || []).find((key) => key.id === selectedKeyId);
    choices.push({ id: selectedKeyId, label: known?.label || selectedKeyId });
  }
  const current = selectedKeyId || choices[0]?.id || '';

  const selector =
    slot && choices.length
      ? createPortal(
          <select
            className="control"
            aria-label="选择键位"
            value={current}
            onChange={(event) => {
              setState('selectedKeyId', event.target.value);
              fetchInto(
                'insightKey',
                `/keyboard/keys/${event.target.value}`,
                periodParams(getState().period),
              );
            }}
          >
            {choices.map((choice) => (
              <option value={choice.id} key={choice.id}>
                {choice.label}
              </option>
            ))}
          </select>,
          slot,
        )
      : null;

  return (
    <>
      {selector}
      <div className="key-app-split">
        <KeyAppRows payload={detail.data} loading={detail.loading} />
      </div>
    </>
  );
}

function KeyAppRows({
  payload,
  loading,
}: {
  payload: KeyDetailResponse | undefined;
  loading: boolean;
}) {
  if (!payload) return loading ? <SkeletonRows count={2} /> : null;
  const byApp = payload.by_app || [];
  const totals = payload.totals;
  if (!byApp.length) {
    return (
      <EmptyState
        title={`${payload.key.label} 没有按应用拆分的数据`}
        detail="这个键在本周期内没有被按下，或按键发生在无法识别前台应用的时段"
        mark="·"
      />
    );
  }
  const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));
  return (
    <>
      <div className="text-sm muted">
        {payload.key.label} 的 {formatCount(totals?.press_count || 0)} 次按下来自：
      </div>
      {byApp.slice(0, 10).map((item) => (
        <div className="top-key" key={item.app_id}>
          <span className="rank" />
          <span className="truncate">{item.display_name}</span>
          <Bar ratio={(Number(item.press_count) || 0) / top} />
          <span className="top-key__count">{formatCount(item.press_count)}</span>
          <span className="top-key__percent">{formatPercent(item.percent)}</span>
        </div>
      ))}
    </>
  );
}
