// 带标题与右上角控件的卡片，加上卡**外**的段标题行。四个视图共用，避免每处各写一遍。
//
// 放在 components/ 而不是某个 view 里：views 不互相 import（07 文档 §3 的分层规则）。
//
// 两种标题的分工（17 文档 §5.2）：`Card` 的 `card__head` 在描边**内**，读起来是"这张
// 卡的表头"；`Section` 的 `section-heading` 在卡外，读起来是"下面这一组卡讲的是什么"。
// 前身两种都有（TimeLens 的 `.section-heading` 与 `.keyboard-card-header`），我们也是。
import type { ReactNode } from 'react';

export interface CardProps {
  title: string;
  /** 右上角控件（分段、下拉、复选）。 */
  controls?: ReactNode;
  /** 标题下面那行 11px 副标题（"颜色越深，使用次数越多"这类说明）。 */
  subtitle?: string;
  /**
   * 紧贴标题右侧的一个小控件（通常是图标钮）。
   *
   * 与 `controls` 的区别只有位置，而位置就是意思：`controls` 在卡头最右端，读作"这张卡的
   * 开关"；`titleAside` 在标题这一句的旁边，读作"这一句的延伸"——「关于」旁边那个去隐私
   * 说明的图标属于后者（18 文档 批 7）。
   */
  titleAside?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  /** 刷新中：卡片顶沿一条细进度条，旧数据留在原位（06 文档 §10.1 第二态）。 */
  refreshing?: boolean;
  id?: string;
  className?: string;
}

export function Card({
  title,
  controls,
  subtitle,
  titleAside,
  footer,
  children,
  refreshing,
  id,
  className,
}: CardProps) {
  return (
    <section
      className={className ? `card ${className}` : 'card'}
      id={id}
      data-refreshing={refreshing ? 'true' : undefined}
    >
      <div className="card__head">
        <div>
          <div className="card__title-row">
            <h2 className="card__title">{title}</h2>
            {titleAside}
          </div>
          {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
        </div>
        <span className="spacer" />
        {controls}
      </div>
      {children}
      {footer}
    </section>
  );
}

export interface SectionProps {
  title: string;
  /** 段标题右侧那行小字。通常是 `<Updated />`。 */
  right?: ReactNode;
  /** 标题下面那行 12px 说明（"只统计键位次数，不保存输入内容"）。 */
  sub?: string;
  /** 一屏第一块：标题重一档（20px + 主文字色）。 */
  lead?: boolean;
  children?: ReactNode;
}

export function Section({ title, right, sub, lead = false, children }: SectionProps) {
  return (
    <section className="section">
      <div className={lead ? 'section-heading section-heading--lead' : 'section-heading'}>
        <div>
          <h2 className="section-title">{title}</h2>
          {sub ? <p className="section-sub">{sub}</p> : null}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}
