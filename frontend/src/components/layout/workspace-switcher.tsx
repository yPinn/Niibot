import { useLocation, useNavigate } from 'react-router-dom'

import { useTenant } from '@/contexts/TenantContext'

export function WorkspaceSwitcher() {
  const { tenants, activeTenant, selectTenant } = useTenant()
  const location = useLocation()
  const navigate = useNavigate()

  if (tenants.length === 0) return null

  const handleChange = (channelId: string) => {
    selectTenant(channelId)
    const suffix = location.pathname.match(/^\/dashboard\/[^/]+(\/.*)?$/)?.[1] ?? ''
    navigate(`/dashboard/${encodeURIComponent(channelId)}${suffix}`)
  }

  return (
    <div className="px-2 pb-1 group-data-[collapsible=icon]:hidden">
      <label htmlFor="workspace-switcher" className="sr-only">
        目前工作區
      </label>
      <select
        id="workspace-switcher"
        aria-label="目前工作區"
        value={activeTenant?.channel_id ?? ''}
        onChange={event => handleChange(event.target.value)}
        className="h-9 w-full rounded-md border border-sidebar-border bg-sidebar px-2 text-sm text-sidebar-foreground outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
      >
        {tenants.map(tenant => (
          <option key={tenant.channel_id} value={tenant.channel_id}>
            {tenant.display_name || tenant.channel_name}
            {tenant.role === 'owner' ? '（擁有者）' : '（MOD）'}
          </option>
        ))}
      </select>
    </div>
  )
}
