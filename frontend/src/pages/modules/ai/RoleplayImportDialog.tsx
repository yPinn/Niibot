import { useState } from 'react'

import { errorMessage } from '@/api/errors'
import {
  importRoleplayCharacter,
  MAX_ROLEPLAY_FILE_BYTES,
  parseRoleplayCharacterFile,
  type RoleplayCharacterFile,
  type RoleplayImportMode,
  type RoleplayImportResult,
} from '@/api/roleplay'
import { Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
} from '@/components/ui'

interface RoleplayImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  channelId: string
  existingDigests: string[]
  atLimit: boolean
  onImported: (result: RoleplayImportResult) => void
  onCloseAutoFocus: () => void
}

export function RoleplayImportDialog({
  open,
  onOpenChange,
  channelId,
  existingDigests,
  atLimit,
  onImported,
  onCloseAutoFocus,
}: RoleplayImportDialogProps) {
  const [character, setCharacter] = useState<RoleplayCharacterFile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyMode, setBusyMode] = useState<RoleplayImportMode | null>(null)

  const duplicate = character ? existingDigests.includes(character.manifest.content_digest) : false
  const blocksNewSet = atLimit && !duplicate

  function reset() {
    setCharacter(null)
    setError(null)
    setBusyMode(null)
  }

  function changeOpen(next: boolean) {
    if (!next && busyMode) return
    if (!next) reset()
    onOpenChange(next)
  }

  async function chooseFile(file: File | undefined) {
    setCharacter(null)
    setError(null)
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.json')) {
      setError('請選擇副檔名為 .json 的 Niibot 角色設定集')
      return
    }
    if (file.size > MAX_ROLEPLAY_FILE_BYTES) {
      setError('檔案大小不能超過 128 KB')
      return
    }
    try {
      setCharacter(parseRoleplayCharacterFile(await file.text()))
    } catch (cause) {
      setError(errorMessage(cause, '無法讀取這個角色設定集'))
    }
  }

  async function submit(mode: RoleplayImportMode) {
    if (!character) return
    setBusyMode(mode)
    setError(null)
    try {
      const result = await importRoleplayCharacter(channelId, mode, character)
      onImported(result)
      reset()
      onOpenChange(false)
    } catch (cause) {
      setError(errorMessage(cause, '匯入角色設定集失敗，請稍後再試'))
      setBusyMode(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent
        onCloseAutoFocus={event => {
          event.preventDefault()
          onCloseAutoFocus()
        }}
      >
        <DialogHeader>
          <DialogTitle>匯入角色設定集</DialogTitle>
          <DialogDescription>
            選擇由 Niibot 下載的設定集。確認內容後，可以直接使用，或另存一份再修改。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-section">
          <div className="space-y-2">
            <Label htmlFor="roleplay-import-file">選擇角色設定集</Label>
            <Input
              id="roleplay-import-file"
              type="file"
              accept=".json,application/json"
              disabled={busyMode !== null}
              onChange={event => void chooseFile(event.currentTarget.files?.[0])}
            />
            <p className="text-label text-muted-foreground">
              僅支援 Niibot 匯出的 JSON 檔，最大 128 KB。
            </p>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertTitle>無法匯入</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {character && (
            <>
              <section className="rounded-lg border bg-muted/30 p-4" aria-label="角色設定摘要">
                <p className="text-label text-muted-foreground">準備匯入</p>
                <h3 className="mt-1 font-medium">{character.package.character.name}</h3>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-muted-foreground">作品或世界</dt>
                    <dd className="mt-0.5">{character.package.world.title}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">故事時間點</dt>
                    <dd className="mt-0.5">{character.package.world.story_stage}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">背景條目</dt>
                    <dd className="mt-0.5">{character.package.lore_entries.length} 條背景條目</dd>
                  </div>
                </dl>
              </section>

              <Alert>
                <AlertTitle>匯入前請留意</AlertTitle>
                <AlertDescription>
                  這份檔案包含完整背景、角色不知道的內容，也可能提到後續劇情；請確認來源可信。
                </AlertDescription>
              </Alert>

              {duplicate && (
                <p className="text-sm text-muted-foreground">
                  已有相同版本；直接使用時會切換到現有角色，不建立重複副本。
                </p>
              )}
              {blocksNewSet && (
                <p className="text-sm text-destructive">
                  已達 5 組上限。請先封存一組未使用的角色，再匯入新的設定集。
                </p>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => changeOpen(false)} disabled={busyMode !== null}>
            取消
          </Button>
          {character && (
            <>
              <Button
                variant="outline"
                onClick={() => void submit('copy')}
                disabled={busyMode !== null || atLimit}
              >
                {busyMode === 'copy' && <Spinner className="mr-1.5 h-3 w-3" />}
                複製並修改
              </Button>
              <Button
                onClick={() => void submit('use')}
                disabled={busyMode !== null || blocksNewSet}
              >
                {busyMode === 'use' && <Spinner className="mr-1.5 h-3 w-3" />}
                使用這個角色
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
