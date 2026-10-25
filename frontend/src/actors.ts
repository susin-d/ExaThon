export const ACTORS = [
  { id: 'susinsusindran@gmail.com', name: 'Susin Susindran' },
  { id: 'vigneshwaran7002@gmail.com', name: 'Vigneshwaran' },
  { id: 'sushramesh5@gmail.com', name: 'Sush Ramesh' },
] as const

export const CURRENT_ACTOR = ACTORS[Math.floor(Math.random() * ACTORS.length)]
