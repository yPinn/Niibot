import { Icon } from '@/components/primitives'

const SCOPE_CATEGORIES: { label: string; scopes: string[] }[] = [
  { label: 'Identity', scopes: ['user:bot', 'channel:bot'] },
  { label: 'Chat', scopes: ['user:read:chat', 'user:write:chat'] },
  { label: 'User', scopes: ['user:read:emotes', 'user:manage:whispers'] },
  {
    label: 'Channel',
    scopes: [
      'channel:read:redemptions',
      'channel:read:subscriptions',
      'channel:manage:moderators',
      'channel:manage:vips',
    ],
  },
  { label: 'Revenue', scopes: ['bits:read'] },
  {
    label: 'Moderation',
    scopes: [
      'moderation:read',
      'moderator:read:followers',
      'moderator:read:chatters',
      'moderator:manage:announcements',
      'moderator:manage:shoutouts',
    ],
  },
]

function buildScopeGroups(granted: string[], missing: string[]) {
  const grantedSet = new Set(granted)
  const allSet = new Set([...granted, ...missing])
  const matched = new Set<string>()
  const groups: { label: string; items: { scope: string; granted: boolean }[] }[] = []

  for (const cat of SCOPE_CATEGORIES) {
    const inCat = cat.scopes.filter(s => allSet.has(s))
    if (inCat.length === 0) continue
    inCat.forEach(s => matched.add(s))
    groups.push({
      label: cat.label,
      items: [
        ...inCat.filter(s => !grantedSet.has(s)).map(s => ({ scope: s, granted: false })),
        ...inCat.filter(s => grantedSet.has(s)).map(s => ({ scope: s, granted: true })),
      ],
    })
  }

  const others = [...allSet].filter(s => !matched.has(s))
  if (others.length > 0) {
    groups.push({
      label: 'Other',
      items: others.map(s => ({ scope: s, granted: grantedSet.has(s) })),
    })
  }

  return groups
}

function ScopeRow({ scope, granted }: { scope: string; granted: boolean }) {
  return (
    <div className="flex items-center gap-element py-0.5">
      <Icon
        icon={granted ? 'fa-solid fa-check' : 'fa-solid fa-xmark'}
        size="xs"
        className={granted ? 'text-status-online shrink-0' : 'text-status-offline shrink-0'}
      />
      <code className={`text-label font-mono ${granted ? 'text-muted-foreground' : ''}`}>
        {scope}
      </code>
    </div>
  )
}

export function ScopeSection({
  title,
  granted,
  missing,
}: {
  title?: string
  granted: string[]
  missing: string[]
}) {
  const groups = buildScopeGroups(granted, missing)
  return (
    <div className="space-y-element">
      {title && (
        <p className="text-label font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </p>
      )}
      <div className="rounded-md border border-border bg-muted p-3">
        {groups.length === 0 ? (
          <p className="text-label text-muted-foreground">No scope data stored</p>
        ) : (
          <div>
            {groups.map((group, i) => (
              <div key={group.label}>
                {i > 0 && <div className="border-t border-border my-1.5" />}
                {group.items.map(({ scope, granted: g }) => (
                  <ScopeRow key={scope} scope={scope} granted={g} />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
