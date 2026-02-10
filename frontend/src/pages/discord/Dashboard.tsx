import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'

export default function DiscordDashboard() {
  return (
    <main className="h-full p-4 overflow-auto">
      <div className="grid gap-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-[#5865F2] text-white">
            <Icon icon="fa-brands fa-discord" wrapperClassName="size-5" />
          </div>
          <div>
            <h1 className="text-page-title font-bold">Discord Bot Dashboard</h1>
            <p className="text-secondary text-muted-foreground">管理您的 Discord 機器人</p>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">伺服器數量</CardTitle>
              <Icon icon="fa-solid fa-server" className="text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">--</div>
              <p className="text-label text-muted-foreground">即將推出</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">總用戶數</CardTitle>
              <Icon icon="fa-solid fa-users" className="text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">--</div>
              <p className="text-label text-muted-foreground">即將推出</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">今日指令</CardTitle>
              <Icon icon="fa-solid fa-terminal" className="text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">--</div>
              <p className="text-label text-muted-foreground">即將推出</p>
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
            <ul className="grid gap-2 text-secondary text-muted-foreground md:grid-cols-2">
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-spinner"
                  className="animate-spin"
                  wrapperClassName="size-3"
                />
                <span>伺服器管理面板</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-spinner"
                  className="animate-spin"
                  wrapperClassName="size-3"
                />
                <span>自訂指令設定</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-spinner"
                  className="animate-spin"
                  wrapperClassName="size-3"
                />
                <span>自動回覆規則</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-spinner"
                  className="animate-spin"
                  wrapperClassName="size-3"
                />
                <span>使用統計分析</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-spinner"
                  className="animate-spin"
                  wrapperClassName="size-3"
                />
                <span>權限管理系統</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  icon="fa-solid fa-spinner"
                  className="animate-spin"
                  wrapperClassName="size-3"
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
