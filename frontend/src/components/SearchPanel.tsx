import type { Async, SearchMode, SearchResult } from '../api'

type Props = {
  state: Async<SearchResult>
  query: string
  onQueryChange: (value: string) => void
  mode: SearchMode
  onModeChange: (mode: SearchMode) => void
  /** Reranker acik mi: adaylar cross-encoder ile yeniden siralansin mi. */
  rerank: boolean
  onRerankChange: (rerank: boolean) => void
  onSubmit: () => void
  /** Repository indekslenmeden arama yapilamaz. */
  ready: boolean
}

/** Uc arama modunun kisa aciklamasi. */
const MODE_INFO: Record<SearchMode, { label: string; hint: string }> = {
  hybrid: {
    label: 'Hybrid',
    hint: 'Ikisini birden calistirir, siralamalari RRF ile birlestirir. Varsayilan.',
  },
  semantic: {
    label: 'Anlamsal',
    hint: 'Kavram eslestirir. Kelimeler farkli olsa da benzer anlamli kodu bulur.',
  },
  keyword: {
    label: 'Kelime (BM25)',
    hint: 'Birebir isim arar. "locate_app" yazinca o fonksiyonun kendisini bulur.',
  },
}

/** Skor rozetinin etiketi ve kac haneyle gosterilecegi moda gore degisir. */
const SCORE_FORMAT: Record<SearchMode, { label: string; digits: number }> = {
  hybrid: { label: 'RRF', digits: 4 },
  semantic: { label: 'benzerlik', digits: 3 },
  keyword: { label: 'BM25', digits: 2 },
}

/** Ornek sorgular; kullanici ne yazacagini bilmesin diye. */
const EXAMPLES: Record<SearchMode, string[]> = {
  hybrid: [
    'how does authentication work',
    'locate_app',
    'where is SECRET_KEY_FALLBACKS used',
  ],
  semantic: [
    'how does authentication work',
    'where is the database connected',
    'how are configuration values loaded',
  ],
  keyword: ['locate_app', 'SECRET_KEY_FALLBACKS', 'url_map'],
}

/** Anlamsal kod aramasi: sorgu kutusu ve sonuclar. */
function SearchPanel({
  state,
  query,
  onQueryChange,
  mode,
  onModeChange,
  rerank,
  onRerankChange,
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
        LLM devreye girmeden, ham arama sonuclarini gosterir. Uc farkli
        yontem var; hangisinin ne buldugunu karsilastirabilirsin.
      </p>
      {mode !== 'keyword' && (
        <p className="note warning-note">
          Anlamsal arama (hybrid dahil) yalnizca Ingilizce icin egitilmis bir
          model kullanir; sorgularini Ingilizce yaz.
        </p>
      )}

      <div className="mode-row">
        {(Object.keys(MODE_INFO) as SearchMode[]).map((option) => (
          <button
            key={option}
            type="button"
            className={`mode-button ${mode === option ? 'mode-button--active' : ''}`}
            onClick={() => onModeChange(option)}
          >
            {MODE_INFO[option].label}
          </button>
        ))}
      </div>
      <p className="note">{MODE_INFO[mode].hint}</p>

      <label className="note rerank-toggle">
        <input
          type="checkbox"
          checked={rerank}
          onChange={(event) => onRerankChange(event.target.checked)}
        />{' '}
        Reranker: once 20 aday cek, cross-encoder ile yeniden sirala, en iyi
        5-ini goster. Daha isabetli ama daha yavas.
      </label>

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
          {EXAMPLES[mode].map((example) => (
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
            {state.data.rerank_ms !== null && (
              <> &middot; bunun {state.data.rerank_ms} ms-si reranker</>
            )}
          </p>
          <div className="chunk-list chunk-list--open">
            {state.data.hits.map((hit) => (
              <article key={hit.chunk_id} className="chunk">
                <header className="chunk-header">
                  <span className="chunk-title">
                    {hit.symbol_name && (
                      <span className="symbol">
                        <span className="symbol-kind">{hit.symbol_type}</span>{' '}
                        {hit.symbol_name}
                      </span>
                    )}
                    <code className="file-path">
                      {hit.file_path}:{hit.start_line}&ndash;{hit.end_line}
                    </code>
                  </span>
                  <span className="score-badge">
                    {SCORE_FORMAT[state.data.mode].label}{' '}
                    {hit.score.toFixed(SCORE_FORMAT[state.data.mode].digits)}
                  </span>
                  {hit.rerank_score !== null && (
                    <span className="score-badge">
                      reranker {hit.rerank_score.toFixed(2)}
                    </span>
                  )}
                </header>
                {state.data.mode === 'hybrid' && (
                  <p className="note">
                    {hit.vector_rank === null
                      ? 'anlamsal: bulamadi'
                      : 'anlamsal #' + hit.vector_rank}
                    {' '}&middot;{' '}
                    {hit.keyword_rank === null
                      ? 'kelime: bulamadi'
                      : 'kelime #' + hit.keyword_rank}
                  </p>
                )}
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
