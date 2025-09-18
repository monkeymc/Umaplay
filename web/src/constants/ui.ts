import type { StatKey } from '@/models/types'

export const STAT_ICON: Record<StatKey, string> = {
  SPD: '/icons/support_card_type_spd.png',
  STA: '/icons/support_card_type_sta.png',
  PWR: '/icons/support_card_type_pwr.png',
  GUTS: '/icons/support_card_type_guts.png',
  WIT: '/icons/support_card_type_wit.png',
}

export const BADGE_ICON: Record<string, string> = {
  G1: '/badges/G1.png',
  G2: '/badges/G2.png',
  G3: '/badges/G3.png',
  OP: '/badges/OP.png',
  EX: '/badges/EX.png',
  "PRE-OP": '/badges/PRE-OP.png',
  DEBUT: '/badges/DEBUT.png', // optional
}

export const DEFAULT_RACE_BANNER = '/race/default_banner.png' // put a small fallback here
