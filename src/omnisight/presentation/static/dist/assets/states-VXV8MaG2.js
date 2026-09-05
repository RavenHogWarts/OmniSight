import { G as Icon, K as require_jsx_runtime } from "./main-DULowGlx.js";
//#region frontend/src/components/Card.tsx
var import_jsx_runtime = require_jsx_runtime();
function Card({ title, controls, subtitle, footer, children, refreshing, id, className }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: className ? `card ${className}` : "card",
		id,
		"data-refreshing": refreshing ? "true" : void 0,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "card__head",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
						className: "card__title",
						children: title
					}), subtitle ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "card__subtitle",
						children: subtitle
					}) : null] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "spacer" }),
					controls
				]
			}),
			children,
			footer
		]
	});
}
function Section({ title, right, sub, lead = false, children }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "section",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: lead ? "section-heading section-heading--lead" : "section-heading",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "section-title",
				children: title
			}), sub ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "section-sub",
				children: sub
			}) : null] }), right]
		}), children]
	});
}
//#endregion
//#region frontend/src/components/states.tsx
function Skeleton({ kind = "text", count = 1 }) {
	if (count === 1) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: `skeleton skeleton--${kind}` });
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: Array.from({ length: count }, (_unused, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: `skeleton skeleton--${kind}` }, index)) });
}
function SkeletonRows({ count = 5 }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Skeleton, {
		kind: "row",
		count
	});
}
function EmptyState({ title, detail = "", mark = "○", action = null }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "empty",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "empty__mark",
				"aria-hidden": "true",
				children: mark
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "empty__title",
				children: title
			}),
			detail ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "empty__detail",
				children: detail
			}) : null,
			action
		]
	});
}
function ErrorState({ message, onRetry = null }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "empty empty--error",
		role: "alert",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "empty__mark",
				"aria-hidden": "true",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
					name: "warning",
					size: 28
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "empty__title",
				children: "加载失败"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "empty__detail",
				children: message || "未知错误"
			}),
			onRetry ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button",
				type: "button",
				onClick: onRetry,
				children: "重试"
			}) : null
		]
	});
}
/**
* 面板内的能力说明块（06 文档 §4.2 第二级）。
*
* 文案的三段（缺什么 / 什么仍然正常 / 怎么解决）由**后端**给：
* degraded[].title / .detail / .hint。前端不编文案，也不判断平台——
* 否则每加一个平台都要改前端（07 文档 §10 第 4 行）。
*/
function CapabilityNotice({ title, detail = "", hint = "" }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "notice",
		role: "note",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "notice__mark",
			"aria-hidden": "true",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "info" })
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "notice__title",
				children: title
			}),
			detail ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "notice__detail",
				children: detail
			}) : null,
			hint ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "notice__hint",
				children: hint
			}) : null
		] })]
	});
}
/** 数据缺口的图例注记。图表里画斜纹，图例里说明斜纹是什么意思。 */
function GapLegend({ count }) {
	if (!count) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "heat-legend",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "heat-legend__step hatched",
			"aria-hidden": "true"
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [count, " 天没有采集记录（斜纹），不是零"] })]
	});
}
//#endregion
export { SkeletonRows as a, GapLegend as i, EmptyState as n, Card as o, ErrorState as r, Section as s, CapabilityNotice as t };
