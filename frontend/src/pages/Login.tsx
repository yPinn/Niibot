import { useTheme } from '@/components/layout/theme-provider'
import { LoginForm } from '@/components/login-form'
import { FadeIn, Icon } from '@/components/primitives'
import { Button } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function LoginPage() {
  useDocumentTitle('登入')
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-4 md:p-page-lg">
      <Button
        variant="ghost"
        size="icon"
        className="fixed right-4 top-4 z-raised"
        aria-label={`切換至${resolvedTheme === 'dark' ? '淺色' : '深色'}主題`}
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>
      <FadeIn className="w-full max-w-sm sm:max-w-md md:max-w-4xl">
        <LoginForm />
      </FadeIn>
    </div>
  )
}
