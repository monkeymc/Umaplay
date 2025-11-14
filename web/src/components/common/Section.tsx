import { Paper, Stack, Typography } from '@mui/material';
import { useTheme, alpha } from '@mui/material/styles';

export default function Section({
  title,
  children,
  footer,
  sx,
  contentSx,
  titleSx,
}: {
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
  sx?: any
  contentSx?: any
  titleSx?: any
}) {
  const theme = useTheme()
  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: 2,
        p: 3,
        transition: 'border-color 120ms ease',
        maxWidth: sx?.maxWidth ?? '680px',
        border: sx?.variant === 'plain' ? 'none' : `1px solid ${alpha(theme.palette.divider, theme.palette.mode === 'dark' ? 0.3 : 0.5)}`,
        bgcolor:
          sx?.variant === 'plain'
            ? undefined
            : theme.palette.mode === 'dark'
              ? alpha(theme.palette.common.white, 0.04)
              : theme.palette.common.white,  // must be white
        boxShadow: 'none',
        '&:hover': sx?.variant === 'plain'
          ? undefined
          : {
              borderColor: alpha(theme.palette.primary.main, 0.35),
              boxShadow: `${alpha(theme.palette.primary.main, 0.12)} 0 8px 24px -12px`,
            },
        ...sx,
      }}
    >
      <Stack spacing={1} sx={contentSx}>
        <Typography variant="h6" sx={titleSx}>{title}</Typography>
        {children}
        {footer}
      </Stack>
    </Paper>
  )
}
