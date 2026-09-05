// 「记录什么、不记录什么、数据在哪、如何暂停」这一段内容（08 文档 §6.1、18 文档 批 4）。
//
// **两处共用同一份排版**：首次运行时它在一个必须点确认的模态里（components/Onboarding.tsx），
// 之后它是 `/about` 那一页的正文（pages/AboutPage.tsx）。08 文档 §6.1 的两条要求因此都成立
// ——首启必须走完"我看到了"这一步，而"之后仍然找得到"从一个模态升级成一个有地址的页面。
//
// 内容**全部来自后端** `GET /api/v1/onboarding`：两张清单由后端按当前能力与配置算出来，
// 前端只负责排版。写死在前端就等于承诺一件自己无从保证的事。
import type { ReactNode } from 'react';
import type { OnboardingRecord, OnboardingResponse } from '../types/api.d.ts';

export function AboutContent({ payload }: { payload: OnboardingResponse }) {
  const platform = payload.platform || {};
  const paths = payload.paths || {};
  const pause = payload.pause || {};
  return (
    <>
      <div className="onboarding__lists">
        <FactList title="会记录" items={payload.records} itemClass="onboarding__item--yes" mark="✓" />
        <FactList
          title="不记录"
          items={payload.not_records}
          itemClass="onboarding__item--no"
          mark="✗"
        />
      </div>

      {/* 平台承诺（12 文档 M6 判据 5）：这句话必须出现，且不暗示已支持跨平台。 */}
      <div className="onboarding__notice" role="note">
        <strong>平台支持</strong>
        <p>{platform.notice || ''}</p>
        {platform.tier_label ? <p className="muted">{platform.tier_label}</p> : null}
      </div>

      <div className="onboarding__section">
        <h3>数据在哪</h3>
        <PathRow label="数据库" value={paths.database} />
        <PathRow label="数据目录" value={paths.data_dir} />
        <PathRow label="日志目录" value={paths.logs_dir} />
        <PathRow label="配置文件" value={paths.config} />
        <p className="muted">
          托盘菜单与设置页「数据」段里的「打开数据目录」直接跳到这里；卸载时删掉它就没有残留。
        </p>
      </div>

      <div className="onboarding__section">
        <h3>如何暂停</h3>
        <p>{pause.detail || ''}</p>
      </div>
    </>
  );
}

function FactList({
  title,
  items,
  itemClass,
  mark,
}: {
  title: string;
  items: readonly OnboardingRecord[] | undefined;
  itemClass: string;
  mark: ReactNode;
}) {
  return (
    <section className="onboarding__list">
      <h3>{title}</h3>
      <ul>
        {(items || []).map((item, index) => (
          <li className={`onboarding__item ${itemClass}`} key={index}>
            <span className="onboarding__mark" aria-hidden="true">
              {mark}
            </span>
            <div>
              <span>{item.text || ''}</span>
              {item.detail ? <p className="muted">{item.detail}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PathRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="onboarding__path">
      <span className="onboarding__path-label">{label}</span>
      {/* 路径用 code 而不是普通文本：Windows 路径里的反斜杠在等宽字体下才不易读错。 */}
      <code>{value}</code>
    </div>
  );
}
