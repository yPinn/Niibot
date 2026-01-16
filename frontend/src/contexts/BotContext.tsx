import React, { createContext, useContext, useState } from 'react'

export type BotType = 'twitch' | 'discord'

export interface BotInfo {
  id: BotType
  name: string
  icon: string
  description: string
}

export const BOTS: BotInfo[] = [
  {
    id: 'twitch',
    name: 'Twitch Bot',
    icon: 'fa-brands fa-twitch',
    description: 'Twitch 聊天機器人',
  },
  {
    id: 'discord',
    name: 'Discord Bot',
    icon: 'fa-brands fa-discord',
    description: 'Discord 伺服器機器人',
  },
]

interface BotContextType {
  activeBot: BotType
  activeBotInfo: BotInfo
  setActiveBot: (bot: BotType) => void
  bots: BotInfo[]
}

const BotContext = createContext<BotContextType | undefined>(undefined)

export function BotProvider({ children }: { children: React.ReactNode }) {
  const [activeBot, setActiveBot] = useState<BotType>(() => {
    // 從 localStorage 讀取上次選擇的 bot
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('activeBot')
      if (saved === 'twitch' || saved === 'discord') {
        return saved
      }
    }
    return 'twitch'
  })

  const handleSetActiveBot = (bot: BotType) => {
    setActiveBot(bot)
    localStorage.setItem('activeBot', bot)
  }

  const activeBotInfo = BOTS.find(b => b.id === activeBot) || BOTS[0]

  return (
    <BotContext.Provider
      value={{
        activeBot,
        activeBotInfo,
        setActiveBot: handleSetActiveBot,
        bots: BOTS,
      }}
    >
      {children}
    </BotContext.Provider>
  )
}

export function useBot() {
  const context = useContext(BotContext)
  if (context === undefined) {
    throw new Error('useBot must be used within a BotProvider')
  }
  return context
}
