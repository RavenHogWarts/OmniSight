// 后端响应的形状（05 文档是契约本身，这里是它的机器可读副本）。
//
// **为什么需要它**：零构建的前端一路 `(payload && payload.apps) || []` 地防御性取值，
// 后端改一个字段名，前端只是静默显示空值——而"这段时间没有记录"恰好是合法状态，
// 于是拼错的字段看起来像"没数据"。tools/check_frontend.py 查不到（它只做导入解析与
// 文本模式），dom-shim 也测不到（它断言渲染结构）。07 文档 §10 列了三处前后端必须
// 一致的内容并各自给了执行机制，**字段级形状原先不在其中**，这个文件补上那一处。
//
// **两份真相的问题由测试解决，不靠人**：tests/integration/test_frontend_contract.py
// 拿 seeded_client 打一遍真实端点，把响应的键集与这里声明的逐层比对——多一个字段、
// 少一个必填字段、改一个名字都会红。因此这里写错比写少更危险，别凭印象加字段。
//
// 约定：
//   * 嵌套对象一律给具名 interface，不用内联字面量——契约测试按名字递归。
//   * 后端可能给 null 的字段写 `| null`；只在某些参数下才出现的字段写 `?`。
//   * JSON 只有一种数字，因此 int 与 float 都是 number。

// ── 公共外壳（05 文档 §2）─────────────────────────────────────────────

/** 非致命的口径说明。前端把它显示成提示，不当错误。 */
export interface ApiWarning {
  code: string;
  message: string;
}

/** 某段时间缺某类数据。前端据此在趋势图上打断口（domain/buckets.js）。 */
export interface CoverageGap {
  from: string;
  to: string;
  missing: string;
  reason: string;
  message: string;
}

export interface Coverage {
  total_days: number;
  recorded_days: number;
  foreground_days: number;
  keyboard_days: number;
  title_days: number;
  key_position_days: number;
  gaps: CoverageGap[];
}

/** 后端算好的区间。周期栏的标题与箭头置灰都读它，前端不重算（07 文档 §10）。 */
export interface PeriodMeta {
  range: string;
  anchor: string;
  start: string;
  end: string;
  truncated_end: string;
  label: string;
  days: number;
  granularity: string;
  is_current: boolean;
}

/**
 * 最小外壳。`/keyboard/layout` 只有这一个字段——它回的是静态布局，没有数据版本，
 * 也没有"生成时刻"可言。
 */
export interface WarningsOnly {
  warnings: ApiWarning[];
}

/** 带数据版本的外壳。`/status` 到此为止（它本身就是"此刻"，不另给 generated_at）。 */
export interface BaseEnvelope extends WarningsOnly {
  data_version: number;
}

/**
 * 统计端点的外壳。`period` / `coverage` 只在按周期查询的端点上出现——
 * `/apps`、`/settings`、`/onboarding` 不按周期取数，因此它们是可选的。
 */
export interface Envelope extends BaseEnvelope {
  generated_at: string;
  period?: PeriodMeta;
  coverage?: Coverage;
}

// ── 应用维度（05 文档 §3）─────────────────────────────────────────────

/** 周期内的一行应用用量。`/overview` 的 top_apps 与 `/usage/period` 的 apps 同形。 */
export interface AppUsageRow {
  app_id: number;
  process_name: string;
  display_name: string;
  user_alias: string | null;
  category: string;
  icon_url: string;
  seconds: number;
  seconds_formatted: string;
  percent: number;
  presses: number;
  kpm: number;
  session_count: number;
  longest_session_seconds: number;
  first_seen_at: string;
  last_seen_at: string;
  is_running: boolean;
}

/** 分类目录项。`/apps` 与 `/settings` 都给这一份。 */
export interface CategoryOption {
  id: string;
  name: string;
}

/** 按分类的占比（总览的环形图）。 */
export interface CategoryShare {
  id: string;
  name: string;
  seconds: number;
  seconds_formatted: string;
  percent: number;
  presses: number;
}

export interface Pagination {
  limit: number;
  offset: number;
  total: number;
}

