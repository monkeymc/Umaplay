export type Stat = {
  spd: number;
  sta: number;
  pwr: number;
  guts: number;
  wit: number;
};

export type Skill = {
  is_auto_buy_skill: boolean;
  skill_pts_check: number;
  skill_list: string[];
};

export type Config = {
  priority_stat: string[];
  minimum_mood: string;
  maximum_failure: number;
  prioritize_g1_race: boolean;
  cancel_consecutive_race: boolean;
  stat_caps: Stat;
  skill: Skill;
};
