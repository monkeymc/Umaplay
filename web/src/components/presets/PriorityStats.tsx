import { useConfigStore } from '@/store/configStore'
import { Chip, Stack, Typography, Paper, Avatar } from '@mui/material'
import { DndContext, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, useSortable, arrayMove, horizontalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { StatKey } from '@/models/types'
import { STAT_ICON } from '@/constants/ui'

function SortableChip({ id, label }: { id: StatKey; label: string }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  } as React.CSSProperties
  return (
    <div
      ref={setNodeRef}
      style={{ ...style, cursor: 'grab' }}
      {...attributes}
      {...listeners}
      onMouseDown={(e) => { (e.currentTarget as HTMLDivElement).style.cursor = 'grabbing' }}
      onMouseUp={(e) => { (e.currentTarget as HTMLDivElement).style.cursor = 'grab' }}
    >
      <Chip
        label={label}
        variant="outlined"
        avatar={<Avatar src={STAT_ICON[id]} alt={id} sx={{ width: 20, height: 20 }} />}
      />
    </div>
  )
}

export default function PriorityStats({ presetId }: { presetId: string }) {
  const preset = useConfigStore((s) => s.getSelectedPreset().preset)
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const sensors = useSensors(useSensor(PointerSensor))

  if (!preset) return null
  const stats = preset.priorityStats

  const onDragEnd = (event: any) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = stats.indexOf(active.id)
    const newIndex = stats.indexOf(over.id)
    const next = arrayMove(stats, oldIndex, newIndex)
    patchPreset(presetId, 'priorityStats', next)
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Priority Stat (drag to reorder)</Typography>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <SortableContext items={stats} strategy={horizontalListSortingStrategy}>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {stats.map((s) => (
              <SortableChip key={s} id={s} label={s} />
            ))}
          </Stack>
        </SortableContext>
      </DndContext>
    </Paper>
  )
}
