import { Box, Typography, useMediaQuery, useTheme, type SxProps, type Theme } from '@mui/material'
import InfoToggle from './InfoToggle'

type Props = {
  label: string
  control: React.ReactNode
  info?: React.ReactNode
  sx?: SxProps<Theme>
  /** Hide the info icon at and below this breakpoint */
  infoBreakpoint?: 'sm' | 'md' | 'lg'
  /** Collapse label+control into 2 rows below this breakpoint (default: md) */
  stackAt?: 'sm' | 'md' | 'lg'
}

export default function FieldRow({
  label,
  control,
  info,
  infoBreakpoint = 'lg',
  stackAt = 'lg',
  sx,
}: Props) {
  const theme = useTheme()
  const hideInfo = useMediaQuery(theme.breakpoints.down(infoBreakpoint))
  // 3 columns >= stackAt:
  const stackCols = {
    xs: '1fr',
    // Let label/control shrink to 0 if needed; keep info at a firm 3rem.
    [stackAt]: 'minmax(0,220px) minmax(0,1fr) 2rem',
  }
  const responsiveCol = { xs: '1 / -1', [stackAt]: 'auto' } as const
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: stackCols,
        columnGap: 1,
        rowGap: 1,
        alignItems: 'center',
        minWidth: 0,       // allow this grid to shrink within its card
        ...sx,
      }}
    >
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ gridColumn: responsiveCol }}
      >
        {label}
      </Typography>
      {/* Control: keep a sane min width and allow overflow to be clipped */}
      <Box
        sx={{
          minWidth: "6rem",           // allow grid to pass available width
          overflow: 'hidden',    // prevent slider tracks from overflowing
          contain: 'paint',
          gridColumn: responsiveCol,
        }}
      >
        {control}
      </Box>
      {/* Info: hide at/below breakpoint; keep a 3rem min when shown */}
      {info && !hideInfo && (
        <Box
          sx={{
            width: '2rem',
            display: 'flex',
            justifyContent: 'flex-end',
            flexShrink: 0, // do not let this cell collapse and steal space from control
          }}
        >
          <InfoToggle>{info}</InfoToggle>
        </Box>
      )}
    </Box>
  )
}
