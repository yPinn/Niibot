interface LegalSectionProps {
  id: string
  title: string
  children: React.ReactNode
}

export function LegalSection({ id, title, children }: LegalSectionProps) {
  return (
    <section id={id} className="flex flex-col gap-3 scroll-mt-4">
      <h2 className="border-l-2 border-primary pl-3 text-section-title font-semibold text-foreground">
        {title}
      </h2>
      <div className="flex flex-col gap-3 text-sub leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  )
}
