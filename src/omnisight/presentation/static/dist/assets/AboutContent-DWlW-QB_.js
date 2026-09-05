import { W as require_jsx_runtime } from "./degraded-qMnijys5.js";
//#region frontend/src/components/AboutContent.tsx
var import_jsx_runtime = require_jsx_runtime();
function AboutContent({ payload }) {
	const platform = payload.platform || {};
	const paths = payload.paths || {};
	const pause = payload.pause || {};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "onboarding__lists",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(FactList, {
				title: "会记录",
				items: payload.records,
				itemClass: "onboarding__item--yes",
				mark: "✓"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(FactList, {
				title: "不记录",
				items: payload.not_records,
				itemClass: "onboarding__item--no",
				mark: "✗"
			})]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "onboarding__notice",
			role: "note",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "平台支持" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: platform.notice || "" }),
				platform.tier_label ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "muted",
					children: platform.tier_label
				}) : null
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "onboarding__section",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { children: "数据在哪" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PathRow, {
					label: "数据库",
					value: paths.database
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PathRow, {
					label: "数据目录",
					value: paths.data_dir
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PathRow, {
					label: "日志目录",
					value: paths.logs_dir
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PathRow, {
					label: "配置文件",
					value: paths.config
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "muted",
					children: "托盘菜单与设置页「数据」段里的「打开数据目录」直接跳到这里；卸载时删掉它就没有残留。"
				})
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "onboarding__section",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { children: "如何暂停" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: pause.detail || "" })]
		})
	] });
}
function FactList({ title, items, itemClass, mark }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "onboarding__list",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { children: title }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", { children: (items || []).map((item, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
			className: `onboarding__item ${itemClass}`,
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "onboarding__mark",
				"aria-hidden": "true",
				children: mark
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: item.text || "" }), item.detail ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: item.detail
			}) : null] })]
		}, index)) })]
	});
}
function PathRow({ label, value }) {
	if (!value) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "onboarding__path",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "onboarding__path-label",
			children: label
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { children: value })]
	});
}
//#endregion
export { AboutContent as t };