/** `/apps` 的一行：管理元数据，与周期无关。 */
export interface AppRecord {
  app_id: number;
  process_name: string;
  display_name: string;
  user_alias: string | null;
  category: string;
  category_source: string;
  icon_url: string;
  icon_state: string;
  excluded: boolean;
  merged_into: number | null;
  total_seconds: number;
  total_seconds_formatted: string;
  total_presses: number;
  session_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface AppsResponse extends Envelope {
  apps: AppRecord[];
  categories: CategoryOption[];
  pagination: Pagination;
}

export interface UsagePeriodResponse extends Envelope {
  apps: AppUsageRow[];
  app_count: number;
  total_seconds: number;
  total_seconds_formatted: string;
  kpm_basis: string;
  filtered_by: string | null;
  pagination: Pagination;
}

/** 应用详情页头部的那条记录。比 AppRecord 多路径与合并成员，少周期数字。 */
export interface AppDetailRecord {
  app_id: number;
  process_name: string;
  display_name: string;
  user_alias: string | null;
  exe_path: string;
  category: string;
  category_source: string;
  icon_url: string;
  icon_state: string;
  excluded: boolean;
  merged_into: number | null;
  merged_members: number[];
  first_seen_at: string;
  last_seen_at: string;
}

export interface AppTotal {
  seconds: number;
  seconds_formatted: string;
  presses: number;
  session_count: number;
}

export interface AppTotals {
  day: AppTotal;
  week: AppTotal;
  month: AppTotal;
  total: AppTotal;
}

/** 键位小计。`/apps/{id}` 与 `/insights/app-keyboard` 共用。 */
export interface KeyTally {
  id: string;
  label: string;
  press_count: number;
}

/** 修饰键占比。 */
export interface ModifierShare {
  id: string;
  label: string;
  press_count: number;
  percent: number;
}

export interface AppKeyboardSummary {
  profile: string;
  profile_name: string;
  kpm: number;
  kpm_basis: string;
  modifier_percent: number;
  modifier_breakdown: ModifierShare[];
  top_keys: KeyTally[];
}

/** 应用详情的趋势桶。**比总览的 TrendBucket 少 presses**——这里只画时长。 */
export interface AppTrendBucket {
  bucket: string;
  label: string;
  seconds: number;
}

export interface AppTrend {
  granularity: string;
  buckets: AppTrendBucket[];
}

export interface AppDetailResponse extends Envelope {
  app: AppDetailRecord;
  totals: AppTotals;
  keyboard: AppKeyboardSummary;
  trend: AppTrend;
}

/** 一段会话。`window_title` 只在 include_titles 且隐私设置允许时非 null（08 文档 §4）。 */
export interface UsageSession {
  id: number;
  app_id: number;
  display_name: string;
  start: string;
  end: string;
  seconds: number;
  seconds_formatted: string;
  window_title: string | null;
  idle_trimmed: boolean;
  end_reason: string;
}

export interface SessionsResponse extends Envelope {
  sessions: UsageSession[];
  titles_included: boolean;
  pagination: Pagination;
}

// ── 总览与时间线（05 文档 §3.1）───────────────────────────────────────

export interface Delta {
  seconds?: number;
  presses?: number;
  percent: number;
}

export interface ScreenTimeSummary {
  total_seconds: number;
  total_formatted: string;
  daily_average_seconds: number;
  app_count: number;
  /** `range=total` 没有"上一周期"可比，此时为 null。 */
  delta_vs_previous: Delta | null;
}

export interface KeyboardSummary {
  total_presses: number;
  active_keys: number;
  duration_total_ms: number;
  duration_avg_ms: number;
  kpm_peak: number;
  /** 同 ScreenTimeSummary：`range=total` 时为 null。 */
  delta_vs_previous: Delta | null;
}

export interface TrendBucket {
  bucket: string;
  label: string;
  seconds: number;
  presses: number;
}

export interface Trend {
  granularity: string;
  buckets: TrendBucket[];
}

/** 一条结论。`basis` 说明它是怎么算出来的，前端原样显示（06 文档 §5.3）。 */
export interface Highlight {
  code: string;
  text: string;
  basis: string;
}

/**
 * `/overview`。`include=highlights` 时只回结论段，其余段缺席——因此除 `included`
 * 之外的业务段全是可选的。
 */
export interface OverviewResponse extends Envelope {
  included: string[];
  screen_time?: ScreenTimeSummary;
  keyboard?: KeyboardSummary;
  top_apps?: AppUsageRow[];
  categories?: CategoryShare[];
  trend?: Trend;
  highlights?: Highlight[];
}

export interface TimelineHourApp {
  app_id: number;
  display_name: string;
  seconds: number;
  percent: number;
}

export interface TimelineHour {
  hour: number;
  total_seconds: number;
  categories: Record<string, number>;
  apps: TimelineHourApp[];
  other_seconds: number;
  presses: number;
}

export interface UsageTimelineResponse extends Envelope {
  hours: TimelineHour[];
}

// ── 键盘维度（05 文档 §4）─────────────────────────────────────────────

/**
 * 布局里的一个键。`w` 是键宽倍数，1 = 标准键宽（07 文档 §6.4）。
 * 后端的 `KeySlot.to_dict` 只在必要时才给后三个字段：占位槽（`id === 'gap'`）没有
 * `label`，`h` 只在跨行时给，`shape` 只有非矩形键才有（目前只有 `iso_enter`）。
 */
export interface LayoutKey {
  id: string;
  w: number;
  label?: string;
  h?: number;
  shape?: string;
}

export interface LayoutUnitHint {
  rows: number;
  max_units: number;
}

/** 键盘布局。**坐标全在后端**，前端只按 rows 顺序渲染。 */
export interface LayoutResponse extends WarningsOnly {
  family: string;
  name: string;
  source: string;
  available_families: string[];
  rows: LayoutKey[][];
  unit_hint: LayoutUnitHint;
}

/** 热力图里的一个键。`rank` 只对有按压的键给值。 */
export interface HeatmapKey {
  id: string;
  label: string;
  row: string;
  finger: string;
  press_count: number;
  percent: number;
  duration_total_ms: number;
  duration_avg_ms: number;
  duration_max_ms: number;
  rank: number | null;
}

/**
 * 色阶。p95 是归一化的基准，不用 max——一个 Space 会把其余键压成同一个色（06 文档 §7）。
 * 键盘时间线的每个粒度各自带一份，且**不带 metric**（metric 在响应顶层）。
 */
export interface BucketScale {
  min: number;
  max: number;
  p95: number;
}

/** 热力图的色阶：多一个 metric，说明这组数字是按哪个指标算的。 */
export interface HeatScale extends BucketScale {
  metric: string;
}

export interface HeatmapTotals {
  press_count: number;
  active_keys: number;
  duration_total_ms: number;
  duration_avg_ms: number;
  duration_max_ms: number;
}

/** 查询范围。`type` 是 all 或 app，后者带 app_id。 */
export interface Scope {
  type: string;
  app_id?: number;
  display_name?: string;
}

export interface HeatmapResponse extends Envelope {
  metric: string;
  layout_family: string;
  layout_source: string;
  scope: Scope;
  keys: HeatmapKey[];
  /** 不在当前布局里但有数据的键（换过键盘、跨机器共用库）。 */
  orphan_keys: HeatmapKey[];
  scale: HeatScale;
  totals: HeatmapTotals;
}

/** 时间线的一个桶。`duration_max_ms` 在 hours 粒度上不给。 */
export interface KeyTimelineBucket {
  bucket: string;
  label: string;
  press_count: number;
  duration_total_ms: number;
  duration_avg_ms: number;
  duration_max_ms?: number;
}

export interface KeyTimelineRange {
  start: string;
  end: string;
}

export interface KeyTimelineView {
  available: boolean;
  period: KeyTimelineRange;
  buckets: KeyTimelineBucket[];
  scale: BucketScale;
}

/** 四个粒度一次取回：KeyTrace 首屏为此发过 4 个请求（05 文档 §4）。 */
export interface KeyTimelineViews {
  hours: KeyTimelineView;
  days: KeyTimelineView;
  months: KeyTimelineView;
  years: KeyTimelineView;
}

export interface KeyboardTimelineResponse extends Envelope {
  metric: string;
  views: KeyTimelineViews;
}

export interface KeyIdentity {
  id: string;
  label: string;
  row: string;
  row_name: string;
  finger: string;
  finger_name: string;
  hid_usage: number;
  in_layout: boolean;
}

export interface KeyTotals {
  press_count: number;
  duration_total_ms: number;
  duration_avg_ms: number;
  duration_max_ms: number;
}

export interface KeyByApp {
  app_id: number;
  display_name: string;
  press_count: number;
  percent: number;
}

export interface KeyByHour {
  hour: number;
  press_count: number;
}

export interface KeyDetailResponse extends Envelope {
  key: KeyIdentity;
  totals: KeyTotals;
  by_app: KeyByApp[];
  by_hour: KeyByHour[];
}

export interface FingerLoad {
  id: string;
  name: string;
  hand: string;
  press_count: number;
  percent: number;
}

export interface RowLoad {
  id: string;
  name: string;
  press_count: number;
  percent: number;
}

export interface HandBalance {
  left: number;
  right: number;
  neutral: number;
  balance_percent: number;
}

export interface ModifierRatio {
  plain: number;
  with_modifier: number;
  percent: number;
  basis: string;
}

export interface ErgonomicsResponse extends Envelope {
  scope: Scope;
  total_presses: number;
  fingers: FingerLoad[];
  rows: RowLoad[];
  hands: HandBalance;
  modifier_ratio: ModifierRatio;
}

// ── 洞察（05 文档 §5）─────────────────────────────────────────────────

/** `/insights/app-keyboard` 的一行。比 AppUsageRow 多键盘画像，少图标与会话。 */
export interface AppIntensityRow {
  app_id: number;
  display_name: string;
  seconds: number;
  seconds_formatted: string;
  presses: number;
  kpm: number;
  intensity_rank: number;
  profile: string;
  profile_name: string;
  modifier_percent: number;
  modifier_breakdown: ModifierShare[];
  top_keys: KeyTally[];
}

/** 时间去向的一档（输入密集 / 阅读 / 被动…）。 */
export interface DistributionBucket {
  id: string;
  name: string;
  seconds: number;
  seconds_formatted: string;
  percent: number;
}

export interface Distribution {
  buckets: DistributionBucket[];
  total_seconds: number;
  input_heavy_seconds: number;
  passive_seconds: number;
  passive_percent: number;
}

export interface AppKeyboardResponse extends Envelope {
  apps: AppIntensityRow[];
  distribution: Distribution;
  kpm_basis: string;
  unattributed_presses: number;
}

export interface HourlyRhythm {
  hour: number;
  seconds: number;
  presses: number;
  kpm: number;
}

export interface HourPeakScreen {
  hour: number;
  seconds: number;
}

export interface HourPeakTyping {
  hour: number;
  seconds: number;
  kpm: number;
}

export interface HourPeaks {
  screen: HourPeakScreen;
  typing: HourPeakTyping;
  typing_basis: string;
  same_hour: boolean;
}

export interface ActiveHours {
  first: string;
  last: string;
  span_hours: number;
}

export interface PeakKpm {
  value: number;
  at: string;
}

/** 一段专注块。 */
export interface FocusBlock {
  app_id: number;
  display_name: string;
  start: string;
  end: string;
  minutes: number;
  presses: number;
  kpm: number;
  end_reason: string;
}

export interface RhythmResponse extends Envelope {
  hourly: HourlyRhythm[];
  hourly_basis: string;
  hour_peaks: HourPeaks;
  active_hours: ActiveHours;
  peak_kpm: PeakKpm;
  switch_count: number;
  switches_per_hour: number;
  switches_basis: string;
  longest_focus_minutes: number;
  focus_blocks: FocusBlock[];
}

// ── 系统与设置（05 文档 §6、§7）───────────────────────────────────────

/**
 * 有效能力。**前端只读这些布尔值做分支**，不读 platform.id——
 * tools/check_frontend.py 强制这一条（07 文档 §10）。
 */
export interface Capabilities {
  keyboard: boolean;
  keyboard_backend: string;
  keyboard_durations: boolean;
  key_position_stable: boolean;
  foreground: boolean;
  window_titles: boolean;
  idle: boolean;
  icons: boolean;
  autostart: boolean;
  tray: boolean;
  permissions_required: string[];
  permissions_granted: string[];
  setup_hint: string | null;
}

/** 一条能力缺失说明。文案讲清缺什么、什么仍正常、怎么解决（05 文档 §7）。 */
export interface DegradedNotice {
  code: string;
  severity: string;
  title: string;
  detail: string;
  hint: string | null;
  docs: string | null;
}

export interface BackendState {
  running: boolean;
  backend: string;
}

export interface WriterState {
  running: boolean;
}

export interface CaptureState {
  paused: boolean;
  keyboard: BackendState;
  foreground: BackendState;
  writer: WriterState;
  queue_depth: number;
  dropped_events: number;
}

export interface DataRange {
  min_date: string | null;
  max_date: string | null;
}

export interface DatabaseInfo {
  path: string;
  size_bytes: number;
  schema_version: number;
}

/** 设置页显示的路径。frozen / portable 是字符串化的布尔值。 */
export interface PathsInfo {
  app_root: string;
  data_dir: string;
  logs_dir: string;
  config: string;
  exe_dir: string;
  resource_dir: string;
  frozen: string;
  portable: string;
}

/** 只作为设置页的一行展示信息，**不许用来做分支**（07 文档 §10）。 */
export interface PlatformInfo {
  id: string;
  tier: number;
  os_version: string;
}

export interface StatusResponse extends BaseEnvelope {
  app: string;
  version: string;
  port: number;
  started_at: string;
  platform: PlatformInfo;
  capabilities: Capabilities;
  degraded: DegradedNotice[];
  capture: CaptureState;
  database: DatabaseInfo;
  data_range: DataRange;
  paths: PathsInfo;
}

export type SettingValue = string | number | boolean | string[] | null;

/** 一条可改设置。`applies` 说明改完何时生效，`available` 为假时前端置灰并显示原因。 */
export interface SettingField {
  kind: string;
  value: SettingValue;
  default: SettingValue;
  applies: string;
  available: boolean;
  min?: number;
  max?: number;
  options?: string[];
  note?: string;
  unavailable_reason?: string;
}

export interface SettingsResponse extends Envelope {
  settings: Record<string, SettingField>;
  categories: CategoryOption[];
  config_path: string;
}

// ── 首次运行说明（05 文档 §6.4）───────────────────────────────────────

export interface OnboardingRecord {
  code: string;
  text: string;
  detail?: string;
}

export interface OnboardingDocuments {
  privacy: string;
  faq: string;
  uninstall: string;
}

export interface OnboardingPaths {
  data_dir: string;
  database: string;
  config: string;
  logs_dir: string;
  portable: string;
}

export interface OnboardingPause {
  tray_item: string;
  detail: string;
}

export interface OnboardingPlatform {
  id: string;
  tier: number;
  tier_label: string;
  notice: string;
}

export interface OnboardingResponse extends Envelope {
  version: number;
  required: boolean;
  acknowledged_at: string | null;
  records: OnboardingRecord[];
  not_records: OnboardingRecord[];
  paths: OnboardingPaths;
  documents: OnboardingDocuments;
  pause: OnboardingPause;
  platform: OnboardingPlatform;
}

// ── 旧库导入（09 文档 §2）─────────────────────────────────────────────

/** 默认搜索路径下发现的一个旧库。 */
export interface LegacySource {
  path: string;
  kind: string;
  size_bytes: number;
  mtime: string;
}

export interface DetectResponse {
  detected: LegacySource[];
}

export interface LegacySelection {
  timelens: string | null;
  keytrace: string | null;
}

export interface TimeLensSessionScan {
  rows: number;
  date_min: string | null;
  date_max: string | null;
  has_titles: boolean;
}

export interface TimeLensKeyScan {
  rows: number;
  days: number;
  date_min: string | null;
  date_max: string | null;
  presses: number;
  unmapped_names: string[];
  ambiguous_names: string[];
}

export interface TimeLensScan {
  sessions: TimeLensSessionScan;
  key_usage: TimeLensKeyScan;
}

export interface KeyTraceRawScan {
  tables: number;
  rows: number;
  ts_min_ns: number | null;
  ts_max_ns: number | null;
}

export interface KeyTraceScan {
  raw: KeyTraceRawScan;
  key_days: string[];
}

/** 步骤 2 的"将导入什么 / 会丢什么"。只读扫描，不写库。 */
export interface ImportPreviewResponse {
  sources: LegacySelection;
  timelens?: TimeLensScan;
  keytrace?: KeyTraceScan;
  conflict_days: string[];
  losses: string[];
}

/**
 * 导入进度。向导与横幅的唯一状态来源。
 * `available` 只在从未导入过时出现；`phase` 起及之后的字段只在有状态记录时出现。
 */
export interface ImportProgressResponse {
  state: string;
  busy: boolean;
  task: string | null;
  error: string | null;
  available?: boolean;
  phase?: string | null;
  counts?: Record<string, number>;
  skipped_days?: string[];
  sources?: LegacySelection;
  backup_dir?: string | null;
  report?: ImportReportResponse | null;
}

export interface ImportSessionsReport {
  imported: number;
  skipped_invalid: number;
  days: number;
  date_range: (string | null)[];
}

export interface ImportKeyUsageReport {
  presses: number;
  days: number;
  duration_available: boolean;
  attribution_available: boolean;
}

export interface ImportRawReport {
  imported: number;
  days: number;
}

export interface ImportReportResponse {
  generated_at: string | null;
  duration_seconds: number | null;
  sources: LegacySelection;
  backup_dir: string | null;
  sessions: ImportSessionsReport;
  key_usage: ImportKeyUsageReport;
  raw_events: ImportRawReport;
  skipped_days: string[];
  unmapped_keys: Record<string, number>;
  losses: string[];
  notes: string[];
}

// ── 实时流（05 文档 §9、08 文档 §2）───────────────────────────────────

/** `foreground` 事件：前台应用变了。 */
export interface LiveForeground {
  app_id: number;
  display_name: string;
}

/** `counters` 事件：今日累计。状态点的浮层读它。 */
export interface LiveCounters {
  presses: number;
  seconds: number;
  kpm: number;
  data_version: number;
}

/** `keypress` 事件：**只有 key_id**，没有时间戳、没有顺序（08 文档 §2）。 */
export interface LiveKeypress {
  keys: string[];
}

// ── 错误（05 文档 §2.3）───────────────────────────────────────────────

/** 4xx/5xx 的响应体。core/api.js 的 ApiError 从这里取字段。 */
export interface ApiErrorBody {
  code: string;
  message: string;
  field?: string;
}

export interface ErrorResponse {
  error: ApiErrorBody;
}

// ── 缓存键 → 响应类型（07 文档 §5.2）─────────────────────────────────
//
// `store.js` 的 `data` 切片按这张表取值，因此视图里 `state.data.appsPeriod` 直接
// 就是 `UsagePeriodResponse | undefined`——不需要在每个使用点断言一次。
// 加一个新请求时必须在这里登记，否则 `fetchInto` 的 key 参数不接受它。

export interface DataMap {
  overview: OverviewResponse;
  overviewIntensity: AppKeyboardResponse;
  appsPeriod: UsagePeriodResponse;
  appsMeta: AppsResponse;
  appDetail: AppDetailResponse;
  appSessions: SessionsResponse;
  layout: LayoutResponse;
  heatmap: HeatmapResponse;
  timeline: KeyboardTimelineResponse;
  ergonomics: ErgonomicsResponse;
  keyDetail: KeyDetailResponse;
  insightHighlights: OverviewResponse;
  insightKeyboard: AppKeyboardResponse;
  insightRhythm: RhythmResponse;
  insightTimeline: UsageTimelineResponse;
  insightHeatmap: HeatmapResponse;
  insightKey: KeyDetailResponse;
}

/** 取数失败后写进 `errors` 切片的那条记录（core/loader.js 的 describe）。 */
export interface RequestFailure {
  message: string;
  code: string;
  status: number;
  field?: string | null;
}

/** 视图声明"我需要哪些数据"时的一项（07 文档 §5.2）。 */
export interface DataRequest {
  key: keyof DataMap;
  path: string;
  params?: Record<string, string | number | boolean | null | undefined>;
  options?: { maxAge?: number };
}
