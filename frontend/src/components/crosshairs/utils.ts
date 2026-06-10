import { recordCrosshairCopy } from '@/api/crosshairs'
import { copyToClipboard } from '@/lib/clipboard'

export function copyCode(code: string, id?: string) {
  copyToClipboard(code, '已複製準星代碼')
  if (id) recordCrosshairCopy(id)
}
