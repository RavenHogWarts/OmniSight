import { d as bucketCoversGap } from "./main-DA_wrxiB.js";
//#region frontend/src/domain/buckets.ts
function markGaps(buckets, granularity, gaps, period) {
	if (!buckets?.length || !gaps || gaps.size === 0) return [...buckets || []];
	if (granularity === "hour") {
		const day = period?.start || period?.anchor;
		const missing = Boolean(day && gaps.has(day));
		return buckets.map((bucket) => missing ? {
			...bucket,
			gap: true
		} : bucket);
	}
	return buckets.map((bucket) => {
		return (granularity === "day" ? gaps.has(bucket.bucket) : bucketCoversGap(bucket.bucket, gaps)) ? {
			...bucket,
			gap: true
		} : bucket;
	});
}
/**
* 把趋势桶的 `categories` 展成活动带上面板要的 `parts`（14 文档 §4.3）。
*
* 键序即后端序（按类别 id 排），所以同一个类别在每个周期都堆在同一层——这与「构成」
* 卡的槽位规则是同一条（14 文档 §2.10）。后端保证各值之和恒等于 `seconds`，因此
* 堆叠段加起来正好是柱高；没有 `categories` 的响应（旧版本或裁剪过的 include）
* 退化成单色柱而不是空柱。
*/
function stackByCategory(buckets, catalog) {
	const names = new Map((catalog || []).map((item) => [item.id, item.name]));
	return (buckets || []).map((bucket) => {
		const entries = Object.entries(bucket.categories || {}).filter(([, seconds]) => (seconds || 0) > 0);
		if (!entries.length) return bucket;
		return {
			...bucket,
			parts: entries.map(([category, seconds]) => ({
				category,
				seconds,
				name: names.get(category) || category
			}))
		};
	});
}
//#endregion
export { stackByCategory as n, markGaps as t };
