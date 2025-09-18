# UmAutoplay — Frontend (React + TypeScript + Vite)

This is the configuration UI for the Uma Musume AI agent. It lets you edit **General configurations** and **Presets**, autosaves to Local Storage, and can persist to the Python backend by writing `config.json` at the repo root.

The UI is built with **React + TypeScript + Vite**, **MUI**, **Zustand** (state), **Zod** (validation), and **React Query** (data fetching).

---

## Quick start

### 1) Requirements

* Node.js 18+ (LTS recommended)
* npm or pnpm (any works)
* The Python backend running at `127.0.0.1:8000` (start it with `python main.py` at the repo root)

### 2) Install & run (dev)

```bash
cd web
npm install
npm run dev
# open http://localhost:5173
```

Vite dev server proxies:

* `/config` → `http://127.0.0.1:8000/config` (save/read config.json)
* `/api/skills` → serves `datasets/in_game/skills.json`
* `/api/races` → serves `datasets/in_game/races.json`

### 3) Build for production

```bash
npm run build
# output in web/dist (served by FastAPI in server/main.py)
```

The Python app serves the built UI at `/` using `server/main.py`. The UI expects to live in `web/dist`.

---

## Tech stack

* **React 18 + TypeScript**
* **Vite** (ESBuild, dev server + production build)
* **Material UI (MUI)** for components/theming
* **Zustand** for app state (config + UI state)
* **Zod** for schema validation & type inference
* **React Query** for async data & caching
* **Vite alias** `@` → `/src`

---

## Project structure

```
web/
├─ public/                       # Static assets (served at /)
│  ├─ icons/
│  │  ├─ mode_steam.png
│  │  ├─ mode_scrcpy.png
│  │  └─ mode_bluestack.png
│  ├─ badges/                    # rank badges, etc (optional)
│  └─ mood/
│     ├─ awful.png
│     ├─ bad.png
│     ├─ normal.png
│     ├─ good.png
│     └─ great.png
├─ src/
│  ├─ components/
│  │  ├─ common/
│  │  │  ├─ FieldRow.tsx         # 3-column row: label | control | info
│  │  │  ├─ InfoToggle.tsx       # click-to-open tooltip/overlay
│  │  │  ├─ SaveLoadBar.tsx      # "Save config" (POST /config) + toast
│  │  │  └─ Section.tsx          # Paper wrapper with title & spacing
│  │  ├─ general/
│  │  │  ├─ GeneralForm.tsx      # General configs (accordion)
│  │  │  └─ AdvancedSettings.tsx # Collapsible advanced subsection
│  │  └─ presets/
│  │     ├─ PresetsShell.tsx     # Tabs + toolbar (add/remove/clone)
│  │     ├─ PresetPanel.tsx      # Per-preset form
│  │     ├─ PriorityStats.tsx    # Drag & drop order of stats
│  │     ├─ TargetStats.tsx      # Numeric stat targets (caps)
│  │     ├─ MoodSelector.tsx     # 5 mood images with opacity for unselected
│  │     ├─ SkillsPicker.tsx     # Dialog with search over skills.json
│  │     └─ RaceScheduler.tsx    # Search & select races (banners, badges)
│  ├─ models/
│  │  ├─ config.schema.ts        # Zod schema for config; types inferred here
│  │  └─ datasets.ts             # Types for skills & races data
│  ├─ pages/
│  │  └─ Home.tsx                # Layout: General (left) + Presets (right)
│  ├─ services/
│  │  └─ api.ts                  # fetchSkills, fetchRaces, saveServerConfig
│  ├─ store/
│  │  └─ configStore.ts          # Zustand store (config + UI state)
│  ├─ utils/
│  │  ├─ race.ts                 # toDateKey, pretty date helpers
│  │  └─ debounce.ts             # (optional) utilities
│  ├─ main.tsx                   # entrypoint
│  └─ theme.ts                   # MUI theme (light/dark)
├─ index.html
├─ tsconfig.json
└─ vite.config.ts
```

---

## How config flows

* **Local autosave**: The entire config (`configStore.config`) automatically syncs to Local Storage with a short debounce. No button needed for local persistence.

* **Save to backend**: Click **Save config** → `POST /config` with the whole config JSON. FastAPI writes it to `config.json` at the repo root. On the Python side, `Settings.apply_config()` + `Settings.extract_runtime_preset()` are called when you **start** the agent, so the runtime uses the latest values.

