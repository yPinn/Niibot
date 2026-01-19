import React, { createContext, useContext } from 'react'

import { useAuth } from './AuthContext'

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
    name: 'Niibot',
    icon: 'fa-brands fa-twitch',
    description: 'Twitch Bot',
  },
  {
    id: 'discord',
    name: 'Niibot',
    icon: 'fa-brands fa-discord',
    description: 'Discord Bot',
  },
]

interface BotContextType {
  activeBot: BotType
  activeBotInfo: BotInfo
  setActiveBot: (bot: BotType) => void
  bots: BotInfo[]
  canSwitchBot: boolean
}

const BotContext = createContext<BotContextType | undefined>(undefined)

export function BotProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()

  const activeBot: BotType = user?.platform || 'twitch'

  // TODO: 實作帳戶連結後啟用
  const canSwitchBot = false

  const handleSetActiveBot = (_bot: BotType) => {
    if (!canSwitchBot) return
  }

  const activeBotInfo = BOTS.find(b => b.id === activeBot) || BOTS[0]

  return (
    <BotContext.Provider
      value={{
        activeBot,
        activeBotInfo,
        setActiveBot: handleSetActiveBot,
        bots: BOTS,
        canSwitchBot,
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
