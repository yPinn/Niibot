import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { openTwitchOAuth } from '@/api'
import { errorMessage } from '@/api/errors'
import rabbitBg from '@/assets/images/Rabbit.jpg'
import { Icon, SlideUp } from '@/components/primitives'
import { Button, Card, CardContent } from '@/components/ui'
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
  const [isStartingOAuth, setIsStartingOAuth] = useState(false)

  async function handleTwitchLogin() {
    if (isStartingOAuth) return

    setIsStartingOAuth(true)
    try {
      await openTwitchOAuth()
    } catch (error) {
      toast.error('無法啟動 Twitch 登入', {
        description: errorMessage(error, '登入服務暫時無法使用，請稍後再試'),
      })
    } finally {
      setIsStartingOAuth(false)
    }
  }

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
                  先用 Twitch 登入，開始設定你的直播聊天室。
                </p>
              </div>
              <ul className="text-muted-foreground my-4 space-y-2 text-sub sm:my-6">
                <li className="flex items-start gap-2">
                  <Icon
                    icon="fa-solid fa-check"
                    className="text-primary mt-0.5"
                    wrapperClassName=""
                  />
                  <span>設定聊天室指令與自動回覆</span>
                </li>
                <li className="flex items-start gap-2">
                  <Icon
                    icon="fa-solid fa-check"
                    className="text-primary mt-0.5"
                    wrapperClassName=""
                  />
                  <span>在追隨、訂閱、突襲與忠誠點數兌換時自動回覆</span>
                </li>
                <li className="flex items-start gap-2">
                  <Icon
                    icon="fa-solid fa-check"
                    className="text-primary mt-0.5"
                    wrapperClassName=""
                  />
                  <span>依需求加入排隊、直播畫面與 Discord 工具</span>
                </li>
              </ul>
              <Button
                type="button"
                onClick={() => void handleTwitchLogin()}
                disabled={isStartingOAuth}
                className="w-full"
              >
                <Icon icon="fa-brands fa-twitch" className="text-lg mr-2" wrapperClassName="" />
                {isStartingOAuth ? '正在連接 Twitch…' : '使用 Twitch 登入'}
              </Button>
              <p className="text-label text-center text-muted-foreground">
                會前往 Twitch 完成登入，再回到 Niibot。
              </p>
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
