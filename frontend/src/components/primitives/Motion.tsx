/**
 * Semantic motion wrapper components.
 *
 * Every component maps to a variant defined in @/lib/motion and supports
 * scroll-triggered animation via `inView` prop (uses viewport token).
 *
 * Quick reference:
 *   <FadeIn>         — opacity fade
 *   <FadeInZoom>     — fade + scale (avatars, media)
 *   <SlideUp>        — fade + slide up (large offset)
 *   <SlideUpSm>      — fade + slide up (small offset, headings)
 *   <SlideInLeft>    — fade + slide from left
 *   <SlideInRight>   — fade + slide from right
 *   <Stagger>        — stagger container
 *   <StaggerItem>    — item inside <Stagger>
 *   <Reveal>         — generic — pass any `variant` key
 */
import { AnimatePresence, motion, type Variants } from 'motion/react'
import { type HTMLMotionProps } from 'motion/react'

import {
  fadeIn,
  fadeInZoom,
  slideInLeft,
  slideInRight,
  slideUp,
  slideUpSm,
  staggerContainer,
  staggerItem,
  type VariantKey,
  variants,
  viewport,
} from '@/lib/motion'

// ── Shared prop types ──────────────────────────────────────────────────────

interface BaseProps extends Omit<
  HTMLMotionProps<'div'>,
  | 'onAnimationStart'
  | 'onDrag'
  | 'onDragEnd'
  | 'onDragStart'
  | 'onDragEnter'
  | 'onDragExit'
  | 'onDragLeave'
  | 'onDragOver'
  | 'onDrop'
> {
  /** Trigger animation when element enters the viewport (default: false = animate on mount) */
  inView?: boolean
  /** Delay before animation starts, in seconds */
  delay?: number
  children?: React.ReactNode
}

function buildAnimateProps(variant: Variants, inView: boolean, delay?: number) {
  const delayProp = delay ? { transition: { delay } } : {}

  if (inView) {
    return {
      variants: variant,
      initial: 'hidden',
      whileInView: 'visible',
      viewport,
      ...delayProp,
    }
  }

  return {
    variants: variant,
    initial: 'hidden',
    animate: 'visible',
    ...delayProp,
  }
}

// ── Primitive wrappers ─────────────────────────────────────────────────────

export function FadeIn({ inView = false, delay, children, ...props }: BaseProps) {
  return (
    <motion.div {...buildAnimateProps(fadeIn, inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

export function FadeInZoom({ inView = false, delay, children, ...props }: BaseProps) {
  return (
    <motion.div {...buildAnimateProps(fadeInZoom, inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

export function SlideUp({ inView = false, delay, children, ...props }: BaseProps) {
  return (
    <motion.div {...buildAnimateProps(slideUp, inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

export function SlideUpSm({ inView = false, delay, children, ...props }: BaseProps) {
  return (
    <motion.div {...buildAnimateProps(slideUpSm, inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

export function SlideInLeft({ inView = false, delay, children, ...props }: BaseProps) {
  return (
    <motion.div {...buildAnimateProps(slideInLeft, inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

export function SlideInRight({ inView = false, delay, children, ...props }: BaseProps) {
  return (
    <motion.div {...buildAnimateProps(slideInRight, inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

// ── Stagger ────────────────────────────────────────────────────────────────

interface StaggerProps extends Omit<BaseProps, 'delay'> {
  /** Delay between each child (seconds, default 0.075) */
  staggerChildren?: number
  /** Delay before the first child starts (seconds, default 0) */
  delayChildren?: number
}

export function Stagger({
  inView = false,
  staggerChildren = 0.075,
  delayChildren = 0,
  children,
  ...props
}: StaggerProps) {
  const containerVariant = staggerContainer(staggerChildren, delayChildren)

  const animateProps = inView
    ? {
        variants: containerVariant,
        initial: 'hidden',
        whileInView: 'visible',
        viewport,
      }
    : {
        variants: containerVariant,
        initial: 'hidden',
        animate: 'visible',
      }

  return (
    <motion.div {...animateProps} {...props}>
      {children}
    </motion.div>
  )
}

export function StaggerItem({ children, ...props }: Omit<BaseProps, 'inView' | 'delay'>) {
  return (
    <motion.div variants={staggerItem} {...props}>
      {children}
    </motion.div>
  )
}

// ── Generic Reveal ─────────────────────────────────────────────────────────

interface RevealProps extends BaseProps {
  /** Which named variant to use (from @/lib/motion variants map) */
  variant?: VariantKey
}

export function Reveal({
  variant = 'fadeIn',
  inView = false,
  delay,
  children,
  ...props
}: RevealProps) {
  return (
    <motion.div {...buildAnimateProps(variants[variant], inView, delay)} {...props}>
      {children}
    </motion.div>
  )
}

// ── AnimatePresence re-export for convenience ──────────────────────────────
export { AnimatePresence }
