// 带标题与右上角控件的卡片。四个视图共用，避免每处各写一遍 card__head。
//
// 放在 components/ 而不是某个 view 里：views 不互相 import（07 文档 §3 的分层规则）。
import type { ReactNode } from 'react';

export interface CardProps {
  title: string;
  /** 右上角控件（分段、下拉、复选）。 */
  controls?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  /** 刷新中：卡片顶沿一条细进度条，旧数据留在原位（06 文档 §10.1 第二态）。 */
  refreshing?: boolean;
  id?: string;
}

export function Card({ title, controls, footer, children, refreshing, id }: CardProps) {
  return (
    <section className="card" id={id} data-refreshing={refreshing ? 'true' : undefined}>
      <div className="card__head">
        <h2 className="card__title">{title}</h2>
        <span className="spacer" />
        {controls}
      </div>
      {children}
      {footer}
    </section>
  );
}
