import { Link } from 'react-router-dom'

import { Icon, Spinner } from '@/components/primitives'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useGrantMod } from '@/hooks/useGrantMod'
import { dismissModPrompt, MANUAL_MOD_HASH } from '@/lib/mod-prompt'

interface ModSetupDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** First-visit prompt on Overview; wording mirrors Get Started's mod card. */
export function ModSetupDialog({ open, onOpenChange }: ModSetupDialogProps) {
  const { granting, grantMod } = useGrantMod(() => onOpenChange(false))

  function dismiss() {
    dismissModPrompt()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={next => !next && dismiss()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon icon="fa-solid fa-shield-halved" size="lg" wrapperClassName="text-primary" />讓
            Niibot 成為管理員
          </DialogTitle>
          <DialogDescription>需要 Mod 才能在頻道發言與執行指令。</DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={dismiss} disabled={granting}>
            稍後再說
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/docs/get-started#${MANUAL_MOD_HASH}`} onClick={dismiss}>
              手動設定
            </Link>
          </Button>
          <Button size="sm" onClick={grantMod} disabled={granting}>
            {granting ? <Spinner /> : <Icon icon="fa-solid fa-shield-halved" />}
            {granting ? '授予中…' : '一鍵授予 Mod'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
