import { LockOverlay } from './LockOverlay'

interface WipLockOverlayProps {
  className?: string
}

export function WipLockOverlay({ className }: WipLockOverlayProps) {
  return (
    <LockOverlay
      icon="fa-solid fa-screwdriver-wrench"
      title="功能開發中"
      description={
        <>
          此頁面正在積極建置，
          <br />
          完成後將立即開放。
        </>
      }
      fullPage
      className={className}
    />
  )
}
