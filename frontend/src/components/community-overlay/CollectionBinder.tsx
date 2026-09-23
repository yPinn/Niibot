import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
} from 'motion/react'

import type {
  CheckinCollectionSnapshot,
  CheckinOwnedCollectionCardSnapshot,
  CommunityOverlayTheme,
} from '@/api/communityOverlay'

import { resolveSameOriginArtwork } from './artwork'
import { CardHologram, getOverlayThemeStyle, MysticCardBackPattern } from './CardVisualPrimitives'
import {
  buildCollectionBinderMotion,
  calculateCardFlightGeometry,
  type CardFlightGeometry,
  COLLECTION_BINDER_PHASES,
  COLLECTION_BINDER_TIMELINE,
} from './collectionBinderMotion'

import styles from './CollectionBinder.module.css'

export interface CollectionBinderEvent {
  actor_display_name: string | null
  payload: {
    total_days: number
    checkin_date: string
    collection: CheckinCollectionSnapshot
    preview?: boolean
  }
}

interface CollectionBinderProps {
  event: CollectionBinderEvent
  theme: CommunityOverlayTheme
  previewLabel?: string
  staticPreview?: boolean
}

const COLLECTION_PAGE_SIZE = 9

function catalogPosition(number: string): number {
  const parsed = /^\d+$/.test(number) ? Number.parseInt(number, 10) : 1
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1
}

function catalogNumber(position: number): string {
  return String(position).padStart(3, '0')
}

function SafeCardArtwork({
  name,
  urls,
  testId = 'card-artwork',
  className = styles.artwork,
  placeholderClassName = styles.artworkPlaceholder,
}: {
  name: string
  urls: Array<string | null>
  testId?: string
  className?: string
  placeholderClassName?: string
}) {
  const artworkUrl = urls.map(url => resolveSameOriginArtwork(url)).find(Boolean) ?? null
  const [failed, setFailed] = useState(false)

  if (!artworkUrl || failed) {
    return (
      <span
        data-testid={testId}
        className={placeholderClassName}
        role="img"
        aria-label={`${name}圖片尚未提供`}
      >
        <span className={styles.placeholderMark} aria-hidden="true" />
      </span>
    )
  }

  return (
    <img
      data-testid={testId}
      className={className}
      src={artworkUrl}
      alt={name}
      decoding="async"
      draggable={false}
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  )
}

