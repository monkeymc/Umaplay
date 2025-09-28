import { useEffect, useState } from 'react'

type Props = {
  candidates: string[]
  alt: string
  style?: React.CSSProperties
  className?: string
  width?: number | string
  height?: number | string
  rounded?: number
}

export default function SmartImage({ candidates, alt, style, className, width, height, rounded = 8 }: Props) {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      for (const url of candidates) {
        try {
          const res = await fetch(url, { method: 'HEAD' })
          if (!cancelled && res.ok) {
            setSrc(url); break
          }
        } catch {/* ignore */}
      }
    })()
    return () => { cancelled = true }
  }, [JSON.stringify(candidates)])

  if (!src) return <div style={{ width, height, borderRadius: rounded, background: 'var(--mui-palette-action-hover)' }} />
  return <img src={src} alt={alt} style={{ width, height, borderRadius: rounded, objectFit: 'cover', ...style }} className={className} />
}
