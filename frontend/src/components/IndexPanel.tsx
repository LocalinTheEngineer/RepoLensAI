import type { Async, IndexResult } from '../api'

type Props = {
  state: Async<IndexResult>
  chunkCount: number
  onIndex: () => void
}

/**
 * Parcalari vektore cevirip veritabanina yazma paneli.
 *
 * Bu islem uzun surebilecegi icin otomatik degil, butona basilarak baslatilir.
 */
function IndexPanel({ state, chunkCount, onIndex }: Props) {
  const busy = state.kind === 'loading'

  return (
    <section className="result scan">
      <h2>Indeksleme</h2>
      <p className="note">
        Parcalar vektore cevrilip arama veritabanina yazilir. Ayni repository
        tekrar indekslenirse kayitlar cogalmaz, uzerine yazilir.
      </p>

      <div className="embed-actions">
        <button
          type="button"
          className="repo-button"
          onClick={onIndex}
          disabled={busy}
        >
          {busy ? 'Indeksleniyor...' : 'Indeksle'}
        </button>
        <span className="note">
          {chunkCount} parca islenecek
          {state.kind === 'idle' && '; ilk calistirmada model yuklenir'}
        </span>
      </div>

      {state.kind === 'ok' && (
        <dl className="result-details">
          <dt>Kayitli parca</dt>
          <dd>
            <strong>{state.data.stored_count}</strong>
          </dd>
          <dt>Vektor boyutu</dt>
          <dd>{state.data.dimensions}</dd>
          <dt>Embedding suresi</dt>
          <dd>{(state.data.embed_duration_ms / 1000).toFixed(1)} sn</dd>
          <dt>Yazma suresi</dt>
          <dd>{(state.data.store_duration_ms / 1000).toFixed(1)} sn</dd>
          <dt>Model</dt>
          <dd>
            <code>{state.data.embedding_model}</code>
          </dd>
        </dl>
      )}
    </section>
  )
}

export default IndexPanel
