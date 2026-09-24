// 0 = Monday, matching the backend's date.weekday() convention.
export const WEEKDAY_LABELS = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']

/** Indices into WEEKDAY_LABELS in Sunday-first display order — calendar
 * views and weekday pickers render in this order, while the underlying
 * `weekday` value stored on a schedule keeps its backend Monday=0 numbering
 * regardless of how it's displayed. */
export const WEEK_DISPLAY_ORDER = [6, 0, 1, 2, 3, 4, 5]

export const TITLE_VARS = [{ var: '$(channel)', desc: '頻道名稱' }]
