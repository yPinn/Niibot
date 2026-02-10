import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Icon } from '@/components/ui/icon'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function NotFound() {
  useDocumentTitle('404 - 頁面不存在')
  return (
    <div className="flex h-full items-center justify-center p-4">
      <Empty className="border-none">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Icon
              icon="fa-solid fa-circle-exclamation"
              wrapperClassName="size-6 text-destructive"
            />
          </EmptyMedia>
          <EmptyTitle className="text-page-title font-bold">404</EmptyTitle>
          <EmptyDescription className="text-content">
            The page you're looking for doesn't exist.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild>
            <Link to="/dashboard">
              <Icon icon="fa-solid fa-home" wrapperClassName="mr-2 size-4" />
              Back to Dashboard
            </Link>
          </Button>
        </EmptyContent>
      </Empty>
    </div>
  )
}
