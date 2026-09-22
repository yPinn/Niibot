import { type ReactNode, useLayoutEffect, useRef } from 'react'

import type {
  CommunityOverlayContentType,
  CommunityOverlayPlacement,
  CommunityOverlayTheme,
} from '@/api/communityOverlay'
import { CollectionBinder } from '@/components/community-overlay/CollectionBinder'
import {
  SAMPLE_COLLECTION_BINDER_EVENT,
  SAMPLE_TAROT_CARD_EVENT,
} from '@/components/community-overlay/previewFixtures'
import { TarotCard } from '@/components/community-overlay/TarotCard'
import { Icon, Spinner } from '@/components/primitives'
import { Button, Input } from '@/components/ui'
import { WarningBanner } from '@/components/WarningBanner'

const PLACEMENTS: Array<{
  value: CommunityOverlayPlacement
  label: string
  indicatorClass: string
}> = [
  { value: 'top-left', label: '左上', indicatorClass: 'left-2 top-2' },
  { value: 'top-right', label: '右上', indicatorClass: 'right-2 top-2' },
  { value: 'bottom-left', label: '左下', indicatorClass: 'bottom-2 left-2' },
  { value: 'bottom-right', label: '右下', indicatorClass: 'bottom-2 right-2' },
]

const MOTIONS = [
  { value: 'none' as const, label: '關閉' },
  { value: 'subtle' as const, label: '柔和' },
  { value: 'standard' as const, label: '標準' },
]

const PREVIEW_ALIGNMENT: Record<CommunityOverlayPlacement, string> = {
  'top-left': 'items-start justify-start',
  'top-right': 'items-start justify-end',
  'bottom-left': 'items-end justify-start',
  'bottom-right': 'items-end justify-end',
}

const PREVIEW_CANVAS = { width: 1920, height: 1080 } as const
const PREVIEW_FOCUS = { width: 960, height: 540 } as const
const PREVIEW_FOCUS_OFFSET: Record<CommunityOverlayPlacement, { x: number; y: number }> = {
  'top-left': { x: 0, y: 0 },
  'top-right': { x: PREVIEW_FOCUS.width, y: 0 },
  'bottom-left': { x: 0, y: PREVIEW_FOCUS.height },
  'bottom-right': { x: PREVIEW_FOCUS.width, y: PREVIEW_FOCUS.height },
}

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/

function formatDisplaySeconds(displayMs: number) {
  const seconds = displayMs / 1000
  return Number.isInteger(seconds) ? String(seconds) : seconds.toFixed(1)
}

