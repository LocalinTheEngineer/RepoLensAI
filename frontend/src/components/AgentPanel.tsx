import Markdown from 'react-markdown'
import type { Async, InvestigateResult } from '../api'
import CitationList from './CitationList'

type Props = {
  state: Async<InvestigateResult>
  question: string
  onQuestionChange: (value: string) => void
  onSubmit: () => void
  /** Repository indekslenmeden arastirma yapilamaz. */
  ready: boolean
}

/** Araclarin ekranda gosterilecek adlari. */
const TOOL_LABELS: Record<string, string> = {
  search_code: 'anlamsal arama',
  search_symbol: 'sembol arama',
  read_file: 'dosya okuma',
  find_references: 'referans tarama',
  read_tests: 'test arama',
}

/** Tek aramayla cevaplanmayan sorular icin ornekler. */
const EXAMPLES = [
  'how does a request get from the WSGI entry point to my view function',
  'what happens to the session between the request starting and the response',
  'how does a blueprint end up with its url prefix applied',
]

/** Cok adimli arastirma: agent'in izledigi yol ve kaynakli cevabi. */
function AgentPanel({
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
      <h2>Arastir</h2>
      <p className="note">
        Sohbet tek arama yapar. Burada model araclari kendisi cagirir: arar,
        dosya okur, gordugu isimleri baska dosyalara kadar takip eder. Cevabi
        birden fazla dosyaya dagilmis sorular icin.
      </p>
      <p className="note warning-note">
        Birkac model cagrisi yapildigi icin sohbetten yavastir; sorunu
        Ingilizce yaz.
      </p>

      <form className="repo-form" onSubmit={handleSubmit}>
        <div className="repo-row">
          <input
            className="repo-input"
            type="text"
            placeholder="how does a request reach my view function"
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
            {busy ? 'Arastiriyor...' : 'Arastir'}
          </button>
        </div>
      </form>

      {!ready && (
        <p className="note">
          Arastirma icin once repository&apos;yi indekslemelisin.
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

      {busy && (
        <p className="note">
          Arastiriyor: arama yapiyor, dosya okuyor, bulduklarini takip
          ediyor&hellip;
        </p>
      )}

      {state.kind === 'error' && <p className="query-error">{state.message}</p>}

      {state.kind === 'ok' && (
        <>
          <details className="skipped" open>
            <summary>
              Izlenen yol ({state.data.steps.length} adim)
            </summary>
            <ol className="chunk-list chunk-list--open">
              {state.data.steps.map((step, index) => (
                <li key={index} className="chunk">
                  <span className="symbol">
                    <span className="symbol-kind">
                      {TOOL_LABELS[step.tool] ?? step.tool}
                    </span>{' '}
                    {step.argument}
                  </span>{' '}
                  <span className="score-badge">{step.result_count} sonuc</span>
                </li>
              ))}
            </ol>
          </details>

          <div className="answer">
            <Markdown>{state.data.answer}</Markdown>
          </div>

          <CitationList
            citations={state.data.citations}
            unverified={state.data.unverified_citations}
          />

          <p className="note">
            {state.data.model} &middot; {state.data.sources.length} kod parcasi
            incelendi &middot; {(state.data.duration_ms / 1000).toFixed(1)} sn
          </p>
        </>
      )}
    </section>
  )
}

export default AgentPanel
