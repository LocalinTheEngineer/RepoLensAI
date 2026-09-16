import type { Async, Health } from '../api'

type Props = {
  state: Async<Health>
  onRetry: () => void
}

/** Backend'in ayakta olup olmadigini gosteren kucuk rozet. */
function HealthBadge({ state, onRetry }: Props) {
  return (
    <div className={`health health--${state.kind}`}>
      {state.kind === 'loading' && (
        <span>Backend durumu: kontrol ediliyor&hellip;</span>
      )}

      {state.kind === 'ok' && <span>Backend durumu: {state.data.status}</span>}

      {state.kind === 'error' && (
        <>
          <span>Backend durumu: baglanti yok &mdash; {state.message}</span>
          <button type="button" className="link-button" onClick={onRetry}>
            Tekrar dene
          </button>
        </>
      )}
    </div>
  )
}

export default HealthBadge
