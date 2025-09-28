export const PLACEHOLDER = `/placeholder_card.png`; // add a neutral image; UI will fallback to this on final error.

export const supportTypeIcons: Record<string, string> = {
  SPD: '/icons/support_card_type_spd.png',
  STA: '/icons/support_card_type_sta.png',
  PWR: '/icons/support_card_type_pwr.png',
  GUTS: '/icons/support_card_type_guts.png',
  WIT: '/icons/support_card_type_wit.png',
  PAL: '/icons/support_card_type_friend.png',
  None: '/icons/support_card_type_wit.png', // fallback
}

export function supportImageCandidates(name: string, rarity: any, attr: any) {
  const base = `/events/support`
  const NAME = name
  const ATTR = (attr || 'None').toUpperCase()
  const RAR  = rarity || 'None'
  return [
    `${base}/${NAME}_${ATTR}_${RAR}.png`,
    `${base}/${NAME}_${ATTR}_${RAR}.jpg`,
    `${base}/${NAME}_${ATTR}.png`,
    `${base}/${NAME}_${RAR}.png`,
    `${base}/${NAME}.png`,
  ]
}

export function scenarioImageCandidates(name: string) {
  const base = `/events/scenario`
  return [
    `${base}/${name}.png`,
    `${base}/${name}.jpeg`,
    `${base}/${name}.jpg`,
  ]
}

export function traineeImageCandidates(name?: string) {
  const base = `/events/trainee`
  return [
    `${base}/${name}_profile.png`,
    `${base}/${name}.png`,
    `${base}/${name}_profile.jpg`,
    `${base}/${name}.jpg`,
  ]
}

