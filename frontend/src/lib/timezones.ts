// Curated IANA zones, not a free-text field — a typo here silently breaks a
// feature's day/time boundary. Picking from a list also keeps DST handling
// correct (ZoneInfo), which a raw UTC-offset number can't do. Shared by any
// feature with a per-channel timezone setting (check-in, stream schedule).
export const TIMEZONE_OPTIONS: { value: string; label: string }[] = [
  { value: 'Asia/Taipei', label: '台北（UTC+8）' },
  { value: 'Asia/Hong_Kong', label: '香港（UTC+8）' },
  { value: 'Asia/Shanghai', label: '上海（UTC+8）' },
  { value: 'Asia/Singapore', label: '新加坡（UTC+8）' },
  { value: 'Asia/Manila', label: '馬尼拉（UTC+8）' },
  { value: 'Asia/Tokyo', label: '東京（UTC+9）' },
  { value: 'Asia/Seoul', label: '首爾（UTC+9）' },
  { value: 'Asia/Bangkok', label: '曼谷（UTC+7）' },
  { value: 'Asia/Kolkata', label: '新德里（UTC+5:30）' },
  { value: 'Asia/Dubai', label: '杜拜（UTC+4）' },
  { value: 'Europe/Moscow', label: '莫斯科（UTC+3）' },
  { value: 'Europe/Berlin', label: '柏林（UTC+1/+2）' },
  { value: 'Europe/Paris', label: '巴黎（UTC+1/+2）' },
  { value: 'Europe/London', label: '倫敦（UTC+0/+1）' },
  { value: 'UTC', label: 'UTC（UTC+0）' },
  { value: 'America/New_York', label: '紐約（UTC-5/-4）' },
  { value: 'America/Chicago', label: '芝加哥（UTC-6/-5）' },
  { value: 'America/Denver', label: '丹佛（UTC-7/-6）' },
  { value: 'America/Los_Angeles', label: '洛杉磯（UTC-8/-7）' },
  { value: 'Australia/Sydney', label: '雪梨（UTC+10/+11）' },
  { value: 'Pacific/Auckland', label: '奧克蘭（UTC+12/+13）' },
]

/** Include the value itself, prefixed, if it's not one of the curated options
 * (e.g. an IANA zone typed in before this became a dropdown) so it stays
 * selectable instead of silently resetting the field to blank. */
export function withCurrentTimezone(current: string): { value: string; label: string }[] {
  if (!current || TIMEZONE_OPTIONS.some(option => option.value === current)) {
    return TIMEZONE_OPTIONS
  }
  return [{ value: current, label: current }, ...TIMEZONE_OPTIONS]
}