* **Seed on first run**: Python app ensures `config.json` exists. If not, it copies `config.sample.json`.

---

## UI behavior

* **Responsive layout**:

  * Not collapsed: two columns (left = General, \~1/3; right = Presets, \~2/3)
  * Collapsed: General becomes a compact bar; Presets take full width
* **Info buttons**: Each field has an **i** control. Click to show an explanation (tooltip/persisting popover), hide on mouse-out.
* **Theme toggle**: Switch between light/dark. This affects the UI only (not the game).

---

## State & schema

### Zustand store

`src/store/configStore.ts` exposes:

* `config`: the full typed config object (validated by `config.schema.ts`)
* `setGeneral(partial)`: patch General config
* `patchPreset(presetId, key, value)`: patch a specific preset field
* `addPreset()`, `removePreset(id)`, `clonePreset(id)`, `renamePreset(id, name)`
* `setActivePreset(id)`
* UI state: `uiTheme`, `uiGeneralCollapsed`, etc.
* `loadLocal()` + `saveLocal()` for Local Storage hydration
* `exportJson()` / `importJson()` for preset sharing (optional flow)

### Zod schema

`src/models/config.schema.ts` defines the shape:

* **General**

  * `mode: 'steam' | 'scrcpy' | 'bluestack'` (default: steam)
  * `windowTitle: string`
  * `fastMode: boolean`
  * `tryAgainOnFailedGoal: boolean`
  * `prioritizeHint: boolean`
  * `maxFailure: number (0..99)`
  * `skillPtsCheck: number`
  * `acceptConsecutiveRace: boolean`
  * `advanced: { hotkey, debugMode, useExternalProcessor, externalProcessorUrl, autoRestMin }`
* **Presets\[]**

  * `name: string`
  * `priorityStats: string[]` (order matters)
  * `targetStats: { SPD, STA, PWR, GUTS, WIT }`
  * `minimalMood: 'AWFUL' | 'BAD' | 'NORMAL' | 'GOOD' | 'GREAT'`
  * `selectStyleInJunior: 'end' | 'late' | 'pace' | 'front' | null`
  * `skills: (string | {name:string, description?:string})[]`
  * `plannedRaces: Record<dateKey, raceName>`
* **UI meta**

  * `activePresetId: string`

> The store initializes defaults through this schema to prevent “undefined” errors.

---

## Common dev tasks

### Add a new field to **General configurations**

1. **Add to schema**: `src/models/config.schema.ts`

```ts
const GeneralSchema = z.object({
  // ...
  myNewFlag: z.boolean().default(false),
})
```

2. **Render with `FieldRow`**: `src/components/general/GeneralForm.tsx`

```tsx
<FieldRow
  label="My new flag"
  info="Explain what this does."
  control={
    <FormControlLabel
      control={
        <Switch
          checked={g.myNewFlag}
          onChange={(e) => setGeneral({ myNewFlag: e.target.checked })}
        />
      }
      label={g.myNewFlag ? 'Enabled' : 'Disabled'}
    />
  }
/>
```

3. **Map to backend (optional)**: `core/settings.py -> Settings.apply_config`

```py
Settings.MY_NEW_FLAG = bool(g.get("myNewFlag", Settings.MY_NEW_FLAG))
```

### Add a slider field (no overflow!)

Use this pattern to keep it inside its cell:

```tsx
<FieldRow
  label="Threshold"
  info="Description."
  control={
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Slider
        value={g.threshold}
        onChange={(_, v) => setGeneral({ threshold: Number(v) })}
        min={0}
        max={100}
        sx={{ flex: 1 }}
      />
      <Typography variant="body2" sx={{ width: 32, textAlign: 'right' }}>
        {g.threshold}
      </Typography>
    </Box>
  }
/>
```

### Add a new field to **Preset**

1. **Schema**: Add to `PresetSchema` and defaults.
2. **UI**: Create a small component (e.g., `NewPresetControl.tsx`) and mount it in `PresetPanel.tsx`. Use `useConfigStore().patchPreset(presetId, key, value)` to update.

### Add a new API endpoint usage

Add the client in `src/services/api.ts`:

