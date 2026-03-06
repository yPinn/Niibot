import { Link } from 'react-router-dom'

import { Button, Icon } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function NotFound() {
  useDocumentTitle('Not Found')
  return (
    <div className="flex h-full flex-col items-center justify-center gap-section p-page text-center animate-in fade-in-0 animation-duration-300">
      <Icon
        icon="fa-solid fa-compass"
        className="text-6xl text-muted-foreground/30"
        wrapperClassName="size-20"
      />
      <div className="flex flex-col gap-element">
        <h1 className="text-page-title font-bold">找不到此頁面</h1>
        <p className="text-sub text-muted-foreground">你要找的頁面不存在或已被移除。</p>
      </div>
      <Button asChild>
        <Link to="/dashboard">
          <Icon icon="fa-solid fa-house" wrapperClassName="size-4" />
          回到 Dashboard
        </Link>
      </Button>
    </div>
  )
}