export function CollectionBinder({
  event,
  theme,
  previewLabel,
  staticPreview = false,
}: CollectionBinderProps) {
  const prefersReducedMotion = useReducedMotion()
  const { collection } = event.payload
  const { card, rarity, progress } = collection
  const selectedPosition = Math.min(catalogPosition(card.number), progress.total_cards)
  const pageIndex = Math.floor((selectedPosition - 1) / COLLECTION_PAGE_SIZE)
  const pageStart = pageIndex * COLLECTION_PAGE_SIZE + 1
  const pageCount = Math.max(1, Math.ceil(progress.total_cards / COLLECTION_PAGE_SIZE))
  const fallbackItem: CheckinOwnedCollectionCardSnapshot = {
    card,
    rarity,
    copy_count: collection.copy_count,
  }
  const suppliedInventory = collection.owned_cards?.length ? collection.owned_cards : [fallbackItem]
  const inventory = suppliedInventory.some(item => item.card.id === card.id)
    ? suppliedInventory
    : [...suppliedInventory, fallbackItem]
  const inventoryByPosition = new Map(
    inventory.map(item => [catalogPosition(item.card.number), item] as const)
  )
  inventoryByPosition.set(
    selectedPosition,
    inventory.find(item => item.card.id === card.id) ?? fallbackItem
  )
  const actor = event.actor_display_name || '觀眾'
  const reveal = buildCollectionBinderMotion(theme, Boolean(prefersReducedMotion), staticPreview)
  const themeStyle = getOverlayThemeStyle(theme)
  const preview = previewLabel || event.payload.preview
  const rarityEffect = rarity.effect_intensity >= 50
  const timelineProgress = useMotionValue(0)
  const subtle = theme.motion === 'subtle'
  const bookRef = useRef<HTMLDivElement>(null)
  const cardOriginRef = useRef<HTMLSpanElement>(null)
  const slotCardRef = useRef<HTMLSpanElement>(null)
  const measurementFrameRef = useRef<number | null>(null)
  const canMeasureFlightRef = useRef(reveal.disabled)
  const hasMeasuredFlightRef = useRef(false)
  const [flightGeometry, setFlightGeometry] = useState<CardFlightGeometry | null>(null)
  const sceneOpacity = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.sceneOpacity.input,
    COLLECTION_BINDER_TIMELINE.sceneOpacity.output
  )
  const sceneY = useTransform(timelineProgress, COLLECTION_BINDER_TIMELINE.sceneY.input, [
    subtle ? 12 : 28,
    0,
    0,
  ])
  const sceneScale = useTransform(timelineProgress, COLLECTION_BINDER_TIMELINE.sceneScale.input, [
    subtle ? 0.98 : 0.92,
    1,
    1,
  ])
  const bookX = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.bookX.input,
    COLLECTION_BINDER_TIMELINE.bookX.output
  )
  const coverRotateY = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.coverRotateY.input,
    COLLECTION_BINDER_TIMELINE.coverRotateY.output
  )
  const printOpacity = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.printOpacity.input,
    COLLECTION_BINDER_TIMELINE.printOpacity.output
  )
  const printScale = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.printScale.input,
    COLLECTION_BINDER_TIMELINE.printScale.output
  )
  const cardOpacity = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.cardOpacity.input,
    COLLECTION_BINDER_TIMELINE.cardOpacity.output
  )
  const slotCardOpacity = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.slotCardOpacity.input,
    COLLECTION_BINDER_TIMELINE.slotCardOpacity.output
  )
  const cardTravel = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.cardTravel.input,
    COLLECTION_BINDER_TIMELINE.cardTravel.output
  )
  const cardX = useTransform(cardTravel, [0, 1], [0, flightGeometry?.x ?? 0])
  const cardY = useTransform(cardTravel, [0, 1], [0, flightGeometry?.y ?? 0])
  const featuredCardScale = subtle
    ? COLLECTION_BINDER_TIMELINE.cardScale.subtle
    : COLLECTION_BINDER_TIMELINE.cardScale.standard
  const cardScale = useTransform(timelineProgress, COLLECTION_BINDER_TIMELINE.cardTravel.input, [
    ...featuredCardScale,
    flightGeometry?.scale ?? 1,
    flightGeometry?.scale ?? 1,
  ])
  const cardFlipRotateY = useTransform(
    timelineProgress,
    COLLECTION_BINDER_TIMELINE.cardFlipRotateY.input,
    COLLECTION_BINDER_TIMELINE.cardFlipRotateY.output
  )

  const measureCardFlight = useCallback(() => {
    const bookElement = bookRef.current
    const originElement = cardOriginRef.current
    const targetElement = slotCardRef.current
    if (!bookElement || !originElement || !targetElement) return

    const bookRect = bookElement.getBoundingClientRect()
    const originRect = originElement.getBoundingClientRect()
    const targetRect = targetElement.getBoundingClientRect()
    if (originRect.width <= 0 || originRect.height <= 0 || targetRect.width <= 0) return

    const viewportScale = bookElement.offsetWidth > 0 ? bookRect.width / bookElement.offsetWidth : 1
    const next = calculateCardFlightGeometry(bookRect, originRect, targetRect, viewportScale)
    setFlightGeometry(previous => {
      if (
        previous &&
        Math.abs(previous.left - next.left) < 0.25 &&
        Math.abs(previous.top - next.top) < 0.25 &&
        Math.abs(previous.width - next.width) < 0.25 &&
        Math.abs(previous.height - next.height) < 0.25 &&
        Math.abs(previous.x - next.x) < 0.25 &&
        Math.abs(previous.y - next.y) < 0.25 &&
        Math.abs(previous.scale - next.scale) < 0.002
      ) {
        return previous
      }
      return next
    })
  }, [])

  const queueCardFlightMeasurement = useCallback(() => {
    if (typeof requestAnimationFrame === 'undefined') {
      measureCardFlight()
      return
    }
    if (measurementFrameRef.current !== null) {
      cancelAnimationFrame(measurementFrameRef.current)
    }
    measurementFrameRef.current = requestAnimationFrame(() => {
      measurementFrameRef.current = null
      measureCardFlight()
    })
  }, [measureCardFlight])

  useMotionValueEvent(timelineProgress, 'change', latest => {
    const bookIsOpen =
      latest >= COLLECTION_BINDER_PHASES.openEnd && latest < COLLECTION_BINDER_PHASES.closeStart
    canMeasureFlightRef.current = bookIsOpen
    if (bookIsOpen && !hasMeasuredFlightRef.current) {
      hasMeasuredFlightRef.current = true
      queueCardFlightMeasurement()
    }
  })

  useLayoutEffect(() => {
    canMeasureFlightRef.current = reveal.disabled
    if (reveal.disabled) {
      hasMeasuredFlightRef.current = true
      queueCardFlightMeasurement()
    }

    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            if (canMeasureFlightRef.current) queueCardFlightMeasurement()
          })
    if (bookRef.current) observer?.observe(bookRef.current)
    if (cardOriginRef.current) observer?.observe(cardOriginRef.current)
    if (slotCardRef.current) observer?.observe(slotCardRef.current)

    return () => {
      observer?.disconnect()
      if (measurementFrameRef.current !== null) {
        cancelAnimationFrame(measurementFrameRef.current)
        measurementFrameRef.current = null
      }
    }
  }, [queueCardFlightMeasurement, reveal.disabled])

  useEffect(() => {
    timelineProgress.stop()
    timelineProgress.set(0)
    hasMeasuredFlightRef.current = reveal.disabled
    canMeasureFlightRef.current = reveal.disabled
    if (reveal.disabled) return
    const playback = animate(timelineProgress, 1, {
      duration: reveal.durationSeconds,
      ease: 'linear',
    })
    return () => playback.stop()
  }, [reveal.disabled, reveal.durationSeconds, timelineProgress])

  return (
    <motion.section
      role="status"
      aria-label={`${actor} 的卡冊：獲得${rarity.label}卡${card.name}`}
      aria-live="polite"
      aria-atomic="true"
      data-overlay-card
      data-testid="collection-binder"
      data-animation-sequence="closed open card insert close"
      data-motion={theme.motion}
      data-motion-state={reveal.disabled ? 'final' : 'staged'}
      data-result={collection.is_new ? 'new' : 'duplicate'}
      className={styles.scene}
      style={{
        ...themeStyle,
        opacity: reveal.disabled ? 1 : sceneOpacity,
        y: reveal.disabled ? 0 : sceneY,
        scale: reveal.disabled ? 1 : sceneScale,
      }}
      exit={reveal.sceneExit}
    >
      <motion.div
        ref={bookRef}
        data-testid="binder-book"
        data-phase="closed open close"
        className={styles.book}
        style={{ x: reveal.disabled ? '0%' : bookX }}
        aria-hidden="true"
      >
        <div data-testid="binder-leaf-stack" className={styles.leafStack}>
          <div data-testid="binder-pages" data-phase="open close" className={styles.pages}>
            <div data-testid="binder-right-page" className={`${styles.page} ${styles.rightPage}`}>
              <div
                data-testid="binder-card-stage"
                data-phase="card"
                data-presentation="featured"
                className={styles.cardSlot}
              >
                <motion.span
                  data-testid="binder-print"
                  data-phase="print"
                  className={styles.printAura}
                  style={{
                    opacity: reveal.disabled ? 0 : printOpacity,
                    scale: reveal.disabled ? 1 : printScale,
                  }}
                  aria-hidden="true"
                />
                <span
                  ref={cardOriginRef}
                  data-testid="binder-card-origin"
                  className={styles.cardOrigin}
                  aria-hidden="true"
                />
              </div>

              <div className={styles.result}>
                <strong>{collection.is_new ? 'NEW' : `×${collection.copy_count}`}</strong>
              </div>
            </div>
          </div>

          <motion.div
            data-testid="binder-cover"
            data-phase="closed open close"
            className={styles.cover}
            style={{ rotateY: reveal.disabled ? -180 : coverRotateY }}
          >
            <div
              data-testid="binder-cover-outer"
              className={`${styles.coverFace} ${styles.coverOuter}`}
              aria-hidden="true"
            >
              <div className={styles.coverSigil}>
                <span />
              </div>
              <strong>ARCANA INDEX</strong>
              <small>COLLECTION RECORD</small>
            </div>

            <div
              data-testid="binder-cover-inner"
              className={`${styles.coverFace} ${styles.coverInner}`}
            >
              <div data-testid="binder-left-page" className={`${styles.page} ${styles.leftPage}`}>
                <div className={styles.slotGrid} aria-hidden="true">
                  {Array.from({ length: COLLECTION_PAGE_SIZE }, (_, index) => {
                    const position = pageStart + index
                    const isCatalogSlot = position <= progress.total_cards
                    const isTarget = position === selectedPosition
                    const item = isCatalogSlot ? inventoryByPosition.get(position) : undefined
                    const number = isCatalogSlot ? catalogNumber(position) : null
                    const slotArtwork = item ? (
                      <SafeCardArtwork
                        key={
                          item.card.artwork.portrait_url ??
                          item.card.artwork.square_url ??
                          item.card.artwork.backdrop_url ??
                          `missing-${position}`
                        }
                        name={item.card.name}
                        urls={[
                          item.card.artwork.portrait_url,
                          item.card.artwork.square_url,
                          item.card.artwork.backdrop_url,
                        ]}
                        testId={`binder-slot-artwork-${number}`}
                        className={styles.slotArtwork}
                        placeholderClassName={styles.slotArtworkPlaceholder}
                      />
                    ) : null

                    return (
                      <span
                        key={position}
                        data-testid={isTarget ? 'binder-slot' : undefined}
                        data-phase={isTarget ? 'insert' : undefined}
                        data-slot-position={position}
                        data-catalog-number={number ?? undefined}
                        className={`${styles.miniSlot} ${
                          isTarget ? styles.targetSlot : ''
                        } ${isCatalogSlot ? '' : styles.inactiveSlot}`}
                      >
                        {item &&
                          (isTarget ? (
                            <motion.span
                              ref={slotCardRef}
                              data-testid="binder-slot-card"
                              data-phase="handoff close"
                              data-card-face="front"
                              data-rarity={item.rarity.key}
                              className={styles.slotCard}
                              style={{ opacity: reveal.disabled ? 1 : slotCardOpacity }}
                            >
                              {slotArtwork}
                              {item.copy_count > 1 && (
                                <span
                                  data-testid={`binder-slot-copy-${number}`}
                                  className={styles.slotCopyBadge}
                                >
                                  ×{item.copy_count}
                                </span>
                              )}
                            </motion.span>
                          ) : (
                            <span
                              data-card-face="front"
                              data-rarity={item.rarity.key}
                              className={styles.slotCard}
                            >
                              {slotArtwork}
                              {item.copy_count > 1 && (
                                <span
                                  data-testid={`binder-slot-copy-${number}`}
                                  className={styles.slotCopyBadge}
                                >
                                  ×{item.copy_count}
                                </span>
                              )}
                            </span>
                          ))}
                      </span>
                    )
                  })}
                </div>
                <div data-testid="binder-progress" className={styles.progress}>
                  {pageCount > 1 && (
                    <span data-testid="binder-page-indicator">
                      {pageIndex + 1} / {pageCount}
                    </span>
                  )}
                  <strong>
                    {progress.unique_cards} / {progress.total_cards}
                  </strong>
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        <motion.article
          data-testid="collection-card"
          data-phase="card insert"
          data-rarity={rarity.key}
          data-geometry={flightGeometry ? 'measured' : 'pending'}
          className={`${styles.collectionCard} ${styles.flightCard}`}
          style={{
            left: flightGeometry?.left ?? 0,
            top: flightGeometry?.top ?? 0,
            width: flightGeometry?.width ?? 0,
            height: flightGeometry?.height ?? 0,
            opacity: flightGeometry ? (reveal.disabled ? 1 : cardOpacity) : 0,
            x: reveal.disabled ? 0 : cardX,
            y: reveal.disabled ? 0 : cardY,
            scale: reveal.disabled ? 1 : cardScale,
          }}
        >
          <motion.div
            className={styles.cardFlipper}
            style={{ rotateY: reveal.disabled ? 0 : cardFlipRotateY }}
          >
            <div className={`${styles.cardFace} ${styles.cardBack}`} aria-hidden="true">
              <MysticCardBackPattern />
            </div>
            <div className={`${styles.cardFace} ${styles.cardFront}`}>
              <div className={styles.cardHeading}>
                <span>{card.number}</span>
                <span className={styles.rarity}>{rarity.label}</span>
              </div>
              <div className={styles.artworkFrame}>
                <SafeCardArtwork
                  key={
                    card.artwork.portrait_url ??
                    card.artwork.square_url ??
                    card.artwork.backdrop_url ??
                    'missing'
                  }
                  name={card.name}
                  urls={[
                    card.artwork.portrait_url,
                    card.artwork.square_url,
                    card.artwork.backdrop_url,
                  ]}
                />
                <CardHologram animated={!reveal.disabled && rarityEffect} />
              </div>
              <div className={styles.cardCaption}>
                <strong className={styles.cardName}>{card.name}</strong>
                <span className={styles.setName}>{collection.set.name}</span>
              </div>
            </div>
          </motion.div>
        </motion.article>

        <div className={styles.spine} aria-hidden="true" />
      </motion.div>

      {preview && (
        <span className={styles.previewBadge} data-anchor="top-right">
          {previewLabel || 'PREVIEW'}
        </span>
      )}
    </motion.section>
  )
}
