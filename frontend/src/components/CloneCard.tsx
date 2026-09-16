import type { Repository } from '../api'

type Props = {
  repository: Repository
}

/** Indirilen repository'nin ozeti. */
function CloneCard({ repository }: Props) {
  return (
    <section className="result result--ok">
      <h2>
        {repository.owner}/{repository.name}
      </h2>
      <p>
        {repository.already_cloned
          ? 'Bu repository zaten indirilmisti.'
          : 'Repository basariyla indirildi.'}
      </p>
      <dl className="result-details">
        <dt>Commit</dt>
        <dd>
          <code>{repository.commit.slice(0, 10)}</code>
        </dd>
        <dt>Konum</dt>
        <dd>
          <code>{repository.path}</code>
        </dd>
      </dl>
    </section>
  )
}

export default CloneCard
