import {
  cloneElement,
  useLayoutEffect,
  useId,
  useRef,
  useState,
  type FocusEvent,
  type MouseEvent,
  type ReactElement,
} from 'react'

type Props = {
  label: string
  children: ReactElement
  disabled?: boolean
  className?: string
}

export function Tooltip({ label, children, disabled, className }: Props) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLSpanElement | null>(null)
  const bubbleRef = useRef<HTMLSpanElement | null>(null)
  const [pos, setPos] = useState<{ left: number; top: number; arrowLeft: number; placement: 'top' | 'bottom' } | null>(null)

  if (!label.trim()) return children

  const el = children as ReactElement<{
    disabled?: boolean
    onMouseEnter?: (e: MouseEvent) => void
    onMouseLeave?: (e: MouseEvent) => void
    onFocus?: (e: FocusEvent) => void
    onBlur?: (e: FocusEvent) => void
  }>

  const childDisabled = Boolean(el.props.disabled)
  const shouldBlock = Boolean(disabled) || childDisabled

  const child = cloneElement(el, {
    'aria-describedby': open ? id : undefined,
    onMouseEnter: (e: MouseEvent) => {
      el.props.onMouseEnter?.(e)
      if (!shouldBlock) setOpen(true)
    },
    onMouseLeave: (e: MouseEvent) => {
      el.props.onMouseLeave?.(e)
      setOpen(false)
    },
    onFocus: (e: FocusEvent) => {
      el.props.onFocus?.(e)
      if (!shouldBlock) setOpen(true)
    },
    onBlur: (e: FocusEvent) => {
      el.props.onBlur?.(e)
      setOpen(false)
    },
  })

  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    const wrap = wrapRef.current
    const bubble = bubbleRef.current
    if (!wrap || !bubble) return

    const margin = 10
    const gap = 10
    const wrapRect = wrap.getBoundingClientRect()
    const bubbleRect = bubble.getBoundingClientRect()

    // Prefer centered above the anchor.
    let left = wrapRect.left + wrapRect.width / 2 - bubbleRect.width / 2
    let top = wrapRect.top - bubbleRect.height - gap
    let placement: 'top' | 'bottom' = 'top'

    // Clamp inside viewport.
    const maxLeft = window.innerWidth - bubbleRect.width - margin
    left = Math.max(margin, Math.min(left, maxLeft))

    // If not enough space above, place below.
    if (top < margin) {
      top = wrapRect.bottom + gap
      placement = 'bottom'
    }
    const maxTop = window.innerHeight - bubbleRect.height - margin
    top = Math.max(margin, Math.min(top, maxTop))

    const anchorCenterX = wrapRect.left + wrapRect.width / 2
    const rawArrowLeft = anchorCenterX - left
    const arrowPad = 14
    const arrowLeft = Math.max(arrowPad, Math.min(rawArrowLeft, bubbleRect.width - arrowPad))

    setPos({ left, top, arrowLeft, placement })
  }, [open, label])

  // Disabled elements often don't receive hover events reliably; wrap them.
  if (childDisabled) {
    return (
      <span
        className={['tooltipWrap', className].filter(Boolean).join(' ')}
        ref={wrapRef}
        tabIndex={-1}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        {child}
        {open ? (
          <span
            id={id}
            role="tooltip"
            className="tooltipBubble"
            ref={bubbleRef}
            data-placement={pos?.placement}
            style={
              pos
                ? ({
                    left: pos.left,
                    top: pos.top,
                    ['--arrow-left' as any]: `${pos.arrowLeft}px`,
                  } as React.CSSProperties)
                : undefined
            }
          >
            {label}
          </span>
        ) : null}
      </span>
    )
  }

  return (
    <span className={['tooltipWrap', className].filter(Boolean).join(' ')} ref={wrapRef}>
      {child}
      {open ? (
        <span
          id={id}
          role="tooltip"
          className="tooltipBubble"
          ref={bubbleRef}
          data-placement={pos?.placement}
          style={
            pos
              ? ({
                  left: pos.left,
                  top: pos.top,
                  ['--arrow-left' as any]: `${pos.arrowLeft}px`,
                } as React.CSSProperties)
              : undefined
          }
        >
          {label}
        </span>
      ) : null}
    </span>
  )
}
