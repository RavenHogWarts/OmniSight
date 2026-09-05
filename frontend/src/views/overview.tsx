// 总览 = TimeLens 的「所有使用」屏（17 文档 §4.2、16 文档 §A1）。两块内容通栏纵排：
//
//   每小时使用  应用图标带：24 行，一行一小时     ← `/usage/timeline`
//   所有使用    两列列表，不分页                  ← `/usage/period` 的完整列表
//
// **「屏幕时间」那一段已撤**（招牌卡 + 「最常使用」Top 8）。剩下的两块正是前身那张
// `.all-section`：它的正面是「所有使用」、背面靠右键翻面是「每小时」——本来就是同一处
// 地方的两副面孔，现在不翻面，纵向排下来（那个翻面交互见 14 文档 §4.1 末：
// prefers-reduced-motion 下无从降级，不学）。
//
// 撤走的量各有落点，不是只存在于招牌卡里：合计时长在「所有使用」的段标题右侧；类别构成
// 与结论在洞察·构成与结论；按键总数与峰值在键盘视图。**只有跨周期对照柱没有第二处**，
// 它随卡一起下线（`charts/context-bars.ts` 一并删掉，不留没人消费的模块）。
//
// 顺序：先按小时、再按应用摊开全表——同一段时间从"什么时候"读到"哪个应用"。
//
// 取数：两个独立请求，各有自己的骨架屏，谁先到谁先画（07 文档 §5.2）。
import { useMemo } from 'react';
import { HourBand } from '../components/HourBand.tsx';
import { Section } from '../components/Card.tsx';
import { UsageList } from '../components/UsageList.tsx';
import { Updated } from '../components/PeriodNav.tsx';
import { capabilityOf, noticeFor } from '../components/degraded.tsx';
import { CapabilityNotice, EmptyState, ErrorState, SkeletonRows } from '../components/states.tsx';
import { getState, setState } from '../core/store.ts';
import { useResource, useSlice } from '../core/useStore.ts';
import { periodParams } from '../domain/period.ts';
import type { State } from '../core/store.ts';
import type { DataRequest } from '../types/api.d.ts';

export const title = '总览';

export function needs(state: State): DataRequest[] {
  const period = periodParams(state.period);
  return [
    // 「所有使用」：不分页、要全量，因此 limit 给得足够大而不是 25。
    { key: 'overviewAll', path: '/usage/period', params: { ...period, limit: 200 } },
    // 「每小时」图标带：`top` 给到后端上限 20（`presentation/api/usage.py` 的 maximum）。
    // 前身那一块不限个数，而通栏一行装得下二十几枚图标——给 10 会让 `+N` 吞掉本来放得
    // 下的那几个。
    { key: 'overviewTimeline', path: '/usage/timeline', params: { ...period, top: 20 } },
  ];
}

/** 重取当前周期：把 period 原样写回去，触发 main 的取数订阅。 */
function reload(): void {
  setState('period', { ...getState().period });
}

export function View() {
  return (
    <>
      <h1 className="view__title sr-only" tabIndex={-1} id="view-title">
        总览
      </h1>
      <div className="overview">
        {/* 「更新于」轮到这一段来带（17 文档 §8 的 D9：每屏都得说得出这些数算于何时）
            ——它原先挂在「屏幕时间」上，而那一段已经没有了。 */}
        <Section title="每小时使用" right={<Updated />} lead>
          <Hourly />
        </Section>

        <Section title="所有使用" right={<AllCount />}>
          <AllUsage />
        </Section>
      </div>
    </>
  );
}

/** 段标题右侧那行小字：应用数与合计时长。前身在这里放的是日期，我们已经有周期带了。 */
function AllCount() {
  const { data } = useResource('overviewAll');
  if (!data) return null;
  return (
    <p className="updated">
      {data.app_count} 个应用，合计 {data.total_seconds_formatted}
    </p>
  );
}

function AllUsage() {
  const { data, loading, error } = useResource('overviewAll');
  if (error) {
    return (
      <div className="usage-list">
        <ErrorState message={error.message} onRetry={reload} />
      </div>
    );
  }
  if (!data) {
    return <div className="usage-list">{loading ? <SkeletonRows count={6} /> : null}</div>;
  }
  const apps = data.apps || [];
  return (
    <UsageList
      apps={apps}
      split
      empty={<EmptyState title="这段时间没有使用记录" detail="换一个日期，或确认采集正在运行" />}
    />
  );
}

/**
 * 每小时图标带。24 行 ×（小时 + 那一小时用过的应用图标），前身 TimeLens 的
 * `.hourly-icon-list`——它回答的是"那个小时我在干什么"，而柱状图只回答"多久"。
 *
 * 类别表从「所有使用」那一份列表里现取（`/usage/period` 的行带 `category`）：小时行
 * 本身不带类别，而首字母兜底块要与那张列表同色，否则同一个应用会在两处长得不一样。
 */
function Hourly() {
  const { data, loading } = useResource('overviewTimeline');
  const { data: all } = useResource('overviewAll');
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const categories = useMemo(
    () => new Map((all?.apps || []).map((app) => [app.app_id, app.category])),
    [all],
  );

  // 归因不可用时这一屏两段都会是空的，而**只有这里说得出为什么**：那句话原先挂在「最
  // 常使用」的面板正文里，那张卡已经撤了（06 文档 §4.2 第二级）。不给重试按钮——重试
  // 不会改变结果。
  if (!capabilityOf(capabilities, 'foreground')) {
    const notice = noticeFor(degraded, 'foreground');
    return (
      <div className="hour-band">
        <CapabilityNotice
          title={notice?.title || '当前环境不支持识别前台应用'}
          detail={notice?.detail || '键盘统计不受影响，但无法按应用拆分时长。'}
          hint={notice?.hint || ''}
        />
      </div>
    );
  }

  if (!data) return loading ? <SkeletonRows count={6} /> : null;
  const hours = data.hours || [];
  if (!hours.some((hour) => (hour.total_seconds || 0) > 0)) {
    return (
      // 空态套同一个 `.hour-band` 外壳：它带卡面，否则空态会裸在页底色上，而有数据时是
      // 一张卡——同一块内容在两种状态下承载面不同。
      <div className="hour-band">
        <EmptyState
          title="这段时间没有小时级记录"
          detail="把范围切到「每天」时这一块最有用：它按小时列出那一刻在用的应用"
        />
      </div>
    );
  }
  return <HourBand hours={hours} categories={categories} />;
}