function luminance(hex: string): number | null {
  if (!HEX_COLOR.test(hex)) return null
  const channels = [1, 3, 5].map(index => Number.parseInt(hex.slice(index, index + 2), 16) / 255)
  const [red, green, blue] = channels.map(value =>
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  )
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

function contrastRatio(foreground: string, background: string): number | null {
  const foregroundLuminance = luminance(foreground)
  const backgroundLuminance = luminance(background)
  if (foregroundLuminance === null || backgroundLuminance === null) return null
  const light = Math.max(foregroundLuminance, backgroundLuminance)
  const dark = Math.min(foregroundLuminance, backgroundLuminance)
  return (light + 0.05) / (dark + 0.05)
}

function ColorControl({
  id,
  label,
  value,
  onChange,
  disabled,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  disabled: boolean
}) {
  const valid = HEX_COLOR.test(value)
  const errorId = `${id}-error`

  return (
    <div className="grid gap-2">
      <label htmlFor={id} className="text-sub font-medium">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          type="color"
          aria-label={`${label}色票`}
          value={HEX_COLOR.test(value) ? value : '#000000'}
          disabled={disabled}
          onChange={event => onChange(event.target.value.toUpperCase())}
          className="h-9 w-12 cursor-pointer rounded-md border bg-background p-1 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Input
          id={id}
          aria-invalid={!valid}
          aria-describedby={valid ? undefined : errorId}
          value={value}
          disabled={disabled}
          maxLength={7}
          spellCheck={false}
          onChange={event => onChange(event.target.value.toUpperCase())}
          className="font-mono uppercase"
        />
      </div>
      {!valid && (
        <p id={errorId} className="text-label text-destructive">
          請輸入 #RRGGBB 格式。
        </p>
      )}
    </div>
  )
}

function PreviewViewport({
  placement,
  draft = false,
  className,
  children,
}: {
  placement: CommunityOverlayPlacement
  draft?: boolean
  className: string
  children: ReactNode
}) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const focusOffset = PREVIEW_FOCUS_OFFSET[placement]

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    const canvas = canvasRef.current
    if (!viewport || !canvas) return

    const updateScale = (observedWidth?: number) => {
      const viewportWidth = observedWidth || viewport.getBoundingClientRect().width
      if (viewportWidth <= 0) return
      const scale = viewportWidth / PREVIEW_FOCUS.width
      canvas.style.left = `${-focusOffset.x * scale}px`
      canvas.style.top = `${-focusOffset.y * scale}px`
      canvas.style.transform = `scale(${scale})`
    }

    updateScale()
    const updateFromLayout = () => updateScale()
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(entries => updateScale(entries[0]?.contentRect.width))
    observer?.observe(viewport)
    if (!observer) window.addEventListener('resize', updateFromLayout)

    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', updateFromLayout)
    }
  }, [focusOffset.x, focusOffset.y])

  return (
    <div
      ref={viewportRef}
      data-testid="theme-preview-viewport"
      data-focus="quarter"
      data-theme-preview={draft ? true : undefined}
      data-placement={placement}
      className={`relative aspect-video w-full overflow-hidden rounded-xl ${className}`}
    >
      <div
        ref={canvasRef}
        data-testid="theme-preview-canvas"
        className="absolute"
        style={{
          width: PREVIEW_CANVAS.width,
          height: PREVIEW_CANVAS.height,
          left: -focusOffset.x,
          top: -focusOffset.y,
          transform: 'scale(1)',
          transformOrigin: 'top left',
        }}
      >
        {children}
      </div>
    </div>
  )
}

interface ThemePreviewProps {
  contentType: CommunityOverlayContentType
  theme: CommunityOverlayTheme
  livePlacement?: CommunityOverlayPlacement
  previewUrl?: string
  previewMode: 'draft' | 'live'
  onPreviewModeChange: (mode: 'draft' | 'live') => void
}

export function ThemePreview({
  contentType,
  theme,
  livePlacement,
  previewUrl,
  previewMode,
  onPreviewModeChange,
}: ThemePreviewProps) {
  const activePlacement =
    previewMode === 'live' ? (livePlacement ?? theme.placement) : theme.placement
  const placementLabel = PLACEMENTS.find(option => option.value === activePlacement)?.label

  return (
    <div data-layout="live-display-theme-preview" className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-label font-semibold">
          {previewMode === 'draft' ? '草稿預覽' : '實際播放'}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-label text-muted-foreground">
            {previewMode === 'draft'
              ? `聚焦${placementLabel} 1/4 畫面`
              : `聚焦${placementLabel}已發布版本`}
          </p>
          {previewMode === 'live' && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => onPreviewModeChange('draft')}
            >
              返回草稿預覽
            </Button>
          )}
        </div>
      </div>

      {previewMode === 'draft' ? (
        <PreviewViewport placement={theme.placement} draft className="bg-muted/40">
          <div className={`flex h-full w-full p-14 ${PREVIEW_ALIGNMENT[theme.placement]}`}>
            <div
              data-preview-content
              data-native-size={contentType === 'checkin' ? '660x400' : '176x295'}
              className={
                contentType === 'checkin'
                  ? 'w-[660px] shrink-0 [&>*]:!w-full [&>*]:!max-w-none'
                  : 'w-44 shrink-0 [&>*]:!w-full [&>*]:!max-w-none'
              }
            >
              {contentType === 'checkin' ? (
                <CollectionBinder
                  key={theme.motion}
                  event={SAMPLE_COLLECTION_BINDER_EVENT}
                  theme={theme}
                  previewLabel="草稿預覽"
                  staticPreview
                />
              ) : (
                <TarotCard
                  key={theme.motion}
                  event={SAMPLE_TAROT_CARD_EVENT}
                  theme={theme}
                  previewLabel="草稿預覽"
                />
              )}
            </div>
          </div>
        </PreviewViewport>
      ) : (
        <PreviewViewport placement={activePlacement} className="border bg-black">
          <div
            aria-hidden="true"
            className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground"
          >
            <Icon icon="fa-solid fa-clapperboard" wrapperClassName="size-6" />
            <span className="text-label">等待測試動畫</span>
          </div>
          {previewUrl && (
            <iframe
              src={previewUrl}
              title={`${contentType === 'checkin' ? '每日簽到' : '每日塔羅'}實際播放`}
              referrerPolicy="no-referrer"
              className="absolute inset-0 block h-full w-full"
            />
          )}
        </PreviewViewport>
      )}
      <p className="mt-2 text-label text-muted-foreground">
        {previewMode === 'draft'
          ? '發布後才會套用至 OBS。'
          : contentType === 'checkin'
            ? '只測試動畫，不會簽到、抽卡或累積天數。'
            : '只測試動畫，不會新增或覆寫抽牌紀錄。'}
      </p>
    </div>
  )
}

