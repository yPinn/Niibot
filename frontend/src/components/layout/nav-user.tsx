import { useLocation, useNavigate } from 'react-router-dom'

import { type User } from '@/api'
import { useTheme } from '@/components/layout/theme-provider'
import { Icon, TwitchRoleBadge } from '@/components/primitives'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useTenant } from '@/contexts/TenantContext'

export function NavUser({ user, showWorkspaces = true }: { user: User; showWorkspaces?: boolean }) {
  const { isMobile } = useSidebar()
  const { resolvedTheme, setTheme } = useTheme()
  const { logout } = useAuth()
  const { tenants, activeTenant, selectTenant } = useTenant()
  const location = useLocation()
  const navigate = useNavigate()

  const getInitials = () => {
    const name = user.display_name || user.name || '??'
    return name.substring(0, 2).toUpperCase()
  }

  const profileUrl =
    user.platform === 'discord'
      ? `https://discord.com/users/${user.id}`
      : `https://twitch.tv/${user.name}`

  const workspaceName =
    showWorkspaces && activeTenant
      ? activeTenant.display_name || activeTenant.channel_name
      : user.display_name || user.name
  const workspaceRole = showWorkspaces && activeTenant ? activeTenant.role : null

  const switchWorkspace = (channelId: string) => {
    selectTenant(channelId)
    const suffix = location.pathname.match(/^\/dashboard\/[^/]+(\/.*)?$/)?.[1] ?? ''
    navigate(`/dashboard/${encodeURIComponent(channelId)}${suffix}`)
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="bg-sidebar-accent hover:bg-sidebar-accent data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <Avatar className="h-8 w-8 rounded-full">
                <AvatarImage src={user.avatar} alt={user.display_name || user.name} />
                <AvatarFallback className="rounded-full">{getInitials()}</AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left">
                <span className="flex min-w-0 items-center gap-1 text-sm leading-[18px]">
                  {workspaceRole && (
                    <TwitchRoleBadge
                      role={workspaceRole === 'owner' ? 'broadcaster' : 'moderator'}
                      label={workspaceRole === 'owner' ? '擁有者' : 'Mod'}
                    />
                  )}
                  <span className="truncate font-medium">{workspaceName}</span>
                </span>
                <span className="truncate text-xs leading-[14px] text-muted-foreground">
                  @{user.name}
                </span>
              </div>
              <Icon icon="fa-solid fa-angles-up-down" className="mr-1" wrapperClassName="size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
            side={isMobile ? 'bottom' : 'right'}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              登入身分
            </DropdownMenuLabel>
            <DropdownMenuItem asChild className="p-0">
              <a
                href={profileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex w-full items-center gap-2 px-2 py-1.5 no-underline"
              >
                <Avatar className="h-8 w-8 rounded-full">
                  <AvatarImage src={user.avatar} alt={user.display_name || user.name} />
                  <AvatarFallback className="rounded-full">{getInitials()}</AvatarFallback>
                </Avatar>

                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">{user.display_name || user.name}</span>
                  <span className="truncate text-xs">@{user.name}</span>
                </div>

                <Icon
                  icon="fa-solid fa-up-right-from-square"
                  wrapperClassName="ml-auto mr-1 size-3.5"
                />
              </a>
            </DropdownMenuItem>

            {showWorkspaces && tenants.length > 0 && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                  切換工作區
                </DropdownMenuLabel>
                <DropdownMenuRadioGroup
                  value={activeTenant?.channel_id ?? ''}
                  onValueChange={switchWorkspace}
                >
                  {tenants.map(tenant => (
                    <DropdownMenuRadioItem
                      key={tenant.channel_id}
                      value={tenant.channel_id}
                      className="gap-1.5"
                    >
                      <TwitchRoleBadge
                        role={tenant.role === 'owner' ? 'broadcaster' : 'moderator'}
                        label={tenant.role === 'owner' ? '擁有者' : 'Mod'}
                      />
                      <span className="min-w-0 flex-1 truncate leading-[18px]">
                        {tenant.display_name || tenant.channel_name}
                      </span>
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </>
            )}

            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              <Icon icon="fa-solid fa-gear" wrapperClassName="" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}>
              <Icon
                icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
                wrapperClassName=""
              />
              {resolvedTheme === 'dark' ? 'Light Mode' : 'Dark Mode'}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout}>
              <Icon icon="fa-solid fa-arrow-right-from-bracket" wrapperClassName="" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
