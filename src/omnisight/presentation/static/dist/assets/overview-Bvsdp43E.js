import { A as formatPercent, B as capabilityOf, D as formatDelta, G as setState, H as useResource, K as Icon, O as formatDuration, T as formatCount, U as useSlice, V as noticeFor, W as getState, Y as require_react, h as periodParams, l as Segmented, m as gapSet, q as require_jsx_runtime } from "./main-DA_wrxiB.js";
import { t as AppRow } from "./AppRow-BMX9Ac2T.js";
import { a as Skeleton, i as GapLegend, n as EmptyState, o as SkeletonRows, r as ErrorState, s as Card, t as CapabilityNotice } from "./states-DZ-0dhHV.js";
import { a as Chart, i as showChartTooltip, n as drawPanelPair, r as hideChartTooltip, t as describePanelPair } from "./panel-pair-ZeqsPmhE.js";
import { n as stackByCategory, t as markGaps } from "./buckets-Vq47HwJd.js";
//#region frontend/src/components/Highlights.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
function Highlights({ items }) {
	const list = items || [];
	if (!list.length) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "dim text-sm",
		children: "数据还不够多，暂时得不出结论"
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: list.map((item, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
		className: "highlight",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("summary", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "highlight__mark",
				"aria-hidden": "true",
				children: "◈"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: item.text }),
			item.basis ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "highlight__toggle",
				"aria-hidden": "true",
				children: "口径"
			}) : null
		] }), item.basis ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "highlight__basis",
			children: ["口径：", item.basis]
		}) : null]
	}, `${index}-${item.text}`)) });
}
//#endregion
//#region frontend/src/components/StackBar.tsx
function StackBar({ segments, label = "构成", onSelect = null }) {
	const items = (segments || []).filter((item) => (Number(item.percent) || 0) > 0);
	const summary = items.length ? `${label}：${items.map((item) => `${item.name} ${formatPercent(item.percent)}`).join("，")}` : `${label}：暂无数据`;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: onSelect ? "stackbar stackbar--clickable" : "stackbar",
		role: "img",
		"aria-label": summary,
		onClick: onSelect ? (event) => {
			const id = event.target.closest(".stackbar__seg")?.dataset.id;
			if (id) onSelect(id);
		} : void 0,
		children: items.map((item) => {
			const percent = Number(item.percent) || 0;
			return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "stackbar__seg",
				"data-category": item.id,
				"data-id": item.id,
				style: { flexGrow: percent },
				title: `${item.name}：${item.formatted ?? ""}（${formatPercent(percent)}）`,
				children: percent >= 9 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "stackbar__label",
					children: item.name
				}) : null
			}, item.id);
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "sr-only",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("caption", { children: label }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "类别" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "占比" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "数值" })
			] }) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: items.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: item.name ?? "" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: formatPercent(item.percent) }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: item.formatted ?? "" })
			] }, item.id)) })
		] })
	})] });
}
//#endregion
//#region frontend/src/charts/context-bars.ts
var PAD = {
	top: 4,
	right: 2,
	bottom: 2,
	left: 2
};
/** 柱宽上限（14 文档 §5.1 的记号规格给的是 ≤24px）。 */
var BAR_MAX = 20;
/** 绘制函数工厂。`Chart` 只接受 `(ctx, box, data, palette)`，选项在这里闭包进去。 */
function contextBarsDraw(options = {}) {
	const { accent = "time", metric = "seconds" } = options;
	return (ctx, box, data, colors) => draw(ctx, box, data, colors, accent, metric);
}
function contextBarsDescribe(options = {}) {
	const { metric = "seconds", format = String, label = "" } = options;
	return (data) => {
		const buckets = data?.buckets || [];
		if (!buckets.length) return null;
		return {
			caption: label || "对照条",
			columns: [
				"时间",
				metric === "presses" ? "按键" : "时长",
				""
			],
			rows: buckets.map((item) => [
				String(item.label ?? item.bucket ?? ""),
				format(Number(item[metric]) || 0),
				item.bucket === data.current ? "当前" : ""
			])
		};
	};
}
function draw(ctx, box, data, colors, accent, metric) {
	const buckets = data.buckets || [];
	if (!buckets.length) return;
	const values = buckets.map((item) => Number(item[metric]) || 0);
	const top = Math.max(...values);
	const plot = {
		x: PAD.left,
		y: PAD.top,
		w: Math.max(1, box.width - PAD.left - PAD.right),
		h: Math.max(1, box.height - PAD.top - PAD.bottom)
	};
	const slot = plot.w / buckets.length;
	const width = Math.max(2, Math.min(slot - 3, BAR_MAX));
	const emphasis = accent === "keys" ? colors.keys : colors.time;
	const quiet = colors.categories.uncategorized;
	buckets.forEach((item, index) => {
		const value = values[index];
		const centre = plot.x + slot * (index + .5);
		const x = centre - width / 2;
		box.hits.push({
			x: centre - slot / 2,
			y: plot.y,
			w: slot,
			h: plot.h,
			payload: item
		});
		const current = item.bucket === data.current;
		const barHeight = top > 0 ? Math.max(value > 0 ? 3 : 2, value / top * plot.h) : 2;
		ctx.fillStyle = current ? emphasis : quiet;
		ctx.globalAlpha = current ? 1 : .5;
		ctx.beginPath();
		ctx.roundRect(x, plot.y + plot.h - barHeight, width, barHeight, Math.min(2, width / 2));
		ctx.fill();
		ctx.globalAlpha = 1;
	});
}
//#endregion
//#region frontend/src/components/StatCard.tsx
function StatCard({ label, hint = "", hero = false, series = "time", metric = "seconds", format = String, text = "—", loading = false, delta = null, context = null, footnote = "", onHover = null, onLeave = null }) {
	const buckets = context?.buckets || [];
	const chartData = {
		buckets,
		current: context?.current || ""
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "card card--keycap metric",
		"data-hero": hero ? "true" : void 0,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "metric__label",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label }),
					hint ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "card__hint",
						title: hint,
						"aria-label": hint,
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "info" })
					}) : null,
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "metric__delta numeric",
						children: !loading && delta ? formatDelta(delta) : ""
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "metric__context",
				hidden: loading || buckets.length === 0,
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chart, {
					data: chartData,
					draw: contextBarsDraw({
						accent: series,
						metric
					}),
					describe: contextBarsDescribe({
						metric,
						format,
						label: `${label}对照条`
					}),
					height: 36,
					label: `${label}对照条`,
					onHover,
					onLeave
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "metric__value",
				children: loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Skeleton, { kind: "value" }) : text
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "metric__foot",
				children: loading ? "" : footnote
			})
		]
	});
}
//#endregion
//#region frontend/src/views/overview.tsx
var title = "总览";
function needs(state) {
	const period = periodParams(state.period);
	return [{
		key: "overview",
		path: "/overview",
		params: period
	}, {
		key: "overviewIntensity",
		path: "/insights/app-keyboard",
		params: {
			...period,
			limit: 8
		}
	}];
}
var TIMELINE_MODES = [
	{
		id: "both",
		name: "并排"
	},
	{
		id: "seconds",
		name: "时长"
	},
	{
		id: "presses",
		name: "按键"
	},
	{
		id: "kpm",
		name: "强度"
	}
];
var GRAIN_NAMES = {
	hour: "小时",
	day: "天",
	month: "月",
	year: "年"
};
/** 重取当前周期：把 period 原样写回去，触发 main 的取数订阅。 */
function reload() {
	setState("period", { ...getState().period });
}
function View() {
	const [mode, setMode] = (0, import_react.useState)("both");
	const { data: overview, loading, error } = useResource("overview");
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
			className: "view__title sr-only",
			tabIndex: -1,
			id: "view-title",
			children: "总览"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Timeline, {
			overview,
			mode,
			onMode: setMode
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "overview__pair",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metrics, {
				overview,
				loading
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "构成",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "overview__stacks",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "overview__stack-label",
					children: "时间去了哪些类别"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Categories, { overview })] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "overview__stack-label",
					children: "其中多少是在真的输入"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Intensity, {})] })]
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "最常使用",
			controls: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "card__link",
				type: "button",
				"data-action": "route:go",
				"data-route": "apps",
				children: "查看全部"
			}),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "app-list",
				children: error ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorState, {
					message: error.message,
					onRetry: reload
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TopApps, {
					overview,
					loading
				})
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "结论",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "highlights",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Highlights, { items: overview?.highlights })
			})
		})
	] });
}
function Metrics({ overview, loading }) {
	const time = overview?.screen_time;
	const keys = overview?.keyboard;
	const context = overview?.context || null;
	const pending = !overview && loading;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatCard, {
		label: "屏幕时间",
		hint: "前台应用的累计时长，已扣除空闲",
		hero: true,
		series: "time",
		metric: "seconds",
		format: formatDuration,
		loading: pending,
		text: time?.total_formatted || formatDuration(time?.total_seconds || 0),
		delta: time?.delta_vs_previous,
		context,
		footnote: `${time?.app_count || 0} 个应用，日均 ${formatDuration(time?.daily_average_seconds || 0)}`,
		onHover: showChartTooltip,
		onLeave: hideChartTooltip
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatCard, {
		label: "按键",
		hint: "按键次数。不记录按了什么内容",
		series: "keys",
		metric: "presses",
		format: (value) => `${formatCount(value)} 次`,
		loading: pending,
		text: `${formatCount(keys?.total_presses || 0)} 次`,
		delta: keys?.delta_vs_previous,
		context,
		footnote: `${keys?.active_keys || 0} 个活跃键，峰值 ${formatCount(keys?.kpm_peak || 0)} KPM`,
		onHover: showChartTooltip,
		onLeave: hideChartTooltip
	})] });
}
function Timeline({ overview, mode, onMode }) {
	const coverage = useSlice("coverage");
	const trend = overview?.trend;
	const granularity = trend?.granularity || "hour";
	const gaps = gapSet(coverage, ["foreground", "keyboard"]);
	const buckets = markGaps(stackByCategory(trend?.buckets, overview?.categories), granularity, gaps, overview?.period);
	const data = {
		buckets,
		mode,
		caption: "活动带",
		summary: `${overview?.period?.label || ""}，共 ${buckets.length} 个时间桶`
	};
	const grain = GRAIN_NAMES[granularity] || "时间";
	const categories = (overview?.categories || []).filter((item) => (item.seconds || 0) > 0);
	const showTime = mode === "both" || mode === "seconds";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
		title: "活动带",
		controls: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
			items: TIMELINE_MODES,
			active: mode,
			onPick: (id) => onMode(id),
			small: true,
			label: "活动带指标"
		}),
		footer: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: [
				overview?.period?.days || 0,
				" 天，按",
				grain,
				"聚合"
			]
		}),
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "chart chart--tall",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chart, {
					data: overview ? data : null,
					draw: drawPanelPair,
					describe: describePanelPair,
					height: 220,
					label: "活动带",
					onHover: showChartTooltip,
					onLeave: hideChartTooltip
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "chart__legend",
				children: [
					showTime && categories.length ? categories.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
						className: "chart__legend-item",
						"data-category": item.id,
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: item.name })]
					}, item.id)) : null,
					showTime && !categories.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
						className: "chart__legend-item",
						"data-series": "time",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "屏幕时间" })]
					}) : null,
					mode === "both" || mode === "presses" || mode === "kpm" ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
						className: "chart__legend-item",
						"data-series": "keys",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: mode === "kpm" ? "输入强度 KPM" : "按键" })]
					}) : null
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(GapLegend, { count: gaps.size }) })
		] })
	});
}
function CategoryRow({ item, percent, kind = "category" }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "category-row",
		"data-category": kind === "category" ? item.id : void 0,
		"data-profile": kind === "profile" ? item.id : void 0,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "swatch",
				"aria-hidden": "true"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "truncate",
				children: item.name
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "category-row__percent",
				children: formatPercent(percent)
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "category-row__value",
				children: item.seconds_formatted
			})
		]
	});
}
function Categories({ overview }) {
	const categories = overview?.categories || [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StackBar, {
		label: "类别构成",
		segments: categories.map((item) => ({
			id: item.id,
			name: item.name,
			percent: item.percent,
			formatted: item.seconds_formatted
		}))
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "category-list",
		children: [categories.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CategoryRow, {
			item,
			percent: item.percent
		}, item.id)), categories.length ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
			title: "这段时间没有应用记录",
			detail: "换一个日期，或确认采集正在运行"
		})]
	})] });
}
function TopApps({ overview, loading }) {
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	if (!overview) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 4 }) : null;
	if (!capabilityOf(capabilities, "foreground")) {
		const notice = noticeFor(degraded, "foreground");
		return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityNotice, {
			title: notice?.title || "当前环境不支持识别前台应用",
			detail: notice?.detail || "键盘统计不受影响，但无法按应用拆分时长。",
			hint: notice?.hint || ""
		});
	}
	const apps = overview.top_apps || [];
	if (!apps.length) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
		title: "这段时间没有使用记录",
		detail: "把范围切到全部即可查看历史数据"
	});
	const maxSeconds = Math.max(...apps.map((app) => app.seconds || 0));
	const maxKpm = Math.max(...apps.map((app) => app.kpm || 0));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: apps.slice(0, 6).map((app) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppRow, {
		app,
		maxSeconds,
		maxKpm
	}, app.app_id)) });
}
function Intensity() {
	const { data: payload, loading } = useResource("overviewIntensity");
	if (!payload) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 }) : null;
	const distribution = payload.distribution;
	const buckets = distribution?.buckets || [];
	const total = Number(distribution?.total_seconds) || 0;
	const share = (seconds) => total ? (seconds || 0) / total * 100 : 0;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StackBar, {
		label: "输入强度构成",
		segments: buckets.map((item) => ({
			id: item.id,
			name: item.name,
			percent: share(item.seconds),
			formatted: item.seconds_formatted
		}))
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "category-list",
		children: [buckets.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CategoryRow, {
			item,
			percent: share(item.seconds),
			kind: "profile"
		}, item.id)), payload.unattributed_presses ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: [
				"另有 ",
				formatCount(payload.unattributed_presses),
				" 次按键没有应用归因"
			]
		}) : null]
	})] });
}
//#endregion
export { View, needs, title };
