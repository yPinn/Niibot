import { type DonationPlatform, NEEDS_HASH, PLATFORM_LABELS } from '@/api/donation'
import { Icon, Spinner } from '@/components/primitives'
import { SecretInput } from '@/components/SecretInput'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  Input,
  Label,
  Switch,
} from '@/components/ui'

export interface PaymentFormState {
  merchant_id: string
  hash_key: string
  hash_iv: string
  min_amount: string
  media_share_enabled: boolean
  enabled: boolean
}

export function emptyForm(minAmount = 30): PaymentFormState {
  return {
    merchant_id: '',
    hash_key: '',
    hash_iv: '',
    min_amount: String(minAmount),
    media_share_enabled: false,
    enabled: false,
  }
}

interface PaymentPlatformCardProps {
  platform: DonationPlatform
  form: PaymentFormState
  hasExisting: boolean
  hasStoredHash: boolean
  isSaving: boolean
  isDeleting: boolean
  locked: boolean
  isOpen: boolean
  revealed: boolean
  onToggleOpen: () => void
  onToggleReveal: () => void
  onPatch: (patch: Partial<PaymentFormState>) => void
  onSave: () => void
  onRequestDelete: () => void
}

export function PaymentPlatformCard({
  platform,
  form,
  hasExisting,
  hasStoredHash,
  isSaving,
  isDeleting,
  locked,
  isOpen,
  revealed,
  onToggleOpen,
  onToggleReveal,
  onPatch,
  onSave,
  onRequestDelete,
}: PaymentPlatformCardProps) {
  const needsHash = NEEDS_HASH[platform]
  const label = PLATFORM_LABELS[platform]

  return (
    <Card>
      <CardHeader className="cursor-pointer select-none" onClick={onToggleOpen}>
        <div className="flex items-center gap-element">
          <CardTitle className="text-sub">{label}</CardTitle>
          {hasExisting && (
            <Badge variant="secondary" className="text-label">
              已設定
            </Badge>
          )}
        </div>
        <CardAction>
          <div className="flex items-center gap-2">
            {hasExisting && (
              <Button
                size="icon"
                variant="ghost"
                onClick={e => {
                  e.stopPropagation()
                  onRequestDelete()
                }}
                disabled={isSaving || isDeleting || locked}
                className="text-muted-foreground hover:text-destructive"
                aria-label={`刪除 ${label} 設定`}
              >
                {isDeleting ? (
                  <Spinner />
                ) : (
                  <Icon icon="fa-solid fa-trash" wrapperClassName="size-3.5" />
                )}
              </Button>
            )}
            <Switch
              id={`${platform}-enabled`}
              aria-label="啟用"
              checked={form.enabled}
              disabled={locked}
              onCheckedChange={checked => {
                onPatch({ enabled: checked })
                if (checked && !isOpen) onToggleOpen()
              }}
              onClick={e => e.stopPropagation()}
            />
            <Icon
              icon="fa-solid fa-chevron-down"
              wrapperClassName="size-3.5"
              className={`text-muted-foreground transition-transform duration-slow ease-default ${
                isOpen ? 'rotate-180' : ''
              }`}
            />
          </div>
        </CardAction>
      </CardHeader>

      <Collapsible open={isOpen}>
        <CollapsibleContent>
          <CardContent className="flex flex-col gap-3 pt-0">
            <div className="flex flex-col gap-1">
              <Label className="text-label text-muted-foreground" htmlFor={`${platform}-merchant`}>
                {platform === 'paypal' ? 'PayPal.me URL' : '商店代號'}
              </Label>
              <Input
                id={`${platform}-merchant`}
                value={form.merchant_id}
                disabled={locked}
                onChange={e => onPatch({ merchant_id: e.target.value })}
                placeholder={platform === 'paypal' ? 'paypal.me/yourname' : '商店代號'}
                className="h-8 text-sub"
              />
            </div>

            {needsHash && (
              <div className="flex flex-col gap-2">
                {hasStoredHash && (
                  <div className="flex items-center gap-1.5 text-label text-muted-foreground">
                    <Icon icon="fa-solid fa-lock" wrapperClassName="size-3" />
                    <span>金鑰已加密儲存，留空則保留原設定</span>
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-element">
                  <SecretInput
                    id={`${platform}-hashkey`}
                    label="HashKey"
                    value={form.hash_key}
                    disabled={locked}
                    revealed={revealed}
                    onToggleReveal={onToggleReveal}
                    onChange={hash_key => onPatch({ hash_key })}
                    placeholder={hasStoredHash ? '留空保留原設定' : 'HashKey'}
                  />
                  <SecretInput
                    id={`${platform}-hashiv`}
                    label="HashIV"
                    value={form.hash_iv}
                    disabled={locked}
                    revealed={revealed}
                    onToggleReveal={onToggleReveal}
                    onChange={hash_iv => onPatch({ hash_iv })}
                    placeholder={hasStoredHash ? '留空保留原設定' : 'HashIV'}
                  />
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-x-element gap-y-2 border-t border-border/50 pt-2">
              {needsHash && (
                <>
                  <span className="text-label text-muted-foreground shrink-0">最低</span>
                  <Input
                    id={`${platform}-minamount`}
                    type="number"
                    min={1}
                    value={form.min_amount}
                    disabled={locked}
                    onChange={e => onPatch({ min_amount: e.target.value })}
                    className="h-7 w-16 text-label"
                  />
                  <span className="text-label text-muted-foreground shrink-0">NT$</span>
                  <div className="flex items-center gap-1 ml-1">
                    <Switch
                      id={`${platform}-media`}
                      checked={form.media_share_enabled}
                      disabled={locked}
                      onCheckedChange={checked => onPatch({ media_share_enabled: checked })}
                    />
                    <Label
                      htmlFor={`${platform}-media`}
                      className="text-label cursor-pointer whitespace-nowrap"
                    >
                      影片點播
                    </Label>
                  </div>
                </>
              )}
              <div className="flex gap-1.5 ml-auto">
                <Button
                  size="sm"
                  onClick={onSave}
                  disabled={isSaving || isDeleting || locked}
                  className="h-7 px-3 text-label"
                >
                  {isSaving && <Spinner className="mr-1" />}
                  儲存
                </Button>
              </div>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
