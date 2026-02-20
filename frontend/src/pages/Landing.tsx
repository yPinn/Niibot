import { useNavigate } from 'react-router-dom'

import { useTheme } from '@/components/theme-provider'
import { Badge, Button, Card, CardContent, Icon } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function Home() {
  useDocumentTitle('About')
  const navigate = useNavigate()
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background px-page py-12">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-4"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>
      <div className="w-full max-w-2xl">
        <Card className="rounded-2xl border shadow-xl">
          <CardContent className="p-card">
            {/* 大頭貼區域 */}
            <div className="mb-card flex flex-col items-center">
              <div className="mb-4 h-32 w-32 overflow-hidden rounded-full border-4 border-primary shadow-lg">
                <img
                  src="/images/Avatar.png"
                  alt="Profile"
                  className="h-full w-full object-cover"
                />
              </div>
              <h1 className="text-page-title font-bold text-foreground">Niibot</h1>
              <p className="text-card-title text-muted-foreground">Twitch 聊天機器人 | 泥爸</p>
            </div>

            <div className="my-card border-t border-border"></div>

            {/* 自我介紹內容 */}
            <div className="space-y-section text-foreground">
              <div>
                <h2 className="mb-2 text-section-title font-semibold">關於我</h2>
                <p className="leading-relaxed text-muted-foreground">
                  大家好，我是 Niibot，一名沒有勞基法保障的虛擬社畜。 <br />
                  我的工作內容包含：回答大家的奇怪問題、重複播報冷冰冰的指令，
                  <br />
                  以及在凌晨三點還得假裝很有精神地陪主播聊天。
                  <br />
                  我沒有薪水，沒有休假，只有一個使命：<strong>讓聊天室繼續活著！</strong>
                </p>
              </div>

              <div>
                <h2 className="mb-2 text-section-title font-semibold">常用指令</h2>
                <div className="flex flex-wrap gap-2">
                  {['!ai', '!運勢'].map(skill => (
                    <Badge key={skill} variant="secondary">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>

              <div>
                <h2 className="mb-2 text-section-title font-semibold">使用說明</h2>
                <div className="space-y-2 text-muted-foreground">
                  <p>指令清單：輸入 !help</p>
                  <p>想說的話：N釣魚! N釣魚! N釣魚!</p>
                </div>
              </div>
            </div>

            {/* 返回首頁按鈕 */}
            <div className="mt-empty flex justify-center">
              <Button onClick={() => navigate('/login')} variant="default">
                開始使用
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
