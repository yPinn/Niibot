import { Icon } from '@/components/primitives'

export interface SetupStep {
  /** Font Awesome icon shown next to the step title. */
  icon?: string
  title: string
  /** One line of context — the "why" of this step. */
  description?: string
  /** Ordered sub-steps. Plain strings, or JSX with <GuideValue> for literals. */
  items: React.ReactNode[]
}

/**
 * Inline chip for a literal the user must type or look for — a size, a URL,
 * a checkbox label. The app font is already monospace, so a chip (not <code>)
 * is what makes it read as "this exact string".
 */
export function GuideValue({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-muted px-1 py-0.5 text-label text-foreground">{children}</span>
}

/**
 * A vertical numbered timeline of setup steps — each an optional icon, a
 * one-line "why", and an ordered list of "how" sub-steps. Shared by the OBS /
 * Twitch setup sheets (Video Queue, Chat Overlay, …).
 */
export function SetupSteps({ steps }: { steps: SetupStep[] }) {
  return (
    <ol className="flex flex-col">
      {steps.map((step, i) => (
        <li key={step.title} className="flex gap-element pb-section last:pb-0">
          <div className="flex flex-col items-center">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sub font-semibold text-primary ring-1 ring-primary/20 tabular-nums">
              {i + 1}
            </span>
            {i < steps.length - 1 && <span className="mt-1 w-px flex-1 bg-border" />}
          </div>
          <div className="flex flex-1 flex-col gap-element">
            <h3 className="flex items-center gap-1.5 text-content font-semibold">
              {step.icon && (
                <Icon
                  icon={step.icon}
                  wrapperClassName="size-3.5"
                  className="text-label text-muted-foreground"
                />
              )}
              {step.title}
            </h3>
            {step.description && (
              <p className="text-sub text-muted-foreground">{step.description}</p>
            )}
            <ol className="flex flex-col gap-element">
              {step.items.map((item, j) => (
                <li key={j} className="flex gap-element text-sub">
                  <span className="shrink-0 text-label text-muted-foreground tabular-nums">
                    {j + 1}.
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </div>
        </li>
      ))}
    </ol>
  )
}
