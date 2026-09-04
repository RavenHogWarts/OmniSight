// 单条 100% 构成条（14 文档 §2.10）。
//
// 它替换的是环形图。三条理由，任何一条都够：扇区顺序由数据决定（因此是 all-pairs
// 场景，而 all-pairs 能安全承载的身份色上限约 3–4 个，这里有 6 个）；命中区是扇区
// 中点的 24×24 方块，既不覆盖整个扇区也不精确；旁边的类别列表已经把名称、占比、
// 时长全列了一遍，环形图只多贡献了一次颜色匹配。
//
// **槽位顺序固定**（后端 CATEGORIES 的顺序），不按大小排：相邻关系因此确定、可以
// 事先校验，而且同一个类别在每个周期都在同一个位置，跨周期对比更容易。
//
// 用 DOM 而不是 canvas：单条构成条用 flex 就是几行 CSS，而且天然可悬停、可读屏、
// 可选中文字——canvas 要为这些各写一遍。
import { formatPercent } from '../domain/format.ts';

export interface StackSegment {
  id: string;
  name: string;
  percent: number;
  /** 后端给的预格式化值（`seconds_formatted` 一类）。 */
  formatted?: string;
}

export function StackBar({
  segments,
  label = '构成',
  onSelect = null,
}: {
  segments: readonly StackSegment[] | undefined;
  label?: string;
  onSelect?: ((id: string) => void) | null;
}) {
  const items = (segments || []).filter((item) => (Number(item.percent) || 0) > 0);
  const summary = items.length
    ? `${label}：${items.map((item) => `${item.name} ${formatPercent(item.percent)}`).join('，')}`
    : `${label}：暂无数据`;

  return (
    <>
      <div
        className={onSelect ? 'stackbar stackbar--clickable' : 'stackbar'}
        role="img"
        aria-label={summary}
        onClick={
          onSelect
            ? (event) => {
                const segment = (event.target as HTMLElement).closest('.stackbar__seg');
                const id = (segment as HTMLElement | null)?.dataset.id;
                if (id) onSelect(id);
              }
            : undefined
        }
      >
        {items.map((item) => {
          const percent = Number(item.percent) || 0;
          return (
            <span
              key={item.id}
              className="stackbar__seg"
              data-category={item.id}
              data-id={item.id}
              style={{ flexGrow: percent }}
              title={`${item.name}：${item.formatted ?? ''}（${formatPercent(percent)}）`}
            >
              {/* 内联标签只在装得下时出现（约 9%）；装不下时交给列表与悬停，
                  绝不缩字或裁字（14 文档 §4.3）。 */}
              {percent >= 9 ? <span className="stackbar__label">{item.name}</span> : null}
            </span>
          );
        })}
      </div>
      <div className="sr-only">
        <table>
          <caption>{label}</caption>
          <thead>
            <tr>
              <th>类别</th>
              <th>占比</th>
              <th>数值</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.name ?? ''}</td>
                <td>{formatPercent(item.percent)}</td>
                <td>{item.formatted ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
