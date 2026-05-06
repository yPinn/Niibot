import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { openTwitchOAuth } from '@/api'
import rabbitBg from '@/assets/images/Rabbit.jpg'
import { Button, Card, CardContent, Icon, SlideUp } from '@/components/ui'
import { cn } from '@/lib/utils'

const ERROR_MESSAGES: Record<string, string> = {
  db_not_ready: '伺服器資料庫尚未就緒，請稍後再試',
  db_timeout: '伺服器連線逾時，請稍後再試',
  save_token_failed: '登入資料儲存失敗，請稍後再試',
  no_code: '未收到授權碼，請重新登入',
  access_denied: '授權被拒絕',
}

const REASON_MESSAGES: Record<string, string> = {
  session_expired: '登入已過期，請重新登入',
}

export function LoginForm({ className, ...props }: React.ComponentProps<'div'>) {
  const [searchParams, setSearchParams] = useSearchParams()

  // Process error / reason params once on mount
  useEffect(() => {
    const errorCode = searchParams.get('error')
    const reasonCode = searchParams.get('reason')
    if (errorCode) {
      const errorMessage = ERROR_MESSAGES[errorCode] || `登入失敗 (${errorCode})`
      toast.error('登入失敗', { description: errorMessage })
      setSearchParams({}, { replace: true })
    } else if (reasonCode) {
      const reasonMessage = REASON_MESSAGES[reasonCode]
      if (reasonMessage) {
        toast.warning(reasonMessage)
        setSearchParams({}, { replace: true })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <SlideUp className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className="overflow-hidden p-0">
        <CardContent className="grid p-0 md:grid-cols-2">
          <form className="select-none p-5 sm:p-6 md:p-8">
            <div className="flex flex-col gap-6">
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-page-title font-bold">歡迎使用 Niibot</h1>
                <p className="text-muted-foreground text-balance text-sub">
                  Twitch 直播 × Discord 社群的機器人助手
                </p>
              </div>
              <ul className="text-muted-foreground my-4 space-y-2 text-sub sm:my-6">
                <li className="flex items-start gap-2">
                  <Icon
                    icon="fa-solid fa-check"
                    className="text-primary mt-0.5"
                    wrapperClassName=""
                  />
                  <span>自訂指令、觸發詞與定時訊息</span>
                </li>
                <li className="flex items-start gap-2">
                  <Icon
                    icon="fa-solid fa-check"
                    className="text-primary mt-0.5"
                    wrapperClassName=""
                  />
                  <span>遊戲 / 影片排隊與 OBS 疊加層</span>
                </li>
                <li className="flex items-start gap-2">
                  <Icon
                    icon="fa-solid fa-check"
                    className="text-primary mt-0.5"
                    wrapperClassName=""
                  />
                  <span>Discord 社群連結預覽與伺服器日誌</span>
                </li>
              </ul>
              <Button type="button" onClick={openTwitchOAuth} className="w-full">
                <Icon icon="fa-brands fa-twitch" className="text-lg mr-2" wrapperClassName="" />
                使用 Twitch 登入
              </Button>
            </div>
          </form>
          <div className="bg-muted relative hidden min-h-72 select-none md:block">
            <img
              src={rabbitBg}
              alt=""
              draggable="false"
              className="absolute inset-0 h-full w-full object-cover dark:brightness-[0.75]"
            />
            <div className="absolute inset-0 bg-linear-to-r from-card via-card/10 to-transparent" />
          </div>
        </CardContent>
      </Card>
    </SlideUp>
  )
}
