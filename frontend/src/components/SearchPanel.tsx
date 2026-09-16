import type { Async, SearchMode, SearchResult } from '../api'

type Props = {
  state: Async<SearchResult>
  query: string
  onQueryChange: (value: string) => void
  mode: SearchMode
  onModeChange: (mode: SearchMode) => void
  onSubmit: () => void
  /** Repository indekslenmeden arama yapilamaz. */
  ready: boolean
}

/** Iki arama modunun kisa aciklamasi. */
const MODE_INFO: Record<SearchMode, { label: string; hint: string }> = {
  semantic: {
    label: 'Anlamsal',
    hint: 'Kavram eslestirir. Kelimeler farkli olsa da benzer anlamli kodu bulur.',
  },
  keyword: {
    label: 'Kelime (BM25)',
    hint: 'Birebir isim arar. "locate_app" yazinca o fonksiyonun kendisini bulur.',
  },
}

/** Ornek sorgular; kullanici ne yazacagini bilmesin diye. */
const EXAMPLES: Record<SearchMode, string[]> = {
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
        LLM devreye girmeden, ham arama sonuclarini gosterir. Iki farkli
        yontem var; hangisinin ne buldugunu karsilastirabilirsin.
      </p>
      {mode === 'semantic' && (
        <p className="note warning-note">
          Anlamsal arama yalnizca Ingilizce icin egitilmis bir model kullanir;
          sorgularini Ingilizce yaz.
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
                    {state.data.mode === 'keyword' ? 'BM25' : 'benzerlik'}{' '}
                    {hit.score.toFixed(state.data.mode === 'keyword' ? 2 : 3)}
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
