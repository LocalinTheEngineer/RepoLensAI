import type { Async, SearchResult } from '../api'

type Props = {
  state: Async<SearchResult>
  query: string
  onQueryChange: (value: string) => void
  onSubmit: () => void
  /** Repository indekslenmeden arama yapilamaz. */
  ready: boolean
}

/** Ornek sorgular; kullanici ne yazacagini bilmesin diye. */
const EXAMPLES = [
  'how does authentication work',
  'where is the database connected',
  'how are configuration values loaded',
]

/** Anlamsal kod aramasi: sorgu kutusu ve sonuclar. */
function SearchPanel({
  state,
  query,
  onQueryChange,
  onSubmit,
  ready,
}: Props) {
  const busy = state.kind === 'loading'

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <section className="result scan">
      <h2>Kod arama</h2>
      <p className="note">
        Bir kavram yaz; sistem kelime degil <strong>anlam</strong> eslestirir.
        Aradigin metnin kodda birebir gecmesi gerekmez.
      </p>
      <p className="note warning-note">
        Kullanilan model yalnizca Ingilizce icin egitilmistir; sorgularini
        Ingilizce yaz. Turkce sorgular alakasiz sonuc dondurur.
      </p>

      <form className="repo-form" onSubmit={handleSubmit}>
        <div className="repo-row">
          <input
            className="repo-input"
            type="text"
            placeholder="how does authentication work"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            disabled={busy || !ready}
            autoComplete="off"
          />
          <button
            type="submit"
            className="repo-button"
            disabled={busy || !ready || query.trim() === ''}
          >
            {busy ? 'Araniyor...' : 'Ara'}
          </button>
        </div>
      </form>

      {!ready && (
        <p className="note">
          Arama yapabilmek icin once repository&apos;yi indekslemelisin.
        </p>
      )}

      {ready && state.kind === 'idle' && (
        <ul className="pill-list">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                type="button"
                className="pill pill--button"
                onClick={() => onQueryChange(example)}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      )}

      {state.kind === 'error' && <p className="query-error">{state.message}</p>}

      {state.kind === 'ok' && state.data.hits.length === 0 && (
        <p className="note">Sonuc bulunamadi.</p>
      )}

      {state.kind === 'ok' && state.data.hits.length > 0 && (
        <>
          <p className="note">
            {state.data.hits.length} sonuc &middot; {state.data.duration_ms} ms
          </p>
          <div className="chunk-list chunk-list--open">
            {state.data.hits.map((hit) => (
              <article key={hit.chunk_id} className="chunk">
                <header className="chunk-header">
                  <code className="file-path">
                    {hit.file_path}:{hit.start_line}&ndash;{hit.end_line}
                  </code>
                  <span className="score-badge">
                    benzerlik {hit.score.toFixed(3)}
                  </span>
                </header>
                <pre className="chunk-preview">{hit.content}</pre>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

export default SearchPanel
