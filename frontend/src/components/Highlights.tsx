// 结论列表：总览与洞察共用（M4 判据 4）。
//
// 每条结论都是原生 <details>，点开就是这条结论的计算口径（后端下发的 basis）。
// 用 details/summary 而不是按钮 + 显隐：键盘可达与展开语义浏览器免费给。
import type { Highlight } from '../types/api.d.ts';

export function Highlights({ items }: { items: readonly Highlight[] | undefined }) {
  const list = items || [];
  if (!list.length) {
    return <div className="dim text-sm">数据还不够多，暂时得不出结论</div>;
  }
  return (
    <>
      {list.map((item, index) => (
        <details className="highlight" key={`${index}-${item.text}`}>
          <summary>
            <span className="highlight__mark" aria-hidden="true">
              ◈
            </span>
            <span>{item.text}</span>
            {item.basis ? (
              <span className="highlight__toggle" aria-hidden="true">
                口径
              </span>
            ) : null}
          </summary>
          {item.basis ? <div className="highlight__basis">口径：{item.basis}</div> : null}
        </details>
      ))}
    </>
  );
}
