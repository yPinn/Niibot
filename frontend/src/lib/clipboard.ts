import { toast } from 'sonner'

export function copyToClipboard(text: string, successMsg = '已複製', errorMsg = '複製失敗'): void {
  navigator.clipboard.writeText(text).then(
    () => toast.success(successMsg),
    () => toast.error(errorMsg)
  )
}
