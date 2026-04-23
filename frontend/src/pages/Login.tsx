import { LoginForm } from '@/components/login-form'
import { useTheme } from '@/components/theme-provider'
import { Button, Icon } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function LoginPage() {
  useDocumentTitle('Login')
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-page-lg">
      <Button
        variant="ghost"
        size="icon"
        className="fixed right-4 top-4 z-10"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>
      <div className="w-full max-w-sm md:max-w-4xl">
        <LoginForm />
      </div>
    </div>
  )
}
