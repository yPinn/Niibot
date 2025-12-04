import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { handleDiscordCallback } from '@/lib/discord-oauth'

export default function DiscordCallback() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('處理 Discord 驗證中...')

  useEffect(() => {
    const processCallback = async () => {
      const result = handleDiscordCallback()

      if (result.success && result.code) {
        setStatus('success')
        setMessage('驗證成功！正在導向...')

        // TODO: 將 code 發送到後端 API 進行驗證
        // 範例：
        // try {
        //   const response = await fetch('/api/auth/discord', {
        //     method: 'POST',
        //     headers: { 'Content-Type': 'application/json' },
        //     body: JSON.stringify({ code: result.code }),
        //   })
        //   const data = await response.json()
        //   // 儲存 token 到 localStorage
        //   localStorage.setItem('token', data.token)
        // } catch (error) {
        //   console.error('驗證失敗:', error)
        //   setStatus('error')
        //   setMessage('驗證失敗，請重試')
        //   return
        // }

        // 暫時直接導向 dashboard
        setTimeout(() => {
          navigate('/')
        }, 1500)
      } else {
        setStatus('error')
        setMessage(`驗證失敗: ${result.error}`)

        setTimeout(() => {
          navigate('/login')
        }, 3000)
      }
    }

    processCallback()
  }, [navigate])

  return (
    <div className="bg-background flex min-h-svh flex-col items-center justify-center p-6">
      <div className="bg-card text-card-foreground flex flex-col items-center gap-4 rounded-lg border p-8 shadow-lg">
        {status === 'loading' && (
          <>
            <div className="border-primary h-12 w-12 animate-spin rounded-full border-4 border-t-transparent" />
            <p className="text-muted-foreground">{message}</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="bg-green-500 flex h-12 w-12 items-center justify-center rounded-full">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-6 w-6 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-foreground font-medium">{message}</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="bg-destructive flex h-12 w-12 items-center justify-center rounded-full">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-6 w-6 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-destructive font-medium">{message}</p>
            <p className="text-muted-foreground text-sm">即將返回登入頁面...</p>
          </>
        )}
      </div>
    </div>
  )
}
