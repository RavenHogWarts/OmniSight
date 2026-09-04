import { O as formatDuration, P as assetUrl, T as formatCount, Y as require_react, j as initialOf, q as require_jsx_runtime } from "./main-DA_wrxiB.js";
//#region frontend/src/components/AppRow.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
function AppRow({ app, maxSeconds = 0, maxKpm = 0, expanded = false, onToggle = null }) {
	const label = app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`;
	const seconds = Number(app.seconds ?? app.total_seconds ?? 0);
	const pressCount = Number(app.presses ?? app.total_presses ?? 0);
	const kpm = Number(app.kpm || 0);
	const meta = [app.process_name, app.category_name || null].filter(Boolean).join(" · ");
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-row",
		"data-app-id": app.app_id,
		"data-category": app.category || "uncategorized",
		role: "button",
		tabIndex: 0,
		"aria-expanded": expanded,
		onClick: () => onToggle?.(app.app_id),
		onKeyDown: (event) => {
			if (event.key !== "Enter" && event.key !== " ") return;
			event.preventDefault();
			onToggle?.(app.app_id);
		},
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppIcon, {
				iconUrl: app.icon_url,
				label
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "app-row__main",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "app-row__name",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "truncate",
							children: label
						}), app.is_running ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "app-row__running",
							title: "正在运行"
						}) : null]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "app-row__meta",
						children: meta
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "bar app-row__bar",
						style: { "--fill": maxSeconds ? seconds / maxSeconds : 0 },
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {})
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "app-row__stats",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "app-row__duration",
						children: app.seconds_formatted || app.total_seconds_formatted || formatDuration(seconds)
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "app-row__percent",
						children: app.percent === void 0 || app.percent === null ? "" : `${app.percent.toFixed(1)}%`
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
						className: "app-row__presses",
						children: [formatCount(pressCount), " 次"]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "bar bar--kpm",
						style: { "--fill": maxKpm ? kpm / maxKpm : 0 },
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {})
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-xs muted numeric",
						children: kpm ? `${kpm.toFixed(0)} KPM` : ""
					})
				]
			})
		]
	});
}
/**
* 图标：`icon_url` 由后端给，204 表示"没有图标"（不是 404，应用是存在的）。
* 取不到就显示首字母色块——这条路径在 icons 能力缺失的机器上是常态。
*/
function AppIcon({ iconUrl, label }) {
	const [broken, setBroken] = (0, import_react.useState)(false);
	const url = iconUrl ? assetUrl(iconUrl) : "";
	if (!url || broken) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "app-row__initial",
		children: initialOf(label)
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", {
		className: "app-row__icon",
		src: url,
		alt: "",
		loading: "lazy",
		decoding: "async",
		onError: () => setBroken(true)
	});
}
//#endregion
export { AppRow as t };
