import type { ReactNode } from 'react'
import { ActorContext } from './actor-context'
import { CURRENT_ACTOR } from './actors'

export function ActorProvider({ children }: { children: ReactNode }) {
  return (
    <ActorContext.Provider value={{ ...CURRENT_ACTOR, role: 'Internal Ombudsman' }}>
      {children}
    </ActorContext.Provider>
  )
}
