import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'

export default function DiscordDashboard() {
  return (
    <main className="h-full p-4 overflow-auto">
      <div className="grid gap-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-[#5865F2] text-white">
            <Icon icon="fa-brands fa-discord" className="size-5" wrapperClassName="" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Discord Bot Dashboard</h1>
            <p className="text-muted-foreground text-sm">管理您的 Discord 機器人</p>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">伺服器數量</CardTitle>
              <Icon
                icon="fa-solid fa-server"
                className="size-4 text-muted-foreground"
                wrapperClassName=""
              />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">--</div>
              <p className="text-xs text-muted-foreground">即將推出</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">總用戶數</CardTitle>
              <Icon
                icon="fa-solid fa-users"
                className="size-4 text-muted-foreground"
                wrapperClassName=""
              />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">--</div>
              <p className="text-xs text-muted-foreground">即將推出</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">今日指令</CardTitle>
              <Icon
                icon="fa-solid fa-terminal"
                className="size-4 text-muted-foreground"
                wrapperClassName=""
              />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">--</div>
              <p className="text-xs text-muted-foreground">即將推出</p>
            </CardContent>
          </Card>
        </div>

        {/* Coming Soon Section */}
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>Discord Bot 功能開發中</CardTitle>
            <CardDescription>以下功能即將推出</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-2 text-sm text-muted-foreground md:grid-cols-2">
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-circle-notch"
                  className="size-3 animate-spin"
                  wrapperClassName=""
                />
                <span>伺服器管理面板</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-circle-notch"
                  className="size-3 animate-spin"
                  wrapperClassName=""
                />
                <span>自訂指令設定</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-circle-notch"
                  className="size-3 animate-spin"
                  wrapperClassName=""
                />
                <span>自動回覆規則</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-circle-notch"
                  className="size-3 animate-spin"
                  wrapperClassName=""
                />
                <span>使用統計分析</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-circle-notch"
                  className="size-3 animate-spin"
                  wrapperClassName=""
                />
                <span>權限管理系統</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-circle-notch"
                  className="size-3 animate-spin"
                  wrapperClassName=""
                />
                <span>日誌與審計</span>
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
