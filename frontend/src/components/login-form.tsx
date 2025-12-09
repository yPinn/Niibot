import { openTwitchOAuth } from '@/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Field, FieldGroup } from '@/components/ui/field'
import { Icon } from '@/components/ui/icon'
import { cn } from '@/lib/utils'

export function LoginForm({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className="overflow-hidden p-0">
        <CardContent className="grid p-0 md:grid-cols-2">
          <form className="p-6 md:p-8">
            <FieldGroup>
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold">歡迎使用 Niibot</h1>
                <p className="text-muted-foreground text-balance text-sm">
                  一個功能強大的 Twitch 聊天機器人
                </p>
              </div>
              <div className="my-6 space-y-4">
                <p className="text-foreground/80 text-sm leading-relaxed">
                  Niibot
                  提供豐富的互動功能，讓您的直播更加生動有趣。透過簡單的設定，即可為您的頻道增添更多樂趣。
                </p>
                <ul className="text-muted-foreground space-y-2 text-sm">
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
              <Field>
                <Button
                  type="button"
                  onClick={openTwitchOAuth}
                  className="bg-[#9146FF] hover:bg-[#7d3dd4] text-white w-full"
                >
                  <Icon icon="fa-brands fa-twitch" className="text-lg mr-2" wrapperClassName="" />
                  使用 Twitch 登入
                </Button>
              </Field>
            </FieldGroup>
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
