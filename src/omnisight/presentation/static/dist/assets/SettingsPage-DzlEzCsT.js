import { A as ok, B as tokenParam, C as useSlice, E as setState, F as get, H as on, K as require_react, L as messageOf, R as patch, U as Icon, V as emit, W as require_jsx_runtime, c as set, k as fail, l as setHeat, z as post } from "./degraded-mkfLsXii.js";
import { s as pageUrl } from "./shell-B5wD9e0n.js";
import { a as Switch, s as openImportWizard } from "./controls-CgVt8_vH.js";
import { t as Card } from "./Card-CxjL8c3d.js";
//#region frontend/src/pages/settings-fields.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
var LABELS = {
	"ui.theme": "主题",
	"ui.heat": "热力色",
	"ui.default_view": "默认周期",
	"ui.keyboard_layout": "键盘布局",
	"ui.week_starts_on": "周起始日",
	"ui.timezone": "时区",
	"ui.locale": "语言",
	"ui.shell": "外壳",
	"ui.settings_surface": "设置打开方式",
	"capture.paused": "暂停采集",
	"capture.idle_threshold_seconds": "空闲阈值（秒）",
	"capture.foreground_poll_seconds": "前台轮询间隔（秒）",
	"capture.session_flush_seconds": "会话落盘间隔（秒）",
	"capture.keyboard_backend": "键盘后端",
	"capture.store_raw_key_events": "保存原始按键事件",
	"privacy.record_window_titles": "记录窗口标题",
	"privacy.realtime_stream": "实时按键流",
	"privacy.excluded_processes": "排除的进程",
	"storage.data_dir": "数据目录",
	"storage.raw_event_retention_days": "原始事件保留天数",
	"storage.checkpoint_interval_seconds": "WAL 检查点间隔（秒）",
	"server.port": "端口",
	"system.autostart": "开机自启",
	"system.autostart_elevated": "登录时以管理员身份启动"
};
var OPTION_LABELS = {
	system: "跟随系统",
	light: "浅色",
	dark: "深色",
	blue: "蓝色",
	warm: "暖色",
	daily: "日",
	weekly: "周",
	monthly: "月",
	yearly: "年",
	total: "全部",
	auto: "自动",
	none: "关闭",
	raw_input: "Raw Input",
	pynput: "pynput",
	ansi104: "ANSI 104",
	iso105: "ISO 105",
	browser: "浏览器",
	drawer: "侧边抽屉",
	page: "独立页面",
	"zh-CN": "中文（简体）"
};
var HINTS = {
	"capture.store_raw_key_events": "关闭后无法按应用查看键盘热力图，也无法重算历史聚合",
	"privacy.record_window_titles": "标题是最敏感的一档数据，默认关闭。接口默认也不下发",
	"privacy.realtime_stream": "关闭后键盘视图没有实时按压动画，改为 30 秒轮询",
	"ui.heat": "键盘热力图与日历格子的色阶。写入配置，因此换浏览器也一致"
};
function labelOf(key) {
	return LABELS[key] || key;
}
function optionLabel(value, effective) {
	const text = String(value ?? "");
	if (text === "") return effective ? `跟随系统（${effective}）` : "跟随系统";
	return OPTION_LABELS[text] || text;
}
/**
* 把 `Asia/Shanghai` 这类选项按第一段分组。不带 `/` 的留在最前面（`""`、`UTC`）。
*
* 600 条时区平铺在一个下拉里找不动；分了组之后与系统设置里那个时区选择器读起来一样。
* 普通枚举（主题、周起始日）没有 `/`，因此全部落在 `plain` 里——它们的渲染一行没变。
*/
function groupOptions(options) {
	const plain = [];
	const groups = /* @__PURE__ */ new Map();
	for (const option of options) {
		const text = String(option ?? "");
		const slash = text.indexOf("/");
		if (slash <= 0) {
			plain.push(text);
			continue;
		}
		const region = text.slice(0, slash);
		const bucket = groups.get(region);
		if (bucket) bucket.push(text);
		else groups.set(region, [text]);
	}
	return {
		plain,
		groups: [...groups]
	};
}
/** 一行设置。控件类型完全由 spec.kind 决定。 */
function Field({ settingKey, spec, onChange }) {
	const note = spec.unavailable_reason || spec.note || HINTS[settingKey] || "";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		"data-available": String(spec.available !== false),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "field__label",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: labelOf(settingKey) }), spec.applies === "restart" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "field__tag",
					children: "需重启"
				}) : null]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Control, {
				settingKey,
				spec,
				onChange
			}),
			note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: note
			}) : null
		]
	});
}
function Control({ settingKey, spec, onChange }) {
	const disabled = spec.available === false;
	const label = labelOf(settingKey);
	if (spec.kind === "bool") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
		checked: Boolean(spec.value),
		disabled,
		label,
		onChange: (value) => onChange(settingKey, value)
	});
	if (spec.options) {
		const { plain, groups } = groupOptions(spec.options);
		return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
			className: "control",
			disabled,
			"aria-label": label,
			value: String(spec.value ?? ""),
			onChange: (event) => onChange(settingKey, event.target.value),
			children: [plain.map((option) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
				value: option,
				children: optionLabel(option, spec.effective)
			}, option || "__auto__")), groups.map(([region, items]) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("optgroup", {
				label: region,
				children: items.map((option) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
					value: option,
					children: option
				}, option))
			}, region))]
		});
	}
	if (spec.kind === "int" || spec.kind === "number") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
		className: "control",
		type: "number",
		defaultValue: spec.value === null || spec.value === void 0 ? "" : String(spec.value),
		disabled,
		"aria-label": label,
		min: spec.min === void 0 ? void 0 : String(spec.min),
		max: spec.max === void 0 ? void 0 : String(spec.max),
		step: spec.kind === "int" ? "1" : "any",
		onChange: (event) => {
			const raw = event.target.value;
			const value = spec.kind === "int" ? Number.parseInt(raw, 10) : Number.parseFloat(raw);
			if (Number.isNaN(value)) return;
			onChange(settingKey, value);
		}
	});
	if (spec.kind === "list") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
		className: "control",
		type: "text",
		defaultValue: Array.isArray(spec.value) ? spec.value.join(", ") : "",
		disabled,
		"aria-label": label,
		placeholder: "用逗号分隔",
		onBlur: (event) => onChange(settingKey, event.target.value.split(",").map((item) => item.trim()).filter(Boolean))
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
		className: "control",
		type: "text",
		defaultValue: spec.value === null || spec.value === void 0 ? "" : String(spec.value),
		disabled,
		"aria-label": label,
		onBlur: (event) => onChange(settingKey, event.target.value.trim() || null)
	});
}
/** 暂停走专用端点：它除了写配置还要真的停掉采集线程（05 文档 §7）。 */
function PauseField({ spec }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__label",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "暂停采集" })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
				checked: Boolean(spec.value),
				label: "暂停采集",
				onChange: async (value) => {
					try {
						const result = await post("/capture/pause", { paused: value });
						ok(result.paused ? "采集已暂停" : "采集已恢复");
					} catch (error) {
						fail(messageOf(error));
					}
				}
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: "暂停期间不记录任何按键与前台时长。本次运行不会自动恢复。托盘菜单里那一项是同一条路径。"
			})
		]
	});
}
/**
* 走专用端点的开关：开机自启要写注册表、「登录时以管理员身份启动」要建计划任务
* （10 文档 §5.3），能力缺失时后端返回 422（不是"设置失败"）。
*
* **这两项的真源是操作系统，不是 config.json**（注册表项 / 登录计划任务）。写进配置文件
* 就会立刻有两份真相——"配置说开着、注册表里没有"，而 10 文档 §4 有一条不可退让的要求：
* 任何一条机制开着时，界面都不许显示"开机自启：关"。因此它们留在这里而不是进配置。
* 18 批 4 起托盘里那个勾选框撤掉了，这里是它唯一的落脚处。
*
* 不可用的原因**一定要显示**：提权那个开关多数时候是灰的（要装到 Program Files、
* 要先提权），而三种原因对应三种完全不同的下一步动作。
*/
function ActionToggle({ settingKey, spec, path, onReload }) {
	const label = labelOf(settingKey);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		"data-available": String(spec.available !== false),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__label",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
				checked: Boolean(spec.value),
				disabled: spec.available === false,
				label,
				onChange: async (value) => {
					try {
						const result = await post(path, { enabled: value });
						ok([result.enabled ? `已开启${label}` : `已关闭${label}`, result.note].filter(Boolean).join("；"));
					} catch (error) {
						fail(messageOf(error));
					}
					onReload();
				}
			}),
			spec.unavailable_reason ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: spec.unavailable_reason
			}) : null,
			spec.note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: spec.note
			}) : null
		]
	});
}
/**
* 一行"动作"：左边是名字，控件位上是一个图标钮（18 文档 批 7）。
*
* 这些动作原先是一排文字按钮挤在卡片底部。一排按钮读起来是"这张卡的操作"，而它们其实与上面
* 那些一行一项是同一类东西——一个名字、一个控件。名字回到标签列之后还顺带解决了按钮宽度：
* 「导出使用记录 CSV」这种长度的按钮怎么排都排不齐，而标签列天然对齐。
*
* 图标钮一律带 `aria-label`：控件位上没有文字，屏幕阅读器读不到左边那一列。
*/
function ActionField({ label, icon, note, href, download = false, onClick }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__label",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label })
			}),
			href ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
				className: "icon-button",
				href,
				"aria-label": label,
				download: download ? "" : void 0,
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: icon })
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "icon-button",
				type: "button",
				"aria-label": label,
				onClick,
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: icon })
			}),
			note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: note
			}) : null
		]
	});
}
/**
* 名单类设置（当前只有「排除的进程」）：**标签 + 一个输入框**，不是一行逗号分隔的长文本。
*
* 逗号分隔那种写法的三个毛病都只在真的去用的时候才发现：改一项要先把整行读懂、删一项要连着
* 一个逗号一起删干净、而"要不要写 .exe"没有任何提示。标签形态里每一项自带一个删除位，新增
* 敲回车，占位符里就写着一个例子（18 文档 批 7）。
*
* 粘贴一串也认：空白、半角与全角逗号都当分隔符——用户手里那份名单多半就是这种形状。
*/
function TagsField({ settingKey, spec, onChange }) {
	const values = Array.isArray(spec.value) ? spec.value.map(String) : [];
	const [draft, setDraft] = (0, import_react.useState)("");
	const disabled = spec.available === false;
	const label = labelOf(settingKey);
	const commit = (text) => {
		const additions = text.split(/[,，;；\s]+/).map((item) => item.trim()).filter(Boolean);
		setDraft("");
		if (!additions.length) return;
		const merged = [...values];
		for (const item of additions) if (!merged.some((existing) => existing.toLowerCase() === item.toLowerCase())) merged.push(item);
		if (merged.length !== values.length) onChange(settingKey, merged);
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field field--stack",
		"data-available": String(!disabled),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "field__label",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label }), spec.applies === "restart" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "field__tag",
					children: "需重启"
				}) : null]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "tag-input",
				"data-empty": values.length ? void 0 : "true",
				children: [values.map((value) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "tag",
					children: [value, /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						className: "tag__remove",
						type: "button",
						"aria-label": `不再排除 ${value}`,
						disabled,
						onClick: () => onChange(settingKey, values.filter((item) => item !== value)),
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "close" })
					})]
				}, value)), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
					className: "tag-input__field",
					type: "text",
					value: draft,
					disabled,
					"aria-label": `添加${label}`,
					placeholder: values.length ? "再加一个…" : "输入进程名后回车，例如 KeePass.exe",
					onChange: (event) => setDraft(event.target.value),
					onKeyDown: (event) => {
						if (event.key === "Enter" || event.key === "," || event.key === "，") {
							event.preventDefault();
							commit(draft);
							return;
						}
						if (event.key === "Backspace" && !draft && values.length) {
							event.preventDefault();
							onChange(settingKey, values.slice(0, -1));
						}
					},
					onBlur: () => commit(draft)
				})]
			}),
			spec.note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: spec.note
			}) : null,
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: "名单里的进程完全不被采集：既不记按键，也不记前台时长。改动立即生效。"
			})
		]
	});
}
/**
* 路径项（当前只有「数据目录」）。与普通输入框有两处不同，都来自同一个事实：**这一项留空
* 表示"按平台惯例解析"**（18 文档 批 7）。
*
* 1. 留空时输入框原先是空的——而来看这一项的人要问的恰恰是"数据现在落在哪儿"。后端给了
*    `effective`，这里把它放进 placeholder，并在说明行里再写一遍：placeholder 在 200px 的
*    控件里一定会被截断，而路径的关键部分在末尾。
* 2. 旁边直接给一个打开那个目录的按钮——否则用户得先把路径读出来，再自己去文件管理器里找。
*/
function PathField({ settingKey, spec, onChange, onReveal }) {
	const label = labelOf(settingKey);
	const disabled = spec.available === false;
	const configured = spec.value === null || spec.value === void 0 ? "" : String(spec.value);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		"data-available": String(!disabled),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "field__label",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label }), spec.applies === "restart" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "field__tag",
					children: "需重启"
				}) : null]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "control-row",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
					className: "control",
					type: "text",
					defaultValue: configured,
					disabled,
					"aria-label": label,
					placeholder: spec.effective || "",
					onBlur: (event) => {
						const next = event.target.value.trim();
						if (next !== configured) onChange(settingKey, next || null);
					}
				}), onReveal ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					className: "icon-button",
					type: "button",
					"aria-label": `打开${label}`,
					onClick: onReveal,
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "folder" })
				}) : null]
			}),
			spec.note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: spec.note
			}) : null,
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "field__note",
				children: [configured ? "当前使用：" : "留空表示按平台惯例解析。当前使用：", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "mono",
					children: spec.effective || "-"
				})]
			})
		]
	});
}
//#endregion
//#region frontend/src/pages/settings-sections.tsx
/** 能力名的中文。`capabilities` 只读布尔值，这里只是给它们起个名字。 */
var CAPABILITY_NAMES = {
	keyboard: "键盘采集",
	foreground: "应用归因",
	window_titles: "窗口标题",
	idle: "空闲检测",
	icons: "应用图标",
	autostart: "开机自启",
	tray: "托盘图标",
	keyboard_durations: "按压时长",
	key_position_stable: "左右键位可分"
};
/**
* 导出用普通链接而不是 fetch：响应是流式的附件，交给浏览器下载最省事。
* 令牌走查询串（下载请求带不了自定义头，与图标同一个理由）。
*
* **范围固定 `total`**：设置页没有周期栏，而"从设置页导出"的合理默认是全部数据。原先它
* 长在抽屉里，能读到仪表盘当前那个周期；独立成页之后那个上下文不存在了，继续读 store 里
* 的默认值等于悄悄只导出了今天。
*/
function exportHref(scope, format) {
	return `/api/v1/export?${new URLSearchParams({
		scope,
		format,
		range: "total"
	}).toString()}&token=${encodeURIComponent(tokenParam())}`;
}
/**
* 打开数据目录 / 日志目录。**只有后端做得到**：浏览器里的页面开不了文件管理器，而"管理员
* 模式下要降权打开"这件事本来就在后端（`lifecycle._open_external`）。托盘里那两项、以及
* 「数据目录」那一行旁边的按钮，走的都是这一条。
*/
async function revealDirectory(target) {
	try {
		await post("/system/reveal", { target });
	} catch (error) {
		fail(messageOf(error, "打开目录失败"));
	}
}
/** 数据与导出。备份、重算聚合与删除数据排在后续版本——**说明而不是画一个禁用按钮**。 */
function DataCard({ status }) {
	const database = status?.database;
	const range = status?.data_range;
	const size = database?.size_bytes ? `${(database.size_bytes / 1048576).toFixed(1)} MB` : "-";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
		title: "数据与导出",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
				className: "kv-list",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "数据库" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: size }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "数据范围" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: range?.min_date ? `${range.min_date} 至 ${range.max_date}` : "暂无数据" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "schema" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: String(database?.schema_version || "-") }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "数据库文件" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", {
						className: "mono",
						children: database?.path || "-"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionField, {
				label: "导出使用记录 CSV",
				icon: "download",
				href: exportHref("usage", "csv"),
				download: true
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionField, {
				label: "导出键盘统计 CSV",
				icon: "download",
				href: exportHref("keyboard", "csv"),
				download: true
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionField, {
				label: "导出全部 JSON",
				icon: "download",
				href: exportHref("all", "json"),
				download: true
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionField, {
				label: "打开数据目录",
				icon: "folder",
				onClick: () => void revealDirectory("data")
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionField, {
				label: "打开日志目录",
				icon: "logs",
				onClick: () => void revealDirectory("logs")
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionField, {
				label: "从旧版导入数据",
				icon: "import",
				note: "从 KeyTrace 或 TimeLens 的旧数据库导入历史记录",
				onClick: () => openImportWizard()
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: "备份、重算聚合与删除数据排在后续版本。"
			})
		]
	});
}
/** 能力说明：所有 degraded 都在这里列全，横幅只上 error 一级。 */
function CapabilityCard() {
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	const read = capabilities;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
		title: "运行环境能力",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dl", {
			className: "kv-list",
			children: Object.entries(CAPABILITY_NAMES).map(([key, name]) => {
				if (!read || read[key] === void 0) return null;
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					style: { display: "contents" },
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: name }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: read[key] ? "可用" : "不可用" })]
				}, key);
			})
		}), (degraded || []).map((notice) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "notice",
			"data-severity": notice.severity,
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "notice__mark",
				"aria-hidden": "true",
				children: "i"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "notice__title",
					children: notice.title
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "notice__detail",
					children: notice.detail
				}),
				notice.hint ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "notice__hint",
					children: notice.hint
				}) : null
			] })]
		}, notice.code || notice.title))]
	});
}
/** 关于。详细的隐私说明在 `/about`——标题旁那个图标是去那一页的入口（18 文档 批 7）。 */
function AboutCard({ status, configPath }) {
	const platform = status?.platform;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
		title: "关于",
		titleAside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
			className: "icon-button",
			href: pageUrl("/about"),
			"aria-label": "关于与隐私说明",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "external" })
		}),
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
			className: "kv-list",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "版本" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: status?.version || "-" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "运行环境" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: `${platform?.id || "-"} ${platform?.os_version || ""}` }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "支持级别" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: platform?.tier ? `${platform.tier} 级` : "-" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "端口" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: String(status?.port || "-") }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "配置文件" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", {
					className: "mono",
					children: configPath || "-"
				})
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "field__note",
			children: "所有数据只保存在本机，不上传任何服务器。本程序不记录按键内容，只记录按了哪个键、多少次。"
		})]
	});
}
//#endregion
//#region frontend/src/pages/SettingsPage.tsx
var GROUPS = [
	{
		id: "appearance",
		title: "外观",
		prefixes: ["ui."]
	},
	{
		id: "capture",
		title: "采集",
		prefixes: ["capture."]
	},
	{
		id: "privacy",
		title: "隐私",
		prefixes: ["privacy."]
	},
	{
		id: "data",
		title: "数据",
		prefixes: ["storage."]
	},
	{
		id: "system",
		title: "系统",
		prefixes: ["server.", "system."]
	}
];
/** 页顶那句话。两档共用同一份措辞：说两遍就会有一天只改了一遍。 */
var LEAD = "改动即时保存；需重启的项会标出来，从托盘菜单重启后生效。";
function groupFromHash() {
	const id = window.location.hash.replace(/^#\/?/, "");
	return GROUPS.some((group) => group.id === id) ? id : GROUPS[0].id;
}
/** 取一次设置与状态。入口首屏与每次改动之后都走它。 */
async function loadSettings() {
	const [settings, status] = await Promise.all([get("/settings"), get("/status")]);
	setState("settings", settings);
	setState("status", status);
}
/** 重读表单。改完、被别处改了、以及一次失败的写入之后都走它。 */
function reload() {
	loadSettings().catch(() => fail("重读设置失败"));
}
function SettingsPage({ surface = "page" }) {
	const payload = useSlice("settings");
	const status = useSlice("status");
	const settings = payload?.settings || {};
	const onPage = surface === "page";
	const [group, setGroup] = (0, import_react.useState)(() => onPage ? groupFromHash() : GROUPS[0].id);
	const [pending, setPending] = (0, import_react.useState)([]);
	(0, import_react.useEffect)(() => {
		if (!onPage) return;
		const onHash = () => setGroup(groupFromHash());
		window.addEventListener("hashchange", onHash);
		return () => window.removeEventListener("hashchange", onHash);
	}, [onPage]);
	(0, import_react.useEffect)(() => on("settings:changed", reload), []);
	const pick = (id) => {
		if (onPage) history.replaceState(null, "", `#${id}`);
		setGroup(id);
	};
	const apply = (key, value) => {
		(async () => {
			try {
				const result = await patch("/settings", { settings: { [key]: value } });
				const rejected = (result.rejected || []).find((item) => item.key === key);
				if (rejected) {
					fail(`${labelOf(key)}：${rejected.message}`);
					reload();
					return;
				}
				const restart = (result.requires_restart || []).includes(key);
				ok(restart ? `${labelOf(key)} 已保存，重启后生效` : `${labelOf(key)} 已生效`);
				if (restart) setPending((keys) => keys.includes(key) ? keys : [...keys, key]);
				if (key === "ui.theme") set(String(value));
				if (key === "ui.heat") setHeat(String(value));
				emit("settings:changed", { key });
			} catch (error) {
				fail(messageOf(error));
				reload();
			}
		})();
	};
	const current = GROUPS.find((item) => item.id === group) || GROUPS[0];
	const keys = Object.keys(settings).filter((key) => current.prefixes.some((prefix) => key.startsWith(prefix))).sort();
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		pending.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RestartNotice, { keys: pending }) : null,
		onPage ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "section-heading section-heading--lead",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
				className: "section-title",
				id: "page-title",
				children: "设置"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "section-sub",
				children: LEAD
			})] })
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "section-sub",
			children: LEAD
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
			className: "viewbar settings-nav",
			role: "tablist",
			"aria-label": "设置分组",
			children: GROUPS.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "viewbar__tab",
				role: "tab",
				type: "button",
				"aria-selected": item.id === current.id,
				onClick: () => pick(item.id),
				children: item.title
			}, item.id))
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: current.title,
			children: keys.length ? keys.map((key) => {
				const spec = settings[key];
				if (key === "capture.paused") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PauseField, { spec }, key);
				if (key === "privacy.excluded_processes") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TagsField, {
					settingKey: key,
					spec,
					onChange: apply
				}, key);
				if (key === "storage.data_dir") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PathField, {
					settingKey: key,
					spec,
					onChange: apply,
					onReveal: () => void revealDirectory("data")
				}, key);
				if (key === "system.autostart" || key === "system.autostart_elevated") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionToggle, {
					settingKey: key,
					spec,
					path: key === "system.autostart" ? "/settings/autostart" : "/settings/autostart-elevated",
					onReload: reload
				}, key);
				return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Field, {
					settingKey: key,
					spec,
					onChange: apply
				}, key);
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: "读不到这一段的设置项。"
			})
		}),
		current.id === "data" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(DataCard, { status }) : null,
		current.id === "system" ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityCard, {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AboutCard, {
			status,
			configPath: payload?.config_path || ""
		})] }) : null
	] });
}
/**
* 「有 N 项改动要重启后生效」。
*
* **这里不给重启按钮**（18 文档 批 7）：重启与退出只从托盘走。重启会中断采集几秒，而它的
* 失败模式是"新实例起不来而旧实例已经退了"——那时页面上的按钮只会变成一个消失的标签页，
* 而托盘图标还在。
*/
function RestartNotice({ keys }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "banner",
		"data-severity": "warning",
		role: "status",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "banner__mark",
			"aria-hidden": "true",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "warning" })
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "banner__body",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "banner__title",
				children: [
					"本次改动有 ",
					keys.length,
					" 项要重启后生效"
				]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "banner__detail",
				children: [keys.map(labelOf).join("、"), "——从托盘菜单的「重新启动」生效"]
			})]
		})]
	});
}
//#endregion
export { loadSettings as n, SettingsPage as t };
