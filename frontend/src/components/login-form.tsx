import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { getDiscordOAuthStatus, openDiscordOAuth, openTwitchOAuth } from '@/api'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  Icon,
} from '@/components/ui'
import { cn } from '@/lib/utils'

const ERROR_MESSAGES: Record<string, string> = {
  db_not_ready: '伺服器資料庫尚未就緒，請稍後再試',
  db_timeout: '伺服器連線逾時，請稍後再試',
  save_token_failed: '登入資料儲存失敗，請稍後再試',
  no_code: '未收到授權碼，請重新登入',
  discord_not_configured: 'Discord 登入尚未設定',
  access_denied: '授權被拒絕',
}

export function LoginForm({ className, ...props }: React.ComponentProps<'div'>) {
  const [searchParams] = useSearchParams()
  const [discordEnabled, setDiscordEnabled] = useState(false)
  const [discordLoading, setDiscordLoading] = useState(true)

  const errorCode = searchParams.get('error')
  const errorMessage = errorCode ? ERROR_MESSAGES[errorCode] || `登入失敗 (${errorCode})` : null

  useEffect(() => {
    getDiscordOAuthStatus()
      .then(status => {
        setDiscordEnabled(status.enabled)
      })
      .catch(() => {
        setDiscordEnabled(false)
      })
      .finally(() => {
        setDiscordLoading(false)
      })
  }, [])

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className="overflow-hidden p-0">
        <CardContent className="grid p-0 md:grid-cols-2">
          <form className="p-6 md:p-8">
            <div className="flex flex-col gap-6">
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-page-title font-bold">歡迎使用 Niibot</h1>
                <p className="text-muted-foreground text-balance text-sub">
                  一個功能強大的 Twitch 聊天機器人
                </p>
              </div>
              <div className="my-6 space-y-4">
                <p className="text-foreground/80 text-sm leading-relaxed">
                  Niibot
                  提供豐富的互動功能，讓您的直播更加生動有趣。透過簡單的設定，即可為您的頻道增添更多樂趣。
                </p>
                <ul className="text-muted-foreground space-y-2 text-sub">
                  <li className="flex items-start gap-2">
                    <Icon
                      icon="fa-solid fa-check"
                      className="text-primary mt-0.5"
                      wrapperClassName=""
                    />
                    <span>自訂指令與自動回覆</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Icon
                      icon="fa-solid fa-check"
                      className="text-primary mt-0.5"
                      wrapperClassName=""
                    />
                    <span>即時聊天室管理</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Icon
                      icon="fa-solid fa-check"
                      className="text-primary mt-0.5"
                      wrapperClassName=""
                    />
                    <span>觀眾互動遊戲</span>
                  </li>
                </ul>
              </div>
              {errorMessage && (
                <Alert variant="destructive">
                  <Icon
                    icon="fa-solid fa-circle-exclamation"
                    className="size-4"
                    wrapperClassName=""
                  />
                  <AlertTitle>登入失敗</AlertTitle>
                  <AlertDescription>{errorMessage}</AlertDescription>
                </Alert>
              )}
              <div className="space-y-3">
                <Button
                  type="button"
                  onClick={openTwitchOAuth}
                  className="bg-[#9146FF] hover:bg-[#7d3dd4] text-white w-full"
                >
                  <Icon icon="fa-brands fa-twitch" className="text-lg mr-2" wrapperClassName="" />
                  使用 Twitch 登入
                </Button>
                {!discordLoading && discordEnabled && (
                  <Button
                    type="button"
                    onClick={openDiscordOAuth}
                    className="bg-[#5865F2] hover:bg-[#4752C4] text-white w-full"
                  >
                    <Icon
                      icon="fa-brands fa-discord"
                      className="text-lg mr-2"
                      wrapperClassName=""
                    />
                    使用 Discord 登入
                  </Button>
                )}
              </div>
            </div>
          </form>
          <div className="bg-muted relative hidden md:block">
            <img
              src="/images/Rabbit.jpg"
              alt="Image"
              className="absolute inset-0 h-full w-full object-cover dark:brightness-[0.75] "
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
