// 内联 SVG 图标（14 文档 §3.5）。
//
// 为什么不是字形：`⚙` `◐` `‹` `ⓘ` 这些 Unicode 符号在 Windows 上落到 Segoe UI Symbol，
// 笔重与度量都和正文字族不同源，`ⓘ`（U+24D8）尤其突兀——它是一个实心圆圈字符，和界面
// 里其它一切都不像。为什么不是图标字体或 CDN：无构建、无出站网络、CSP 只允许 'self'
// （07 文档 §2、08 文档 §3）。剩下的选项就是把 SVG 内联进来。
//
// **精灵表在 templates/dashboard.html 里**，不在这里：它是一份静态标记，模板里写一遍
// 就够了，用 JS 建反而要处理命名空间（SVG 元素必须用 createElementNS，而 core/dom.js
// 的 h() 走的是 createElement）。这个模块只负责引用精灵表里的 <symbol>。

/** 精灵表里有哪些图标。改这里之前先改模板——两边的 id 必须对得上。 */
export const ICON_NAMES = Object.freeze([
  'gear', 'theme', 'left', 'right', 'info', 'keyboard', 'apps', 'insights',
  'overview', 'download', 'pause', 'more', 'search', 'close', 'warning',
]);

/**
 * 一个图标。默认 aria-hidden——图标几乎总是配着文字出现；只有纯图标按钮才需要名字，
 * 那时名字应该写在按钮的 aria-label 上，不是写在图标里。
 * @param {string} name 精灵表里的 id（不含 `i-` 前缀）
 * @param {{ size?: number }} [options]
 * @returns {SVGSVGElement}
 */
export function icon(name, { size = 16 } = {}) {
  const svg = svgEl('svg', { class: 'icon', 'aria-hidden': 'true', focusable: 'false' });
  if (size !== 16) {
    svg.style.setProperty('width', `${size}px`);
    svg.style.setProperty('height', `${size}px`);
  }
  svg.append(svgEl('use', { href: `#i-${name}` }));
  return /** @type {SVGSVGElement} */ (svg);
}

/**
 * SVG 必须用带命名空间的创建方式：`document.createElement('svg')` 建出来的是一个
 * HTML 未知元素，不会渲染成图形。
 * @param {string} tag
 * @param {Record<string, string>} [attrs]
 */
function svgEl(tag, attrs = {}) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
  return node;
}
