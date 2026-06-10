import { useCallback, useMemo, useRef, useState } from 'react'

import {
  Button,
  Input,
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Slider,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { cn } from '@/lib/utils'

import { CrosshairSVG } from './CrosshairPreview'
import {
  COLOR_MAP,
  decodeValorantCrosshair,
  encodeValorantCrosshair,
  SNIPER_DEFAULTS,
  type ValorantCrosshairParams,
  type ValorantSniperParams,
} from './valorantDecode'

// ─── Colour palette ────────────────────────────────────────────────────────────

const COLOR_LABELS: Record<number, string> = {
  0: '白色',
  1: '綠色',
  2: '黃綠',
  3: '綠黃',
  4: '黃色',
  5: '青色',
  6: '粉紅',
  7: '紅色',
}

const PRESET_COLORS = Object.entries(COLOR_MAP).map(([i, hex]) => {
  const idx = parseInt(i)
  return { idx, hex, label: COLOR_LABELS[idx] ?? hex }
})

const PRESET_HEX_SET = new Set(PRESET_COLORS.map(p => p.hex))

// ─── Primitives ────────────────────────────────────────────────────────────────

function ToggleRow({
  label,
  checked,
  onCheckedChange,
  disabled,
  onLabel = '開啟',
  offLabel = '關閉',
}: {
  label: string
  checked: boolean
  onCheckedChange: (v: boolean) => void
  disabled?: boolean
  onLabel?: string
  offLabel?: string
}) {
  return (
    <div
      className={cn(
        'flex select-none items-center justify-between py-element',
        disabled && 'opacity-40'
      )}
    >
      <span className="text-sub text-muted-foreground">{label}</span>
      <div className="flex overflow-hidden rounded border">
        <button
          type="button"
          onClick={() => !disabled && onCheckedChange(true)}
          className={cn(
            'px-3 py-1 text-sub transition-colors',
            checked ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50'
          )}
        >
          {onLabel}
        </button>
        <button
          type="button"
          onClick={() => !disabled && onCheckedChange(false)}
          className={cn(
            'border-l px-3 py-1 text-sub transition-colors',
            !checked ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50'
          )}
        >
          {offLabel}
        </button>
      </div>
    </div>
  )
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
  disabled,
  display,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  disabled?: boolean
  display?: (v: number) => string
}) {
  return (
    <div
      className={cn(
        'select-none space-y-element py-element',
        disabled && 'pointer-events-none opacity-40'
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-sub text-muted-foreground">{label}</span>
        <span className="min-w-10 text-right text-sub tabular-nums">
          {display ? display(value) : value}
        </span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={([v]) => onChange(v)}
        disabled={disabled}
      />
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-element text-label font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </p>
  )
}

function AdjustSection({ children }: { children: React.ReactNode }) {
  return <div className="border-t px-page-lg py-page">{children}</div>
}

// ─── Colour picker ──────────────────────────────────────────────────────────────

function ColorPicker({ value, onChange }: { value: string; onChange: (hex: string) => void }) {
  const colorInputRef = useRef<HTMLInputElement>(null)
  const [inputText, setInputText] = useState(value)
  const [prevValue, setPrevValue] = useState(value)

  // Render-phase sync: when the external `value` prop changes (e.g. preset swatch clicked),
  // reset inputText without a useEffect. React re-renders immediately and discards this pass.
  if (prevValue !== value) {
    setPrevValue(value)
    setInputText(value)
  }

  function handleTextChange(raw: string) {
    setInputText(raw)
    if (/^#[0-9A-Fa-f]{6}$/.test(raw)) onChange(raw.toUpperCase())
  }

  const safeColor = /^#[0-9A-Fa-f]{6}$/.test(value) ? value : '#FFFFFF'
  const isCustom = !PRESET_HEX_SET.has(value)

  return (
    <div className="flex flex-wrap items-center gap-element">
      {/* idx 2 (黃綠) and 3 (綠黃) omitted — absent from the in-game quick-picker */}
      {PRESET_COLORS.filter(p => p.idx !== 2 && p.idx !== 3).map(({ idx, hex, label }) => (
        <Tooltip key={idx}>
          <TooltipTrigger asChild>
            <button
              onClick={() => onChange(hex)}
              className={cn(
                'size-7 select-none rounded border-2 transition-all',
                value === hex
                  ? 'scale-110 border-primary'
                  : 'border-transparent hover:border-muted-foreground/40'
              )}
              style={{ background: hex === '#FFFFFF' ? '#e5e5e5' : hex }}
            />
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      ))}

      <div className="h-5 w-px shrink-0 bg-border" />

      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => colorInputRef.current?.click()}
            className={cn(
              'size-7 select-none shrink-0 rounded border-2 transition-all hover:border-muted-foreground/60',
              isCustom ? 'scale-110 border-primary' : 'border-muted-foreground/30'
            )}
            style={{ background: safeColor }}
          />
        </TooltipTrigger>
        <TooltipContent>開啟調色盤</TooltipContent>
      </Tooltip>
      <input
        ref={colorInputRef}
        type="color"
        value={safeColor}
        onChange={e => onChange(e.target.value.toUpperCase())}
        className="sr-only"
        tabIndex={-1}
      />
      <Input
        type="text"
        value={inputText}
        onChange={e => handleTextChange(e.target.value)}
        placeholder="#RRGGBB"
        maxLength={7}
        className="h-7 w-24 font-mono text-sub"
      />
    </div>
  )
}

// ─── Inner / Outer lines sub-panel ─────────────────────────────────────────────

const INNER_KEYS = {
  show: 'showInnerLines',
  opacity: 'innerOpacity',
  linked: 'innerLengthNotLinked',
  length: 'innerLength',
  vLen: 'innerVerticalLength',
  thick: 'innerThickness',
  offset: 'innerOffset',
  fe: 'innerFiringError',
  fem: 'innerFiringErrorMultiplier',
  me: 'innerMovementError',
  mem: 'innerMovementErrorMultiplier',
} as const

const OUTER_KEYS = {
  show: 'showOuterLines',
  opacity: 'outerOpacity',
  linked: 'outerLengthNotLinked',
  length: 'outerLength',
  vLen: 'outerVerticalLength',
  thick: 'outerThickness',
  offset: 'outerOffset',
  fe: 'outerFiringError',
  fem: 'outerFiringErrorMultiplier',
  me: 'outerMovementError',
  mem: 'outerMovementErrorMultiplier',
} as const

function LinesPanel({
  prefix,
  label,
  show,
  opacity,
  lengthNotLinked,
  length,
  verticalLength,
  thickness,
  offset,
  firingError,
  firingErrorMultiplier,
  movementError,
  movementErrorMultiplier,
  onChange,
}: {
  prefix: 'inner' | 'outer'
  label: string
  show: boolean
  opacity: number
  lengthNotLinked: boolean
  length: number
  verticalLength: number
  thickness: number
  offset: number
  firingError: boolean
  firingErrorMultiplier: number
  movementError: boolean
  movementErrorMultiplier: number
  onChange: (patch: Partial<ValorantCrosshairParams>) => void
}) {
  type P = Partial<ValorantCrosshairParams>
  const k = prefix === 'inner' ? INNER_KEYS : OUTER_KEYS
  const s = (key: keyof ValorantCrosshairParams, value: unknown) => onChange({ [key]: value } as P)

  return (
    <>
      <ToggleRow label={`顯示${label}`} checked={show} onCheckedChange={v => s(k.show, v)} />
      <SliderRow
        label={`${label}不透明度`}
        value={opacity}
        min={0}
        max={1}
        step={0.01}
        display={v => v.toFixed(2)}
        onChange={v => s(k.opacity, v)}
        disabled={!show}
      />
      <ToggleRow
        label="允許垂直縮放"
        checked={lengthNotLinked}
        onCheckedChange={v => s(k.linked, v)}
        disabled={!show}
        onLabel="解除綁定"
        offLabel="綁定"
      />
      {lengthNotLinked ? (
        <div
          className={cn(
            'select-none space-y-element py-element',
            !show && 'pointer-events-none opacity-40'
          )}
        >
          <span className="text-sub text-muted-foreground">{label}長度</span>
          <div className="flex gap-element">
            <div className="min-w-0 flex-1 space-y-element">
              <div className="flex items-center justify-between">
                <span className="text-label text-muted-foreground">水平</span>
                <span className="text-right text-sub tabular-nums">{length}</span>
              </div>
              <Slider
                value={[length]}
                min={0}
                max={20}
                step={1}
                onValueChange={([v]) => s(k.length, v)}
                disabled={!show}
              />
            </div>
            <div className="min-w-0 flex-1 space-y-element">
              <div className="flex items-center justify-between">
                <span className="text-label text-muted-foreground">垂直</span>
                <span className="text-right text-sub tabular-nums">{verticalLength}</span>
              </div>
              <Slider
                value={[verticalLength]}
                min={0}
                max={20}
                step={1}
                onValueChange={([v]) => s(k.vLen, v)}
                disabled={!show}
              />
            </div>
          </div>
        </div>
      ) : (
        <SliderRow
          label={`${label}長度`}
          value={length}
          min={0}
          max={20}
          step={1}
          onChange={v => {
            s(k.length, v)
            s(k.vLen, v)
          }}
          disabled={!show}
        />
      )}
      <SliderRow
        label={`${label}粗細`}
        value={thickness}
        min={1}
        max={10}
        step={1}
        onChange={v => s(k.thick, v)}
        disabled={!show}
      />
      <SliderRow
        label={`${label}偏移量`}
        value={offset}
        min={0}
        max={20}
        step={1}
        onChange={v => s(k.offset, v)}
        disabled={!show}
      />
      <ToggleRow
        label="移動失誤"
        checked={movementError}
        onCheckedChange={v => s(k.me, v)}
        disabled={!show}
      />
      <SliderRow
        label="移動失誤倍數"
        value={movementErrorMultiplier}
        min={0}
        max={3}
        step={0.1}
        display={v => v.toFixed(1)}
        onChange={v => s(k.mem, v)}
        disabled={!show || !movementError}
      />
      <ToggleRow
        label="射擊誤差"
        checked={firingError}
        onCheckedChange={v => s(k.fe, v)}
        disabled={!show}
      />
      <SliderRow
        label="射擊誤差倍數"
        value={firingErrorMultiplier}
        min={0}
        max={3}
        step={0.1}
        display={v => v.toFixed(1)}
        onChange={v => s(k.fem, v)}
        disabled={!show || !firingError}
      />
    </>
  )
}

// ─── Main sheet ───────────────────────────────────────────────────────────────

interface CrosshairAdjustSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialCode: string
  onSave: (code: string) => void
  overlayClassName?: string
}

export function CrosshairAdjustSheet({
  open,
  onOpenChange,
  initialCode,
  onSave,
  overlayClassName,
}: CrosshairAdjustSheetProps) {
  const [params, setParams] = useState<ValorantCrosshairParams>(() =>
    decodeValorantCrosshair(initialCode)
  )

  const liveCode = useMemo(() => encodeValorantCrosshair(params), [params])

  const patch = useCallback((delta: Partial<ValorantCrosshairParams>) => {
    setParams(prev => ({ ...prev, ...delta }))
  }, [])

  const patchSniper = useCallback((delta: Partial<ValorantSniperParams>) => {
    setParams(prev => ({
      ...prev,
      sniper: prev.sniper ? { ...prev.sniper, ...delta } : { ...SNIPER_DEFAULTS, ...delta },
    }))
  }, [])

  const handleSave = useCallback(() => {
    onSave(liveCode)
    onOpenChange(false)
  }, [liveCode, onSave, onOpenChange])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col sm:max-w-lg"
        overlayClassName={overlayClassName}
      >
        {/* Fixed header */}
        <SheetHeader className="shrink-0 pb-0">
          <SheetTitle className="text-card-title">調整準星</SheetTitle>
          <div className="flex flex-col items-center gap-3 pt-2 pb-1">
            <div className="flex items-center justify-center rounded-2xl bg-muted p-3">
              <CrosshairSVG p={params} size="lg" />
            </div>
            <code className="max-w-full break-all rounded bg-muted px-2 py-1 text-center font-mono text-label text-muted-foreground">
              {liveCode}
            </code>
          </div>
        </SheetHeader>

        {/* Scrollable body */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {/* 一般 */}
          <AdjustSection>
            <SectionTitle>一般</SectionTitle>
            <ColorPicker value={params.color} onChange={hex => patch({ color: hex })} />
          </AdjustSection>

          {/* 外框 */}
          <AdjustSection>
            <ToggleRow
              label="外框"
              checked={params.outlines}
              onCheckedChange={v => patch({ outlines: v })}
            />
            <SliderRow
              label="外框不透明度"
              value={params.outlineOpacity}
              min={0}
              max={1}
              step={0.01}
              display={v => v.toFixed(2)}
              onChange={v => patch({ outlineOpacity: v })}
              disabled={!params.outlines}
            />
            <SliderRow
              label="外框粗細"
              value={params.outlineThickness}
              min={0}
              max={6}
              step={1}
              onChange={v => patch({ outlineThickness: v })}
              disabled={!params.outlines}
            />
          </AdjustSection>

          {/* 準星中心點 */}
          <AdjustSection>
            <ToggleRow
              label="準星中心點"
              checked={params.hasDot}
              onCheckedChange={v => patch({ hasDot: v })}
            />
            <SliderRow
              label="準星中心點不透明度"
              value={params.dotOpacity}
              min={0}
              max={1}
              step={0.01}
              display={v => v.toFixed(2)}
              onChange={v => patch({ dotOpacity: v })}
              disabled={!params.hasDot}
            />
            <SliderRow
              label="準星中心點粗細"
              value={params.dotThickness}
              min={1}
              max={6}
              step={1}
              onChange={v => patch({ dotThickness: v })}
              disabled={!params.hasDot}
            />
          </AdjustSection>

          {/* 行為 */}
          <AdjustSection>
            <ToggleRow
              label="將十字準星偏移套用至射擊誤差偏移"
              checked={params.overrideFiringError}
              onCheckedChange={v => patch({ overrideFiringError: v })}
            />
            <ToggleRow
              label="將我的主十字準星套用至所有主十字準星"
              checked={params.overrideAllPrimary}
              onCheckedChange={v => patch({ overrideAllPrimary: v })}
            />
          </AdjustSection>

          {/* 內側線 */}
          <AdjustSection>
            <SectionTitle>內側線</SectionTitle>
            <LinesPanel
              prefix="inner"
              label="內側線"
              show={params.showInnerLines}
              opacity={params.innerOpacity}
              lengthNotLinked={params.innerLengthNotLinked}
              length={params.innerLength}
              verticalLength={params.innerVerticalLength}
              thickness={params.innerThickness}
              offset={params.innerOffset}
              firingError={params.innerFiringError}
              firingErrorMultiplier={params.innerFiringErrorMultiplier}
              movementError={params.innerMovementError}
              movementErrorMultiplier={params.innerMovementErrorMultiplier}
              onChange={patch}
            />
          </AdjustSection>

          {/* 外側線 */}
          <AdjustSection>
            <SectionTitle>外側線</SectionTitle>
            <LinesPanel
              prefix="outer"
              label="外側線"
              show={params.showOuterLines}
              opacity={params.outerOpacity}
              lengthNotLinked={params.outerLengthNotLinked}
              length={params.outerLength}
              verticalLength={params.outerVerticalLength}
              thickness={params.outerThickness}
              offset={params.outerOffset}
              firingError={params.outerFiringError}
              firingErrorMultiplier={params.outerFiringErrorMultiplier}
              movementError={params.outerMovementError}
              movementErrorMultiplier={params.outerMovementErrorMultiplier}
              onChange={patch}
            />
          </AdjustSection>

          {/* 開鏡瞄準用主十字準星 */}
          <AdjustSection>
            <ToggleRow
              label="開鏡瞄準用主十字準星"
              checked={params.sniper !== null}
              onCheckedChange={enabled => patch({ sniper: enabled ? SNIPER_DEFAULTS : null })}
            />
          </AdjustSection>

          {/* 狙擊鏡 */}
          {params.sniper && (
            <AdjustSection>
              <SectionTitle>狙擊鏡</SectionTitle>
              <p className="mb-element text-sub text-muted-foreground">準星中心點顏色</p>
              <ColorPicker
                value={params.sniper.color}
                onChange={hex => patchSniper({ color: hex })}
              />
              <ToggleRow
                label="準星中心點"
                checked={params.sniper.hasDot}
                onCheckedChange={v => patchSniper({ hasDot: v })}
              />
              <SliderRow
                label="準星中心點不透明度"
                value={params.sniper.dotOpacity}
                min={0}
                max={1}
                step={0.01}
                display={v => v.toFixed(2)}
                onChange={v => patchSniper({ dotOpacity: v })}
                disabled={!params.sniper.hasDot}
              />
              <SliderRow
                label="準星中心點粗細"
                value={params.sniper.dotThickness}
                min={1}
                max={6}
                step={1}
                onChange={v => patchSniper({ dotThickness: v })}
                disabled={!params.sniper.hasDot}
              />
            </AdjustSection>
          )}

          <div className="h-4" />
        </div>

        {/* Fixed footer */}
        <SheetFooter className="mt-0 shrink-0 flex-row gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button className="flex-1" onClick={handleSave}>
            套用並儲存
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
