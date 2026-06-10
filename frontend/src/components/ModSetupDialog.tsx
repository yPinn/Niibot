import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Icon } from '@/components/ui/icon'
import { useGrantMod } from '@/hooks/useGrantMod'

interface ModSetupDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ModSetupDialog({ open, onOpenChange }: ModSetupDialogProps) {
  const { granting, grantMod } = useGrantMod(() => onOpenChange(false))

  function dismiss() {
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={dismiss}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon
              icon="fa-solid fa-shield-halved"
              size="lg"
              wrapperClassName="text-status-warning"
            />
            授予機器人管理員身份
          </DialogTitle>
          <DialogDescription>
            Niibot 需要 Mod 才能在你的頻道發言，並執行指令回應、事件通知、定時訊息等所有功能。
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={dismiss} disabled={granting}>
            稍後再說
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/docs/get-started" onClick={dismiss}>
              <Icon icon="fa-solid fa-book-open" />
              查看說明
            </Link>
          </Button>
          <Button size="sm" onClick={grantMod} disabled={granting}>
            <Icon icon={granting ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-sword'} />
            {granting ? '授予中…' : '一鍵授予 Mod'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
