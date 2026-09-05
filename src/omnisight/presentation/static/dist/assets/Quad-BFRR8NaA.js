import { C as useSlice, E as setState, K as require_react, N as assetUrl, U as Icon, W as require_jsx_runtime, _ as formatDuration, g as formatDayTime, x as initialOf } from "./degraded-mkfLsXii.js";
import { i as Segmented, r as SearchBox } from "./controls-CgVt8_vH.js";
//#region frontend/src/components/AppGrid.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
var GROUPS = [
	{
		id: "recent",
		name: "最近使用"
	},
	{
		id: "most_used",
		name: "最多使用"
	},
	{
		id: "running",
		name: "正在运行"
	}
];
/** 一屏最多铺多少格。再多就该用搜索，而不是往下滚一整屏图标。 */
var GRID_LIMIT = 60;
function num(value) {
	return Number(value) || 0;
}
function stamp(app) {
	return String(app.last_seen_at || "");
}
function haystack(app) {
	return `${app.user_alias || ""} ${app.display_name || ""} ${app.process_name || ""}`.toLowerCase();
}
function emptyText(needle, group) {
	if (needle) return "没有匹配的应用";
	return group === "running" ? "当前没有已记录的应用在运行" : "这段时间还没有应用记录";
}
function AppGrid({ apps, runningIds = [], selectedId, onPick, allowAll = true, searchKey = "grid", onMenu }) {
	const group = useSlice("appsGroup");
	const setGroup = (id) => setState("appsGroup", id);
	const [query, setQuery] = (0, import_react.useState)("");
	const list = apps || [];
	const running = new Set([...runningIds].filter((id) => typeof id === "number"));
	const ordered = () => {
		const copy = [...list];
		if (group === "running") return copy.filter((app) => running.has(app.app_id)).sort((left, right) => stamp(right).localeCompare(stamp(left)));
		if (group === "most_used") return copy.sort((left, right) => num(right.total_seconds) - num(left.total_seconds));
		return copy.sort((left, right) => stamp(right).localeCompare(stamp(left)));
	};
	/** 副行随分组变：三个分组各自回答的问题不同，副行必须跟着换（前身也是这样）。 */
	const metaOf = (app) => {
		if (group === "running") return "窗口正在运行";
		if (group === "most_used") return app.total_seconds_formatted || formatDuration(num(app.total_seconds));
		return app.last_seen_at ? `最近 ${formatDayTime(app.last_seen_at)}` : app.process_name || "";
	};
	const needle = query.toLowerCase();
	const matched = ordered().filter((app) => !needle || haystack(app).includes(needle));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-grid__filters",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SearchBox, {
			placeholder: "搜索应用",
			onInput: setQuery
		}, searchKey), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "app-grid__groups",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
				items: GROUPS,
				active: group,
				onPick: setGroup,
				variant: "lg",
				label: "应用分组"
			})
		})]
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-grid",
		children: [
			allowAll && !needle ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Cell, {
				active: !selectedId,
				label: "全部应用",
				meta: `${list.length} 个应用`,
				mark: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
					name: "apps",
					size: 18
				}),
				onPick: () => onPick(null)
			}) : null,
			matched.slice(0, GRID_LIMIT).map((app) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Cell, {
				active: selectedId === app.app_id,
				category: app.category,
				label: app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`,
				meta: metaOf(app),
				mark: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Mark, { app }),
				onPick: () => onPick(app.app_id),
				onMenu: onMenu ? (event) => onMenu(app, event) : void 0
			}, app.app_id)),
			matched.length ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "app-grid__empty",
				children: emptyText(needle, group)
			}),
			matched.length > GRID_LIMIT ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "app-grid__empty",
				children: [
					"还有 ",
					matched.length - GRID_LIMIT,
					" 个，用搜索找"
				]
			}) : null
		]
	})] });
}
function Cell({ active, label, meta, mark, category, onPick, onMenu }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
		className: "app-grid__cell",
		type: "button",
		"aria-pressed": active,
		"data-category": category,
		onClick: onPick,
		onContextMenu: onMenu ? (event) => {
			event.preventDefault();
			onMenu(event);
		} : void 0,
		children: [mark, /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
			className: "app-grid__cell-copy",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "app-grid__label",
				title: label,
				children: label
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "app-grid__meta",
				children: meta
			})]
		})]
	});
}
/** 图标取不到就是首字母块——与使用列表同一条兜底路径。 */
function Mark({ app }) {
	const [broken, setBroken] = (0, import_react.useState)(false);
	const label = app.user_alias || app.display_name || "?";
	const url = app.icon_url ? assetUrl(app.icon_url) : "";
	if (!url || broken) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "app-grid__initial",
		children: initialOf(label)
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", {
		className: "app-grid__icon",
		src: url,
		alt: "",
		loading: "lazy",
		decoding: "async",
		onError: () => setBroken(true)
	});
}
/**
* 42px 的选中应用头像（应用视图的面板头）。与 `Mark` 同一条兜底路径，只是更大。
*
* `app` 为 null 是「全部应用」那一态，**不是取图标失败**——所以它画网格图标而不是
* 一个 `?` 首字母块（后者读起来像出错了）。
*/
function BigMark({ app }) {
	const [broken, setBroken] = (0, import_react.useState)(false);
	const url = app?.icon_url ? assetUrl(app.icon_url) : "";
	if (!app) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "app-grid__mark-initial app-grid__mark-initial--all",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
			name: "apps",
			size: 22
		})
	});
	if (!url || broken) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "app-grid__mark-initial",
		children: initialOf(app.user_alias || app.display_name || "?")
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", {
		className: "app-grid__mark",
		src: url,
		alt: "",
		loading: "lazy",
		decoding: "async",
		onError: () => setBroken(true)
	});
}
//#endregion
//#region frontend/src/components/Quad.tsx
function Quad({ items }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "quad",
		children: items.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "quad__cell",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "quad__label",
				children: item.label
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", {
				className: "quad__value",
				title: item.value,
				children: item.value
			})]
		}, item.label))
	});
}
//#endregion
export { Mark as i, AppGrid as n, BigMark as r, Quad as t };
