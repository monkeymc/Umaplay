// Core effect payload in options (raw outcomes inside each option)
export type EventOptionEffect = Record<string, any>; // { power?: number, hints?: string[], ... }

export type AttrKey = 'SPD' | 'STA' | 'PWR' | 'GUTS' | 'WIT' | 'PAL' | 'None';
export type Rarity = 'SSR' | 'SR' | 'R';

export type RawChoiceEvent = {
  type: 'random' | 'chain' | 'special';
  chain_step: number;
  name: string;
  options: Record<string, EventOptionEffect[]>;
  default_preference?: number;
};

// events.json top-level entry (raw)
export type RawEventSet = {
  type: 'support' | 'scenario' | 'trainee';
  name: string;
  rarity?: Rarity | 'None';
  attribute?: AttrKey;
  id?: string;
  choice_events: RawChoiceEvent[];
};

// Normalized event (frontend)
export type ChoiceEvent = {
  type: 'random' | 'chain' | 'special' | string;
  chain_step: number; // default → 1
  name: string;
  options: Record<string, EventOptionEffect[]>;
  default_preference: number | null; // null if absent
};

// Normalized sets used by UI
export type SupportSet = {
  kind: 'support';
  id?: string;
  name: string;
  attribute: AttrKey;
  rarity: Rarity;
  imgCandidates: string[];
  events: ChoiceEvent[];
};

export type ScenarioSet = {
  kind: 'scenario';
  id?: string;
  name: string;
  imgCandidates: string[];
  events: ChoiceEvent[];
};

export type TraineeSet = {
  kind: 'trainee';
  id?: string;
  name: string;
  imgCandidates: string[];
  events: ChoiceEvent[];
};

export type EventsRoot = RawEventSet[];

// Indices the UI will use
export type SupportsIndex = Map<AttrKey, Map<Rarity, SupportSet[]>>;

export type TraineeIndex = {
  general: TraineeSet | null;
  specific: Map<string, TraineeSet>; // by exact trainee name
};

export type EventsIndex = {
  supports: SupportsIndex;
  scenarios: ScenarioSet[];
  trainees: TraineeIndex;
};

// --- UI state ---

export type SupportPriority = {
  enabled: boolean;
  scoreBlueGreen: number;
  scoreOrangeMax: number;
  // Deprioritize this support's hints once these skills are acquired (ANY match)
  skillsRequiredForPriority?: string[];
  // After taking a hint from this support, immediately re-check the skills screen
  // to attempt buying any newly unlocked required skills.
  recheckAfterHint?: boolean;
};

export type SelectedSupport = {
  slot: number // 0..5
  name: string
  rarity: Rarity
  attribute: AttrKey
  rewardPriority?: RewardCategory[]
  priority?: SupportPriority
  avoidEnergyOverflow?: boolean
};

export type SelectedScenario = { name: string; avoidEnergyOverflow?: boolean; rewardPriority?: RewardCategory[] } | null
export type SelectedTrainee  = { name: string; avoidEnergyOverflow?: boolean; rewardPriority?: RewardCategory[] } | null

export type RewardCategory = 'skill_pts' | 'hints' | 'stats'

// step-aware key: "type/name/attribute/rarity/eventName#s<step>"
export type EventKey = string

export type EventOverrides = Record<EventKey, number>
export type EventPatterns  = { pattern: string; pick: number }[]
export type EventDefaults  = { support: number; scenario: number; trainee: number }

export type EventPrefs = {
  overrides: EventOverrides
  patterns: EventPatterns
  defaults: EventDefaults
  rewardPriority: RewardCategory[]
}

// --- Event Setup (what we persist locally and attach to presets on save) ---
export type EventSetup = {
  supports: (SelectedSupport | null)[]   // length 6
  scenario: SelectedScenario
  trainee: SelectedTrainee
  prefs: EventPrefs                      // overrides + defaults
}