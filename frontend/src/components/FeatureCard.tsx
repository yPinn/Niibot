import { Link } from 'react-router-dom'

import { Icon } from '@/components/primitives'
import { Badge, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { cn } from '@/lib/utils'

export interface FeatureCardProps {
  icon: string
  title: string
  description: string
  /** When set, the whole card becomes a Link with a hover affordance + arrow. */
  href?: string
  /** Top-right pill, e.g. "OBS". */
  badge?: string
  /** boolean → check / empty-circle beside the title; null / undefined → nothing. */
  done?: boolean | null
  /** Platform / capability tags under the description. */
  tags?: string[]
  /** Icon colour class. Defaults to the primary hue. */
  iconClassName?: string
  /** Stronger surface for highlighted cards (e.g. OBS modules). */
  accent?: boolean
}

/**
 * The icon + title + blurb card repeated across Get Started (core features,
 * modules) and the Discord dashboard. One component so the three used to be
 * hand-written variants stay in sync.
 */
export function FeatureCard({
  icon,
  title,
  description,
  href,
  badge,
  done,
  tags,
  iconClassName = 'text-primary',
  accent = false,
}: FeatureCardProps) {
  const card = (
    <Card
      className={cn(
        'h-full gap-0 py-section transition-colors',
        accent && 'border-primary/20 bg-primary/5',
        href && 'group-hover:border-primary/40',
        href && (accent ? 'group-hover:bg-primary/10' : 'group-hover:bg-accent/30')
      )}
    >
      <CardHeader className="px-section pb-element">
        <CardTitle className="flex items-center gap-element text-card-title">
          <Icon
            icon={icon}
            size="md"
            wrapperClassName={cn(
              iconClassName,
              href && 'transition-colors group-hover:text-primary'
            )}
          />
          <span className={cn('flex-1', href && 'transition-colors group-hover:text-primary')}>
            {title}
          </span>
          {done != null &&
            (done ? (
              <Icon
                icon="fa-solid fa-circle-check"
                size="sm"
                wrapperClassName="text-status-success"
              />
            ) : (
              <Icon
                icon="fa-regular fa-circle"
                size="sm"
                wrapperClassName="text-muted-foreground/40"
              />
            ))}
          {badge && (
            <Badge
              variant="outline"
              className="shrink-0 text-label border-primary/30 text-primary/70"
            >
              {badge}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-element px-section">
        <p className="text-sub leading-relaxed text-muted-foreground">{description}</p>
        {tags && tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tags.map(tag => (
              <Badge key={tag} variant="secondary" className="text-label">
                {tag}
              </Badge>
            ))}
          </div>
        )}
        {href && (
          <Icon
            icon="fa-solid fa-arrow-right"
            size="xs"
            wrapperClassName="mt-auto self-end pt-1 text-muted-foreground/30 transition-colors group-hover:text-primary/70"
          />
        )}
      </CardContent>
    </Card>
  )

  if (!href) return card
  return (
    <Link to={href} className="group block h-full">
      {card}
    </Link>
  )
}