interface ThemeEditorProps {
  contentType: CommunityOverlayContentType
  theme: CommunityOverlayTheme
  localDirty: boolean
  hasUnpublishedChanges: boolean
  busy: 'save' | 'publish' | 'reset' | null
  onChange: (theme: CommunityOverlayTheme) => void
  onSave: () => void
  onPublish: () => void
  onReset: () => void
}

export function ThemeEditor({
  contentType,
  theme,
  localDirty,
  hasUnpublishedChanges,
  busy,
  onChange,
  onSave,
  onPublish,
  onReset,
}: ThemeEditorProps) {
  const disabled = busy !== null
  const colorsValid = [theme.surface_color, theme.accent_color, theme.text_color].every(color =>
    HEX_COLOR.test(color)
  )
  const surfaceContrast = contrastRatio(theme.text_color, theme.surface_color)
  const accentContrast = contrastRatio(theme.text_color, theme.accent_color)
  const accentSurfaceContrast = contrastRatio(theme.accent_color, theme.surface_color)
  const lowContrast =
    (surfaceContrast !== null && surfaceContrast < 4.5) ||
    (accentContrast !== null && accentContrast < 4.5)
  const lowAccentSeparation = accentSurfaceContrast !== null && accentSurfaceContrast < 4.5
  return (
    <div data-layout="live-display-theme-editor" className="flex min-w-0 flex-col gap-card">
      <p className="text-label text-muted-foreground">設定只套用到這個頻道。</p>

      <div
        data-layout="live-display-theme-editor-columns"
        className="grid grid-cols-1 gap-section lg:grid-cols-2 lg:items-start"
      >
        <fieldset data-layout-panel="appearance" className="grid gap-section" disabled={disabled}>
          <legend className="mb-2 text-sub font-medium">外觀</legend>
          <div className="grid gap-card sm:grid-cols-3 lg:grid-cols-1 2xl:grid-cols-3">
            <ColorControl
              id="overlay-surface-color"
              label="背景色"
              value={theme.surface_color}
              disabled={disabled}
              onChange={surface_color => onChange({ ...theme, surface_color })}
            />
            <ColorControl
              id="overlay-accent-color"
              label="強調色"
              value={theme.accent_color}
              disabled={disabled}
              onChange={accent_color => onChange({ ...theme, accent_color })}
            />
            <ColorControl
              id="overlay-text-color"
              label="文字色"
              value={theme.text_color}
              disabled={disabled}
              onChange={text_color => onChange({ ...theme, text_color })}
            />
          </div>
          {(lowContrast || lowAccentSeparation) && (
            <WarningBanner>
              {lowContrast && '文字色與背景色、強調色的對比偏低，觀眾可能不易閱讀。'}
              {lowContrast && lowAccentSeparation && ' '}
              {lowAccentSeparation &&
                '強調色與背景色的對比偏低（低於 4.5:1），小字重點可能不易閱讀。'}{' '}
              （僅供參考，不影響儲存）
            </WarningBanner>
          )}
          <label className="grid gap-2 text-sub font-medium">
            <span className="flex justify-between gap-element">
              {contentType === 'tarot' ? '牌框圓角' : '卡片圓角'}{' '}
              <output>{theme.radius_px}px</output>
            </span>
            <input
              type="range"
              aria-label="卡片圓角"
              min={0}
              max={40}
              step={4}
              value={theme.radius_px}
              disabled={disabled}
              onChange={event => onChange({ ...theme, radius_px: Number(event.target.value) })}
              className="h-9 w-full accent-primary"
            />
          </label>
        </fieldset>

        <div data-layout-panel="placement-motion" className="grid gap-section">
          <fieldset disabled={disabled}>
            <legend className="mb-2 text-sub font-medium">位置</legend>
            <div
              role="group"
              aria-label="顯示位置"
              className="grid aspect-video w-full grid-cols-2 grid-rows-2 gap-px overflow-hidden rounded-lg border bg-border"
            >
              {PLACEMENTS.map(option => {
                const selected = theme.placement === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    data-placement-option={option.value}
                    aria-label={option.label}
                    aria-pressed={selected}
                    className={`group relative flex min-h-11 items-center justify-center p-2 text-label font-medium transition-colors focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                      selected
                        ? 'bg-primary/15 text-primary'
                        : 'bg-background text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                    }`}
                    onClick={() => onChange({ ...theme, placement: option.value })}
                  >
                    <span aria-hidden="true">{option.label}</span>
                    <span
                      data-testid={`placement-indicator-${option.value}`}
                      aria-hidden="true"
                      className={`absolute flex h-4 w-10 items-center justify-center rounded-sm border transition-colors ${
                        option.indicatorClass
                      } ${
                        selected
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-muted-foreground/50 bg-muted-foreground/20 group-hover:border-muted-foreground/80 group-hover:bg-muted-foreground/30'
                      }`}
                    >
                      {selected && <Icon icon="fa-solid fa-check" size="xs" />}
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="mt-2 text-label text-muted-foreground">
              預設左下，可避開右下角實況視訊。
            </p>
          </fieldset>

          <fieldset className="grid gap-section" disabled={disabled}>
            <legend className="mb-2 text-sub font-medium">動態</legend>
            <label className="grid gap-2 text-sub font-medium">
              <span className="flex justify-between gap-element">
                顯示時間 <output>{formatDisplaySeconds(theme.display_ms)} 秒</output>
              </span>
              <input
                type="range"
                aria-label="顯示時間"
                min={2000}
                max={15000}
                step={500}
                value={theme.display_ms}
                disabled={disabled}
                onChange={event => onChange({ ...theme, display_ms: Number(event.target.value) })}
                className="h-9 w-full accent-primary"
              />
            </label>
            <div className="grid grid-cols-3 gap-2">
              {MOTIONS.map(option => (
                <Button
                  key={option.value}
                  type="button"
                  size="sm"
                  variant={theme.motion === option.value ? 'default' : 'outline'}
                  aria-pressed={theme.motion === option.value}
                  onClick={() => onChange({ ...theme, motion: option.value })}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </fieldset>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-section">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled || (!localDirty && !hasUnpublishedChanges)}
          onClick={onReset}
        >
          {busy === 'reset' && <Spinner className="mr-1.5" />}
          還原已發布版本
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={disabled || !localDirty || !colorsValid}
            onClick={onSave}
          >
            {busy === 'save' && <Spinner className="mr-1.5" />}
            儲存草稿
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={disabled || localDirty || !hasUnpublishedChanges}
            onClick={onPublish}
          >
            {busy === 'publish' && <Spinner className="mr-1.5" />}
            發布至 OBS
          </Button>
        </div>
      </div>
    </div>
  )
}
