import ManualText from './ManualText'

export default function TopicView({ section, topic }) {
  return (
    <article>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{section.title}</p>
      <h2 className="mt-1 text-xl font-semibold text-foreground">{topic.title}</h2>
      <div className="mt-3 text-sm text-muted-foreground leading-relaxed">
        <ManualText text={topic.summary} />
      </div>
      {topic.image && (
        <figure className="mt-4">
          {/* Keyed by the picture, so moving to another topic swaps in a new
              element instead of showing the old picture while the new one loads. */}
          <img
            key={topic.image.src}
            src={topic.image.src}
            alt={topic.image.alt}
            loading="lazy"
            className="w-full rounded-lg border border-border"
          />
          <figcaption className="mt-1 text-xs text-muted-foreground">{topic.image.caption}</figcaption>
        </figure>
      )}
      {topic.steps?.length > 0 && (
        <>
          <h3 className="mt-5 text-sm font-semibold text-foreground">Steps</h3>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            {topic.steps.map((step) => (
              <li key={step}><ManualText text={step} /></li>
            ))}
          </ol>
        </>
      )}
      {topic.notes?.length > 0 && (
        <>
          <h3 className="mt-5 text-sm font-semibold text-foreground">Good to know</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {topic.notes.map((note) => (
              <li key={note}><ManualText text={note} /></li>
            ))}
          </ul>
        </>
      )}
    </article>
  )
}
