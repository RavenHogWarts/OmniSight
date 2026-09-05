// 四格摘要（17 文档 §4.3/§4.4，KeyTrace 的 `.app-summary`）。
//
// 两处用它：键盘视图的四格总计（按键次数/活跃键位/平均时长/最长按压）、应用面板里
// 选中应用的四格键盘统计。**同一份几何**，因为它们回答的是同一类问题——"这个范围的
// 四个关键读数是多少"。
//
// 它刻意不是四张 `StatCard`：那种卡是键帽形状的英雄数字，一屏只该有一个（14 文档
// §2.6）。这里的四个数是并列的读数，没有主次。
export interface QuadItem {
  label: string;
  value: string;
}

export function Quad({ items }: { items: readonly QuadItem[] }) {
  return (
    <div className="quad">
      {items.map((item) => (
        <div className="quad__cell" key={item.label}>
          <span className="quad__label">{item.label}</span>
          <strong className="quad__value" title={item.value}>
            {item.value}
          </strong>
        </div>
      ))}
    </div>
  );
}
