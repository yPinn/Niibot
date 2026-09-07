import { Icon } from '@/components/primitives'
import { Button } from '@/components/ui'

const INVITE_URL = import.meta.env.VITE_DISCORD_COMMUNITY_URL?.trim()

/**
 * Discord community call-to-action. The community server is the support / QA
 * entry point, so this is a full-weight block (not a muted footnote): brand
 * surface, a clear value line, and a primary button.
 */
export function DiscordHelpBanner() {
  return (
    <div className="flex flex-col gap-card rounded-xl border border-discord/20 bg-discord/5 p-page-lg sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3 sm:items-center">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-discord/10">
          <Icon icon="fa-brands fa-discord" size="lg" wrapperClassName="text-discord" />
        </span>
        <div className="flex flex-col gap-0.5">
          <p className="text-sub font-semibold">加入 Discord 社群</p>
          <p className="text-sub text-muted-foreground">
            提問、回報問題、搶先看更新，也能跟其他實況主交流使用心得。
          </p>
        </div>
      </div>
      {INVITE_URL ? (
        <Button asChild className="shrink-0 bg-discord hover:bg-discord/90">
          <a href={INVITE_URL} target="_blank" rel="noreferrer">
            <Icon icon="fa-brands fa-discord" wrapperClassName="mr-1.5" />
            加入社群
          </a>
        </Button>
      ) : (
        <Button disabled className="shrink-0" title="尚未設定 Discord 社群連結">
          <Icon icon="fa-brands fa-discord" wrapperClassName="mr-1.5" />
          加入社群
        </Button>
      )}
    </div>
  )
}
