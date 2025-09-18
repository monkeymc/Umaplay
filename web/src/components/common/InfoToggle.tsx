import { IconButton, Tooltip } from '@mui/material'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { useState, useRef } from 'react'

type Props = {
  title?: string
  children: React.ReactNode // tooltip content (string or JSX)
}

/**
 * Click-to-toggle tooltip that closes when the mouse leaves the button.
 * Uses Tooltip with controlled open state (no layout shift / overflow).
 */
export default function InfoToggle({ title, children }: Props) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement | null>(null)

  return (
    <Tooltip
      title={children}
      placement="right"
      open={open}
      onClose={() => setOpen(false)}
      disableFocusListener
      disableHoverListener
      disableTouchListener
      PopperProps={{ modifiers: [{ name: 'offset', options: { offset: [0, 8] } }] }}
    >
      <IconButton
        ref={btnRef}
        size="small"
        onClick={() => setOpen((v) => !v)}
        onMouseLeave={() => setOpen(false)}
        aria-label={title || 'more info'}
        sx={{ ml: 1 }}
      >
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  )
}
