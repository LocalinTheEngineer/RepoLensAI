import Markdown from 'react-markdown'
import type { Async, AskResult } from '../api'
import CitationList from './CitationList'

type Props = {
  state: Async<AskResult>
  question: string
  onQuestionChange: (value: string) => void
  onSubmit: () => void
  /** Repository indekslenmeden soru sorulamaz. */
  ready: boolean
}

/** Ornek sorular. Flask uzerinde denenip cevaplandigi dogrulananlar. */
const EXAMPLES = [
  'how does request routing work',
  'how is the session cookie signed',
  'how does the CLI find the app',
]

/**
 * Repository hakkinda soru sorma paneli.
 *
 * Cevap, yalnizca asagida listelenen kod parcalarina dayanilarak uretilir.
 * Model kanit bulamazsa uydurmak yerine bulamadigini soyler.
 */
function AskPanel({
  state,
  question,
  onQuestionChange,
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
      <h2>Soru sor</h2>
      <p className="note">
        Cevap yalnizca repository&apos;deki gercek koddan uretilir. Kanit
        bulunamazsa model uydurmaz, bulamadigini soyler.
      </p>
      <p className="note warning-note">
        Arama Ingilizce calisir; sorunu Ingilizce yaz.
      </p>

      <form className="repo-form" onSubmit={handleSubmit}>
        <div className="repo-row">
          <input
            className="repo-input"
            type="text"
            placeholder="how does request routing work"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            disabled={busy || !ready}
            autoComplete="off"
          />
          <button
            type="submit"
            className="repo-button"
            disabled={busy || !ready || question.trim() === ''}
          >
            {busy ? 'Dusunuyor...' : 'Sor'}
          </button>
        </div>
      </form>

      {!ready && (
        <p className="note">
          Soru sorabilmek icin once repository&apos;yi indekslemelisin.
        </p>
      )}

      {ready && state.kind === 'idle' && (
        <ul className="pill-list">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                type="button"
                className="pill pill--button"
                onClick={() => onQuestionChange(example)}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      )}

      {state.kind === 'loading' && (
        <p className="note">
          Kod parcalari bulunuyor ve cevap yaziliyor&hellip;
        </p>
      )}

      {state.kind === 'error' && <p className="query-error">{state.message}</p>}

      {state.kind === 'ok' && (
        <>
          <article className="answer">
            <Markdown>{state.data.answer}</Markdown>
          </article>

          <CitationList
            citations={state.data.citations}
            unverified={state.data.unverified_citations}
          />

          <p className="note">
            {state.data.model} &middot; arama {state.data.retrieval_ms} ms
            &middot; cevap {(state.data.generation_ms / 1000).toFixed(1)} sn
          </p>

          <details className="skipped" open>
            <summary>
              Kaynaklar ({state.data.sources.length} kod parcasi)
            </summary>
            <div className="chunk-list chunk-list--open">
              {state.data.sources.map((source) => (
                <article
                  key={source.chunk_id}
                  id={`source-${source.chunk_id}`}
                  className="chunk"
                >
                  <header className="chunk-header">
                    <code className="file-path">
                      {source.file_path}:{source.start_line}&ndash;
                      {source.end_line}
                    </code>
                    <span className="score-badge">
                      benzerlik {source.score.toFixed(3)}
                    </span>
                  </header>
                  <pre className="chunk-preview">{source.content}</pre>
                </article>
              ))}
            </div>
          </details>
        </>
      )}
    </section>
  )
}

export default AskPanel
