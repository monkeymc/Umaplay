import { useState } from 'react'
import { PLACEHOLDER } from '@/utils/imagePaths'

type Props = {
  candidates: string[]
  alt?: string
  width?: number
  height?: number
  rounded?: number
  className?: string
  style?: React.CSSProperties
}

export default function SmartImage({
  candidates,
  alt = '',
  width,
  height,
  rounded,
  className,
  style,
}: Props) {
  // Ensure placeholder is last guard
  const list = (candidates && candidates.length ? candidates : []).concat(PLACEHOLDER)
  const [idx, setIdx] = useState(0)
  const src = list[Math.min(idx, list.length - 1)]

  return (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading="lazy"
      decoding="async"
      draggable={false}
      onError={() => setIdx((i) => Math.min(i + 1, list.length - 1))}
      className={className}
      style={{ borderRadius: rounded ?? 0, display: 'block', ...(style || {}) }}
    />
  )
}