```ts
export async function fetchFoo(): Promise<Foo> {
  const r = await fetch('/api/foo')
  if (!r.ok) throw new Error('Failed to fetch /api/foo')
  return r.json()
}
```

Then use it with React Query:

```ts
const { data, isLoading, error } = useQuery({ queryKey: ['foo'], queryFn: fetchFoo })
```

### Add icons/images

* Put images in `public/…` and reference by absolute path (e.g., `/icons/mode_steam.png`).
* For mood icons, we use:

```ts
const moodImgs: Partial<Record<MoodName, string>> = {
  AWFUL: '/mood/awful.png',
  BAD: '/mood/bad.png',
  NORMAL: '/mood/normal.png',
  GOOD: '/mood/good.png',
  GREAT: '/mood/great.png',
}
```

### Add/modify Race Scheduler visuals

* Banners: by default, we show `instance.race_url` (if present), else `instance.banner_url`, else a `DEFAULT_RACE_BANNER` from `src/constants/ui`.
* Badges: map rank → image via `BADGE_ICON` map.
* Pretty date: we render `year_label — date_text`. If missing, we derive from `dateKey`.

---

## UX patterns

* **FieldRow**: always use `control={...}` (not children) and keep controls inside a `<Box sx={{ minWidth: 0, overflow: 'hidden' }}>` to prevent overflow.
* **InfoToggle**: explanatory tips. Click to toggle, auto-hide on mouse-out.
* **Icons in selects**: use MUI `Select.renderValue` to render an icon + text.
* **Drag handles**: show hand cursor on hover for reordering (PriorityStats).

---

## Toasts

* The “Save config” button shows a **Snackbar + Alert**. See `SaveLoadBar.tsx`.
* For more toasts, use the same pattern or bring in `notistack` if you prefer.

---

## Theming

* Light/Dark toggled in General Form (`UI Theme`).
* See `src/theme.ts` for palette overrides. The toggle only affects the admin UI.

---

## Data files

* `datasets/in_game/skills.json` — queried at `/api/skills`
* `datasets/in_game/races.json` — queried at `/api/races`

The backend serves these (see `/api/skills` and `/api/races` routes in `server/main.py`). If you change those file paths, update the server and `fetchSkills/fetchRaces`.

---

## Backend integration

* **Save config**: UI POSTs to `/config` with the whole config object. FastAPI writes `config.json`.
* **On Start** (hotkey toggle): Python side calls `load_config()`, `Settings.apply_config()`, and reads active preset via `Settings.extract_runtime_preset()`. No restart required to pick new values before starting.

---

## Code quality

* **Type safety**: Zod schema → inferred TS types for the config & datasets.
* **State isolation**: `configStore.ts` owns all mutations. Components call store actions only.
* **Components**: Keep focused and portable. Prefer small, tested leaf components over big monoliths.
* **Naming**: Use `camelCase` for variables, `PascalCase` for components, and folder names matching component names.

---

## Troubleshooting

* **CORS / 404 on /config**: Ensure the Python server is running on `127.0.0.1:8000`. Vite proxies `/config` → backend (see `vite.config.ts`).
* **Images not showing**: Assets must be under `public/`. Reference with `/path/from/public`.
* **Sliders overflowing**: Ensure you used the `FieldRow` `control={…}` pattern and wrapped controls in a flex Box with `minWidth:0; overflow:hidden;`.
* **Races/skills empty**: Confirm backend endpoints `/api/skills` & `/api/races` serve the files; watch terminal logs.

---

## FAQ

**Q:** Can I export/import entire config files from the UI?
**A:** The main button writes server-side `config.json`. For sharing **presets**, use the (optional) import/export actions in the Presets panel (disabled by default; easy to enable in `SaveLoadBar.tsx` or Presets toolbar).

**Q:** How do I add a new preset programmatically?
**A:** Use `useConfigStore().addPreset()` and then `setActivePreset(id)`. The store ensures schema defaults.

**Q:** Can we hot-swap MODE (steam/scrcpy) live?
**A:** The controller is created on app boot, but **Start** re-applies settings and updates the controller’s window title. If you want full controller type hot-swap, we can recreate the controller object in `BotState.start()` based on `Settings.MODE`.

---

## Scripts

```bash
npm run dev     # start Vite dev server
npm run build   # build to web/dist (served by FastAPI)
npm run preview # preview build locally on a static server
```
