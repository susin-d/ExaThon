import type { ReactNode } from 'react'
import type { Actor } from './types'
import { ActorContext } from './actor-context'

export function ActorProvider({ children }: { children: ReactNode }) {
  return (
    <ActorContext.Provider value={{ id: 'ombudsman.demo', name: 'Ananya Rao', role: 'Internal Ombudsman' }}>
      {children}
    </ActorContext.Provider>
  )
}
