/**
 * Global animation tokens and variants for Motion (motion/react).
 *
 * Usage:
 *   import { variants, duration, ease, viewport } from '@/lib/motion'
 *   <motion.div variants={variants.slideUp} initial="hidden" animate="visible" />
 *
 * Or use the semantic wrapper components from @/components/ui/motion:
 *   <FadeIn>, <SlideUp>, <Stagger>, <StaggerItem>, <Reveal>
 */
import { type Variants } from 'motion/react'

// ── Duration Tokens (seconds) ──────────────────────────────────────────────
export const duration = {
  fast: 0.15,
  normal: 0.25,
  slow: 0.45,
} as const

// ── Easing Tokens ─────────────────────────────────────────────────────────
export const ease = {
  /** Standard Material Design curve — suitable for most transitions */
  smooth: [0.4, 0, 0.2, 1] as [number, number, number, number],
  /** Deceleration curve — elements entering the screen */
  out: [0, 0, 0.2, 1] as [number, number, number, number],
  /** Spring — for interactive / bouncy feel */
  spring: { type: 'spring', stiffness: 380, damping: 28 } as const,
} as const

// ── Viewport Config (scroll-triggered, fires once) ─────────────────────────
export const viewport = {
  once: true,
  margin: '-60px',
} as const

// ── Base Variants ──────────────────────────────────────────────────────────

/** Simple opacity fade */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: duration.normal, ease: ease.smooth },
  },
}

/** Fade + scale-up (ideal for avatars / hero media) */
export const fadeInZoom: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: duration.slow, ease: ease.smooth },
  },
}

/** Fade + slide up — large offset (hero text, section intros) */
export const slideUp: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: duration.normal, ease: ease.out },
  },
}

/** Fade + slide up — small offset (headings, labels) */
export const slideUpSm: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: duration.fast, ease: ease.out },
  },
}

/** Fade + slide in from left */
export const slideInLeft: Variants = {
  hidden: { opacity: 0, x: -20 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: duration.normal, ease: ease.out },
  },
}

/** Fade + slide in from right */
export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 20 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: duration.normal, ease: ease.out },
  },
}

// ── Stagger Container ──────────────────────────────────────────────────────

/**
 * Returns a container variant that staggers its children.
 * Pair with `staggerItem` on each child.
 *
 * @param staggerChildren  Delay between each child (default 0.075 s)
 * @param delayChildren    Initial delay before the first child (default 0)
 */
export function staggerContainer(staggerChildren = 0.075, delayChildren = 0): Variants {
  return {
    hidden: {},
    visible: {
      transition: { staggerChildren, delayChildren },
    },
  }
}

/** Default item variant used inside a stagger container */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: duration.normal, ease: ease.out },
  },
}

// ── Convenience re-export (named map for variant picker props) ─────────────
export const variants = {
  fadeIn,
  fadeInZoom,
  slideUp,
  slideUpSm,
  slideInLeft,
  slideInRight,
  staggerItem,
} as const

export type VariantKey = keyof typeof variants
