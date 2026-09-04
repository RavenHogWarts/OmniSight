// 四种状态（06 文档 §10.1）。**它们必须长得不一样**，这就是本文件存在的理由：
//
//   加载中（首次）  骨架屏，形状与真实内容一致
//   加载中（刷新）  保留旧数据 + 卡片顶沿细进度条（CSS 的 data-refreshing）
//   无数据（正常）  "这一天没有记录" + 跳到最近有数据的日期
//   加载失败        具体原因 + 重试按钮
//   能力不可用      面板内说明块，**不给重试按钮**——重试不会改变结果
//
// 最后两种最容易被合并成一种，而合并的后果是用户在 Wayland 上看到"这一天没有记录"
// 然后去排查自己的使用习惯。
import type { ReactNode } from 'react';
import { Icon } from './Icon.tsx';

export function Skeleton({ kind = 'text', count = 1 }: { kind?: string; count?: number }) {
  if (count === 1) return <div className={`skeleton skeleton--${kind}`} />;
  return (
    <div>
      {Array.from({ length: count }, (_unused, index) => (
        <div key={index} className={`skeleton skeleton--${kind}`} />
      ))}
    </div>
  );
}

export function SkeletonRows({ count = 5 }: { count?: number }) {
  return <Skeleton kind="row" count={count} />;
}

export interface EmptyStateProps {
  title: string;
  detail?: string;
  /** 默认是一个空心圆。空态图标是内联 SVG，与全站一致（14 文档 §3.5）。 */
  mark?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, detail = '', mark = '○', action = null }: EmptyStateProps) {
  return (
    <div className="empty">
      <div className="empty__mark" aria-hidden="true">
        {mark}
      </div>
      <div className="empty__title">{title}</div>
      {detail ? <div className="empty__detail">{detail}</div> : null}
      {action}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry = null,
}: {
  message?: string;
  onRetry?: (() => void) | null;
}) {
  return (
    <div className="empty empty--error" role="alert">
      <div className="empty__mark" aria-hidden="true">
        <Icon name="warning" size={28} />
      </div>
      <div className="empty__title">加载失败</div>
      <div className="empty__detail">{message || '未知错误'}</div>
      {onRetry ? (
        <button className="button" type="button" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}

/**
 * 面板内的能力说明块（06 文档 §4.2 第二级）。
 *
 * 文案的三段（缺什么 / 什么仍然正常 / 怎么解决）由**后端**给：
 * degraded[].title / .detail / .hint。前端不编文案，也不判断平台——
 * 否则每加一个平台都要改前端（07 文档 §10 第 4 行）。
 */
export function CapabilityNotice({
  title,
  detail = '',
  hint = '',
}: {
  title: string;
  detail?: string;
  hint?: string;
}) {
  return (
    <div className="notice" role="note">
      <span className="notice__mark" aria-hidden="true">
        <Icon name="info" />
      </span>
      <div>
        <div className="notice__title">{title}</div>
        {detail ? <div className="notice__detail">{detail}</div> : null}
        {hint ? <div className="notice__hint">{hint}</div> : null}
      </div>
    </div>
  );
}

/** 数据缺口的图例注记。图表里画斜纹，图例里说明斜纹是什么意思。 */
export function GapLegend({ count }: { count: number }) {
  if (!count) return null;
  return (
    <div className="heat-legend">
      <span className="heat-legend__step hatched" aria-hidden="true" />
      <span>{count} 天没有采集记录（斜纹），不是零</span>
    </div>
  );
}
