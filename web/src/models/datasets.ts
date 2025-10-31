export type SkillRarity = 'normal' | 'gold' | 'unique'

export type Skill = {
  name: string
  description?: string
  icon_filename?: string
  color_class?: string
  rarity?: SkillRarity
  grade_symbol?: string
  category?: string
}

export type RaceInstance = {
  year_label: string
  year_int: number
  date_text: string
  month: number
  day: number
  surface: string
  course_hint?: string
  location?: string
  distance_category: string
  distance_text: string
  distance_m: number
  banner_url?: string
  public_banner_path?: string
  ribbon_src?: string
  ribbon_code?: string
  rank: 'PRE-OP' | 'EX' | 'OP' | 'G3' | 'G2' | 'G1' | string
}

export type RacesMap = Record<string, RaceInstance[]>
