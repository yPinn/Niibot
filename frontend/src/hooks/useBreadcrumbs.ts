import { useLocation } from 'react-router-dom'

import { navigationData } from '@/config/navigation'

export interface BreadcrumbItem {
  label: string
  href?: string
}

export function useBreadcrumbs(): BreadcrumbItem[] {
  const location = useLocation()
  const breadcrumbs: BreadcrumbItem[] = []
  const currentPath = location.pathname

  // 搜尋 navMain 中的匹配項
  for (const mainItem of navigationData.navMain) {
    // 檢查是否有子項目匹配當前路徑
    if (mainItem.items) {
      for (const subItem of mainItem.items) {
        if (subItem.url === currentPath) {
          // 找到匹配，加入父項和當前項
          breadcrumbs.push({
            label: mainItem.title,
            href: mainItem.url !== '#' ? mainItem.url : undefined,
          })
          breadcrumbs.push({
            label: subItem.title,
          })
          return breadcrumbs
        }
      }
    }

    // 檢查主項目本身是否匹配
    if (mainItem.url === currentPath && mainItem.url !== '#') {
      breadcrumbs.push({
        label: mainItem.title,
      })
      return breadcrumbs
    }
  }

  // 如果沒有找到匹配，返回空陣列
  return breadcrumbs
}
