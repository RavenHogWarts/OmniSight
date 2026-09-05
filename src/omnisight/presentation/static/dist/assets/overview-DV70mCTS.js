import { A as initialOf, B as noticeFor, H as useSlice, J as require_react, K as require_jsx_runtime, N as assetUrl, O as formatDurationShort, U as getState, V as useResource, W as setState, h as periodParams, k as formatPercent, n as hide, o as Updated, r as show, z as capabilityOf } from "./main-DULowGlx.js";
import { a as SkeletonRows, n as EmptyState, r as ErrorState, s as Section, t as CapabilityNotice } from "./states-VXV8MaG2.js";
//#region frontend/src/components/HourBand.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
/** 一个图标槽的宽度（图标 28px + 间距 8px），与 hour-band.css 里的值一致；前身同值。 */
var ICON_SLOT = 36;
/** `+N` 那一格占掉的宽度（38px + 8px 间距）。 */
var MORE_SLOT = 46;
/** 还没量到宽度时的容量（面板隐藏、或 ResizeObserver 第一次回调之前）。
*
*  通栏一行的图标格宽约 1036 − 28（卡内边距）− 54 − 12 ≈ 940px，即 26 个图标槽，比后端
*  `top=20` 还多——所以兜底值给 8 只是"先画一部分"，量到宽度之后立刻补齐。 */
var CAPACITY_FALLBACK = 8;
var HOURS = Array.from({ length: 24 }, (_unused, hour) => hour);
function num(value) {
	return Number(value) || 0;
}
function HourBand({ hours, categories = null, gap = false }) {
	const root = (0, import_react.useRef)(null);
	const [capacity, setCapacity] = (0, import_react.useState)(CAPACITY_FALLBACK);
	(0, import_react.useEffect)(() => {
		const node = root.current;
		if (!node) return;
		const measure = () => {
			const cell = node.querySelector(".hour-band__apps");
			const width = cell ? cell.clientWidth : 0;
			setCapacity(width ? Math.max(1, Math.floor((width - MORE_SLOT) / ICON_SLOT)) : CAPACITY_FALLBACK);
		};
		measure();
		const observer = new ResizeObserver(measure);
		observer.observe(node);
		return () => observer.disconnect();
	}, []);
	(0, import_react.useEffect)(() => () => hide(), []);
	if (gap) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "hour-band",
		ref: root,
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "hour-band__gap",
			children: "该时段没有采集记录（不是 0）"
		})
	});
	const byHour = new Map((hours || []).map((item) => [item.hour, item]));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "hour-band",
		ref: root,
		onPointerLeave: () => hide(),
		children: HOURS.map((hour) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HourRow, {
			item: byHour.get(hour) || {
				hour,
				total_seconds: 0,
				apps: [],
				other_seconds: 0
			},
			capacity,
			categories
		}, hour))
	});
}
function HourRow({ item, capacity, categories }) {
	const list = [...item.apps || []].sort((left, right) => num(right.seconds) - num(left.seconds));
	const visible = list.slice(0, capacity);
	const hiddenCount = Math.max(0, list.length - visible.length);
	const otherSeconds = num(item.other_seconds);
	const moreCount = hiddenCount + (otherSeconds > 0 ? 1 : 0);
	const moreSeconds = list.slice(capacity).reduce((sum, app) => sum + num(app.seconds), 0) + otherSeconds;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "hour-band__row",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
			className: "hour-band__hour",
			children: [String(item.hour).padStart(2, "0"), ":00"]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "hour-band__apps",
			children: [visible.map((app) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(IconCell, {
				app,
				hour: item.hour,
				category: categories?.get(app.app_id)
			}, app.app_id)), moreCount ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "hour-band__more",
				onPointerEnter: (event) => show({
					title: `另外 ${moreCount} 个应用`,
					rows: [["时长", formatDurationShort(moreSeconds)]],
					x: event.clientX,
					y: event.clientY
				}),
				children: ["+", moreCount]
			}) : null]
		})]
	});
}
/** 图标取不到就是首字母块——`icons` 能力缺失的机器上这是常态，不是异常。 */
function IconCell({ app, hour, category }) {
	const [broken, setBroken] = (0, import_react.useState)(false);
	const label = app.display_name || `应用 ${app.app_id}`;
	const duration = formatDurationShort(num(app.seconds));
	const url = app.icon_url ? assetUrl(app.icon_url) : "";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "hour-band__app",
		"data-app-id": app.app_id,
		"data-category": category,
		"aria-label": `${String(hour).padStart(2, "0")}:00 ${label} ${duration}`,
		onPointerEnter: (event) => show({
			title: label,
			rows: [["时长", duration], ["占这一小时", formatPercent(num(app.percent))]],
			x: event.clientX,
			y: event.clientY
		}),
		children: !url || broken ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "hour-band__initial",
			children: initialOf(label)
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", {
			className: "hour-band__icon",
			src: url,
			alt: "",
			loading: "lazy",
			decoding: "async",
			onError: () => setBroken(true)
		})
	});
}
//#endregion
//#region frontend/src/components/UsageList.tsx
function UsageList({ apps, maxSeconds, split = false, empty = null }) {
	const classes = ["usage-list"];
	if (split) classes.push("usage-list--split");
	const top = maxSeconds ?? Math.max(1, ...apps.map((app) => app.seconds || 0));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: classes.join(" "),
		children: apps.length ? apps.map((app) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Row, {
			app,
			top
		}, app.app_id)) : empty
	});
}
function Row({ app, top }) {
	const name = app.user_alias || app.display_name || app.process_name;
	const width = top > 0 ? Math.max(3, Math.round((app.seconds || 0) / top * 100)) : 0;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "usage-row",
		"data-category": app.category || "uncategorized",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Mark, {
				app,
				name
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "usage-row__main",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "usage-row__title",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "usage-row__name",
						title: name,
						children: name
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("small", {
						className: "usage-row__value",
						children: app.seconds_formatted
					})]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "usage-row__track",
					title: `${(app.percent || 0).toFixed(1)}%`,
					role: "img",
					"aria-label": `${name}：${app.seconds_formatted}，占 ${(app.percent || 0).toFixed(1)}%`,
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "usage-row__fill",
						style: { width: `${width}%` }
					})
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "usage-row__tail",
				children: app.is_running ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {
					className: "usage-row__running",
					title: "正在运行",
					"aria-label": "正在运行"
				}) : null
			})
		]
	});
}
/** 图标取不到就是首字母块——204 而不是 404 的那条路径（05 文档 §6）。 */
function Mark({ app, name }) {
	const [broken, setBroken] = (0, import_react.useState)(false);
	const url = app.icon_url ? assetUrl(app.icon_url) : "";
	if (!url || broken) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "usage-row__initial",
		children: initialOf(name)
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", {
		className: "usage-row__icon",
		src: url,
		alt: "",
		loading: "lazy",
		decoding: "async",
		onError: () => setBroken(true)
	});
}
//#endregion
//#region frontend/src/views/overview.tsx
var title = "总览";
function needs(state) {
	const period = periodParams(state.period);
	return [{
		key: "overviewAll",
		path: "/usage/period",
		params: {
			...period,
			limit: 200
		}
	}, {
		key: "overviewTimeline",
		path: "/usage/timeline",
		params: {
			...period,
			top: 20
		}
	}];
}
/** 重取当前周期：把 period 原样写回去，触发 main 的取数订阅。 */
function reload() {
	setState("period", { ...getState().period });
}
function View() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
		className: "view__title sr-only",
		tabIndex: -1,
		id: "view-title",
		children: "总览"
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "overview",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Section, {
			title: "每小时使用",
			right: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Updated, {}),
			lead: true,
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Hourly, {})
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Section, {
			title: "所有使用",
			right: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AllCount, {}),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AllUsage, {})
		})]
	})] });
}
/** 段标题右侧那行小字：应用数与合计时长。前身在这里放的是日期，我们已经有周期带了。 */
function AllCount() {
	const { data } = useResource("overviewAll");
	if (!data) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
		className: "updated",
		children: [
			data.app_count,
			" 个应用，合计 ",
			data.total_seconds_formatted
		]
	});
}
function AllUsage() {
	const { data, loading, error } = useResource("overviewAll");
	if (error) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "usage-list",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorState, {
			message: error.message,
			onRetry: reload
		})
	});
	if (!data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "usage-list",
		children: loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 6 }) : null
	});
	const apps = data.apps || [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(UsageList, {
		apps,
		split: true,
		empty: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
			title: "这段时间没有使用记录",
			detail: "换一个日期，或确认采集正在运行"
		})
	});
}
/**
* 每小时图标带。24 行 ×（小时 + 那一小时用过的应用图标），前身 TimeLens 的
* `.hourly-icon-list`——它回答的是"那个小时我在干什么"，而柱状图只回答"多久"。
*
* 类别表从「所有使用」那一份列表里现取（`/usage/period` 的行带 `category`）：小时行
* 本身不带类别，而首字母兜底块要与那张列表同色，否则同一个应用会在两处长得不一样。
*/
function Hourly() {
	const { data, loading } = useResource("overviewTimeline");
	const { data: all } = useResource("overviewAll");
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	const categories = (0, import_react.useMemo)(() => new Map((all?.apps || []).map((app) => [app.app_id, app.category])), [all]);
	if (!capabilityOf(capabilities, "foreground")) {
		const notice = noticeFor(degraded, "foreground");
		return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "hour-band",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityNotice, {
				title: notice?.title || "当前环境不支持识别前台应用",
				detail: notice?.detail || "键盘统计不受影响，但无法按应用拆分时长。",
				hint: notice?.hint || ""
			})
		});
	}
	if (!data) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 6 }) : null;
	const hours = data.hours || [];
	if (!hours.some((hour) => (hour.total_seconds || 0) > 0)) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "hour-band",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
			title: "这段时间没有小时级记录",
			detail: "把范围切到「每天」时这一块最有用：它按小时列出那一刻在用的应用"
		})
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HourBand, {
		hours,
		categories
	});
}
//#endregion
export { View, needs, title };
