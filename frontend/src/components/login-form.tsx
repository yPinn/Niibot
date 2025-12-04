import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Icon } from '@/components/ui/icon'
import { Input } from '@/components/ui/input'
import { getDiscordAuthUrl } from '@/lib/discord-oauth'
import { cn } from '@/lib/utils'

export function LoginForm({ className, ...props }: React.ComponentProps<'div'>) {
  const handleDiscordLogin = () => {
    window.location.href = getDiscordAuthUrl()
  }

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className="overflow-hidden p-0">
        <CardContent className="grid p-0 md:grid-cols-2">
          <form className="p-6 md:p-8">
            <FieldGroup>
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold">Welcome back</h1>
                <p className="text-muted-foreground text-balance">Login to Niibot</p>
              </div>
              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input id="email" type="email" placeholder="m@example.com" required />
              </Field>
              <Field>
                <div className="flex items-center">
                  <FieldLabel htmlFor="password">Password</FieldLabel>
                  <a href="#" className="ml-auto text-sm underline-offset-2 hover:underline">
                    Forgot your password?
                  </a>
                </div>
                <Input id="password" type="password" required />
              </Field>
              <Field>
                <Button type="submit">Login</Button>
              </Field>
              <FieldSeparator className="*:data-[slot=field-separator-content]:bg-card">
                Or continue with
              </FieldSeparator>
              <Field className="grid grid-cols-2 gap-6">
                <Button
                  variant="outline"
                  type="button"
                  className="bg-[#9146FF]/75 hover:bg-[#9146FF] text-white border-none"
                >
                  <Icon icon="fa-brands fa-twitch" className="text-lg" wrapperClassName="" />
                  <span className="sr-only">Login with Twitch</span>
                </Button>
                <Button
                  variant="outline"
                  type="button"
                  onClick={handleDiscordLogin}
                  className="bg-[#5865F2]/75 hover:bg-[#5865F2] text-white border-none"
                >
                  <Icon icon="fa-brands fa-discord" className="text-lg" wrapperClassName="" />
                  <span className="sr-only">Login with Discord</span>
                </Button>
              </Field>
            </FieldGroup>
          </form>
          <div className="bg-muted relative hidden md:block">
            <img
              src="/images/Rabbit.jpg"
              alt="Image"
              className="absolute inset-0 h-full w-full object-cover dark:brightness-[0.2] dark:grayscale"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
