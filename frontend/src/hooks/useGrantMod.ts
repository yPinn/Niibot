import { useState } from 'react'
import { toast } from 'sonner'

import { grantBotMod } from '@/api/channels'
import { toastApiError } from '@/lib/toast-error'

export function useGrantMod(onSuccess?: (alreadyMod: boolean) => void) {
  const [granting, setGranting] = useState(false)

  const grantMod = async () => {
    setGranting(true)
    try {
      const res = await grantBotMod()
      if (res.granted || res.already_mod) {
        if (res.already_mod) {
          toast.info('Niibot 已經是管理員了')
        } else {
          toast.success('管理員授予成功')
        }
        onSuccess?.(res.already_mod)
      }
    } catch (e) {
      toastApiError(e, '授予失敗，請稍後再試')
    } finally {
      setGranting(false)
    }
  }

  return { granting, grantMod }
}
