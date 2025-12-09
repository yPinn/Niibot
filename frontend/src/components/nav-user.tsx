import { logout, type User } from '@/api'
import { useTheme } from '@/components/theme-provider'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'

export function NavUser({ user }: { user: User }) {
  const { isMobile } = useSidebar()
  const { theme, setTheme } = useTheme()

  const handleLogout = async () => {
    try {
      await logout()
      // 登出後重定向到登入頁面
      window.location.href = '/login'
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  // Get initials from display_name or name, fallback to '??'
  const getInitials = () => {
    const name = user.display_name || user.name || '??'
    return name.substring(0, 2).toUpperCase()
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
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
                icon="fa-solid fa-angles-up-down"
                className="ml-auto"
                wrapperClassName="size-4"
              />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
            side={isMobile ? 'bottom' : 'right'}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <Avatar className="h-8 w-8 rounded-full">
                  <AvatarImage src={user.avatar} alt={user.display_name || user.name} />
                  <AvatarFallback className="rounded-full">{getInitials()}</AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">{user.display_name || user.name}</span>
                  <span className="truncate text-xs">@{user.name}</span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem>
                <Icon icon="fa-solid fa-user" wrapperClassName="" />
                Account
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Icon icon="fa-solid fa-bell" wrapperClassName="" />
                Notifications
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
              <Icon
                icon={theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
                wrapperClassName=""
              />
              {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout}>
              <Icon icon="fa-solid fa-right-from-bracket" wrapperClassName="" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
