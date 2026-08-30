import type { CommunityOverlayPlacement, CommunityOverlayTheme } from '@/api/communityOverlay'
import { CheckinCard } from '@/components/community-overlay/CheckinCard'
import { Icon, Spinner } from '@/components/primitives'
import { Badge, Button, Input } from '@/components/ui'

const SAMPLE_EVENT = {
  actor_display_name: 'NiibotFan',
  payload: {
    total_days: 8,
    checkin_date: '2026-08-31',
  },
}

const PLACEMENTS: Array<{ value: CommunityOverlayPlacement; label: string }> = [
  { value: 'top-left', label: '左上' },
  { value: 'top-right', label: '右上' },
  { value: 'bottom-left', label: '左下' },
  { value: 'bottom-right', label: '右下' },
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

const PREVIEW_ORIGIN: Record<CommunityOverlayPlacement, string> = {
  'top-left': 'origin-top-left',
  'top-right': 'origin-top-right',
  'bottom-left': 'origin-bottom-left',
  'bottom-right': 'origin-bottom-right',
}

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/

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
      <label htmlFor={id} className="text-label font-medium">
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

interface ThemeEditorProps {
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
  const lowAccentSeparation = accentSurfaceContrast !== null && accentSurfaceContrast < 3
  const themeValid =
    colorsValid &&
    surfaceContrast !== null &&
    surfaceContrast >= 4.5 &&
    accentContrast !== null &&
    accentContrast >= 4.5 &&
    accentSurfaceContrast !== null &&
    accentSurfaceContrast >= 3
  const status = localDirty ? '尚未儲存' : hasUnpublishedChanges ? '草稿未發布' : '與已發布同步'

  return (
    <div className="grid gap-card xl:grid-cols-[minmax(20rem,0.82fr)_minmax(32rem,1.18fr)]">
      <div className="flex min-w-0 flex-col gap-section">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-content font-semibold">簽到集點卡</h3>
            <p className="text-label text-muted-foreground">修改只會影響這個頻道。</p>
          </div>
          <Badge variant={localDirty || hasUnpublishedChanges ? 'secondary' : 'outline'}>
            {status}
          </Badge>
        </div>

        <fieldset className="grid gap-3" disabled={disabled}>
          <legend className="mb-2 text-label font-semibold">配色</legend>
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
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
          {lowContrast && (
            <p role="status" className="flex items-start gap-2 text-label text-destructive">
              <Icon icon="fa-solid fa-circle-exclamation" className="mt-0.5" />
              文字色需與背景色及強調色皆達 4.5:1 對比，調整後才能儲存。
            </p>
          )}
          {lowAccentSeparation && (
            <p role="status" className="flex items-start gap-2 text-label text-destructive">
              <Icon icon="fa-solid fa-circle-exclamation" className="mt-0.5" />
              強調色與背景色需達 3:1 對比，調整後才能儲存。
            </p>
          )}
        </fieldset>

        <fieldset disabled={disabled}>
          <legend className="mb-2 text-label font-semibold">顯示位置</legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-2 2xl:grid-cols-4">
            {PLACEMENTS.map(option => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={theme.placement === option.value ? 'default' : 'outline'}
                aria-pressed={theme.placement === option.value}
                onClick={() => onChange({ ...theme, placement: option.value })}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <label className="grid gap-2 text-label font-semibold">
            <span className="flex justify-between gap-3">
              卡片圓角 <output>{theme.radius_px}px</output>
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
          <label className="grid gap-2 text-label font-semibold">
            <span className="flex justify-between gap-3">
              顯示時間 <output>{(theme.display_ms / 1000).toFixed(1)} 秒</output>
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
        </div>

        <fieldset disabled={disabled}>
          <legend className="mb-2 text-label font-semibold">動畫強度</legend>
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

        <div className="flex flex-wrap gap-2 border-t pt-section">
          <Button type="button" disabled={disabled || !localDirty || !themeValid} onClick={onSave}>
            {busy === 'save' && <Spinner className="mr-1.5" />}
            儲存草稿
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={disabled || localDirty || !hasUnpublishedChanges}
            onClick={onPublish}
          >
            {busy === 'publish' && <Spinner className="mr-1.5" />}
            發布至 OBS
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={disabled || (!localDirty && !hasUnpublishedChanges)}
            onClick={onReset}
          >
            {busy === 'reset' && <Spinner className="mr-1.5" />}
            還原已發布版本
          </Button>
        </div>
      </div>

      <div className="min-w-0">
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-label font-semibold">草稿預覽</p>
          <p className="text-label text-muted-foreground">示意 1920 × 1080 安全區</p>
        </div>
        <div
          data-theme-preview
          data-placement={theme.placement}
          className={`flex h-72 overflow-hidden rounded-xl bg-muted/40 p-4 sm:h-auto sm:aspect-video sm:min-h-72 sm:p-6 ${PREVIEW_ALIGNMENT[theme.placement]}`}
        >
          <div
            className={`${PREVIEW_ORIGIN[theme.placement]} scale-[0.68] sm:scale-[0.78] lg:scale-[0.84] 2xl:scale-100`}
          >
            <CheckinCard
              key={theme.motion}
              event={SAMPLE_EVENT}
              theme={theme}
              previewLabel="草稿預覽"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
