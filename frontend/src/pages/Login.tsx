import { LoginForm } from '@/components/login-form'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function LoginPage() {
  useDocumentTitle('Login')
  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-page-lg">
      <div className="w-full max-w-sm md:max-w-4xl">
        <LoginForm />
      </div>
    </div>
  )
}
