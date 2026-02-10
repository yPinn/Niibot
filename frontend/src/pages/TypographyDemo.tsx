import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const layer1Scale = [
  { token: '--text-xs', cls: 'text-xs', rem: '0.75rem', px: '12px' },
  { token: '--text-sm', cls: 'text-sm', rem: '0.875rem', px: '14px' },
  { token: '--text-base', cls: 'text-base', rem: '1rem', px: '16px' },
  { token: '--text-lg', cls: 'text-lg', rem: '1.125rem', px: '18px' },
  { token: '--text-xl', cls: 'text-xl', rem: '1.25rem', px: '20px' },
  { token: '--text-2xl', cls: 'text-2xl', rem: '1.5rem', px: '24px' },
  { token: '--text-3xl', cls: 'text-3xl', rem: '1.875rem', px: '30px' },
]

const layer2Scale = [
  {
    token: '--text-page-title',
    cls: 'text-page-title',
    ref: 'var(--text-2xl)',
    usage: '頁面主標題 h1',
  },
  {
    token: '--text-section-title',
    cls: 'text-section-title',
    ref: 'var(--text-xl)',
    usage: '區塊標題 h2',
  },
  {
    token: '--text-card-title',
    cls: 'text-card-title',
    ref: 'var(--text-lg)',
    usage: 'Card 內標題 h3',
  },
  { token: '--text-content', cls: 'text-content', ref: 'var(--text-base)', usage: '正文內容' },
  { token: '--text-secondary', cls: 'text-secondary', ref: 'var(--text-sm)', usage: '次要說明' },
  { token: '--text-label', cls: 'text-label', ref: 'var(--text-xs)', usage: '標籤、badge' },
]

const spacingScale = [
  { cls: 'gap-1 / p-1', rem: '0.25rem', px: '4px', usage: '最小間距、icon gap' },
  { cls: 'gap-2 / p-2', rem: '0.5rem', px: '8px', usage: '元素內距、compact gap' },
  { cls: 'gap-3 / p-3', rem: '0.75rem', px: '12px', usage: 'card 內元素間距' },
  { cls: 'gap-4 / p-4', rem: '1rem', px: '16px', usage: '標準 padding' },
  { cls: 'gap-6 / p-6', rem: '1.5rem', px: '24px', usage: 'section 間距' },
  { cls: 'gap-8 / p-8', rem: '2rem', px: '32px', usage: '頁面區塊間距' },
]

export default function TypographyDemo() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 p-8">
      {/* ── 頁面標題 ── */}
      <div>
        <h1 className="text-page-title font-bold">Typography & Spacing Demo</h1>
        <p className="text-secondary text-muted-foreground">
          兩層 Token 架構：Layer 1 尺寸原值 → Layer 2 語義別名
        </p>
      </div>

      {/* ── Layer 2: 語義 Token 實際渲染 ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-section-title">Layer 2 — 語義 Token（頁面使用這層）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {layer2Scale.map(t => (
            <div key={t.cls} className="flex items-baseline gap-4 border-b border-border/50 pb-3">
              <Badge variant="secondary" className="shrink-0 font-mono text-label">
                {t.cls}
              </Badge>
              <span className="shrink-0 text-label text-muted-foreground">{t.ref}</span>
              <span className={t.cls}>{t.usage} — Niibot 機器人</span>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ── 標題層級展示（使用語義 class） ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-section-title">標題層級對照（語義 class）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <h1 className="text-page-title font-bold">h1 — text-page-title → 24px</h1>
          <h2 className="text-section-title font-semibold">h2 — text-section-title → 20px</h2>
          <h3 className="text-card-title font-medium">h3 — text-card-title → 18px</h3>
          <p className="text-content">正文 — text-content → 16px</p>
          <p className="text-secondary text-muted-foreground">次要 — text-secondary → 14px</p>
          <p className="text-label text-muted-foreground">標籤 — text-label → 12px</p>
        </CardContent>
      </Card>

      {/* ── Layer 1: 尺寸原值 ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-section-title">Layer 1 — 尺寸原值（Tailwind 預設）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {layer1Scale.map(t => (
            <div key={t.cls} className="flex items-baseline gap-4 border-b border-border/50 pb-3">
              <Badge variant="secondary" className="shrink-0 font-mono text-label">
                {t.cls}
              </Badge>
              <span className="shrink-0 text-label text-muted-foreground">{t.px}</span>
              <span className={t.cls}>Niibot 機器人指令管理 — The quick brown fox</span>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ── 間距展示 ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-section-title">間距 Scale</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {spacingScale.map(s => (
            <div key={s.cls} className="flex items-center gap-4">
              <Badge
                variant="secondary"
                className="w-28 shrink-0 justify-center font-mono text-label"
              >
                {s.px}
              </Badge>
              <div className="flex items-center gap-2">
                <div
                  className="bg-primary/20 border border-primary/40"
                  style={{ width: s.rem, height: '1.5rem' }}
                />
                <span className="text-secondary">{s.cls}</span>
                <span className="text-label text-muted-foreground">— {s.usage}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ── 兩層對照表 ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-section-title">完整對照表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Layer 2 (語義)</TableHead>
                  <TableHead>→ Layer 1 (尺寸)</TableHead>
                  <TableHead>rem</TableHead>
                  <TableHead>px</TableHead>
                  <TableHead>用途</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {layer2Scale.map((s, i) => (
                  <TableRow key={s.token}>
                    <TableCell className="font-mono text-secondary">{s.cls}</TableCell>
                    <TableCell className="font-mono text-secondary">{layer1Scale[i].cls}</TableCell>
                    <TableCell className="text-secondary">{layer1Scale[i].rem}</TableCell>
                    <TableCell className="text-secondary">{layer1Scale[i].px}</TableCell>
                    <TableCell className="text-secondary text-muted-foreground">
                      {s.usage}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
