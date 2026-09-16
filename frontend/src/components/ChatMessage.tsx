import Markdown from 'react-markdown'
import type { Async, AskResult } from '../api'
import CitationList from './CitationList'

export type ChatTurn = {
  id: string
  question: string
  result: Async<AskResult>
}

type Props = {
  turn: ChatTurn
}

/** Sohbetteki tek bir soru-cevap turu. */
function ChatMessage({ turn }: Props) {
  const { question, result } = turn

  return (
    <article className="turn">
      <div className="bubble bubble--question">{question}</div>

      {result.kind === 'loading' && (
        <div className="bubble bubble--answer bubble--pending">
          <span className="typing" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          Kod parcalari bulunuyor ve cevap yaziliyor&hellip;
        </div>
      )}

      {result.kind === 'error' && (
        <div className="bubble bubble--answer bubble--error">
          {result.message}
        </div>
      )}

      {result.kind === 'ok' && (
        <div className="bubble bubble--answer">
          <div className="answer">
            <Markdown>{result.data.answer}</Markdown>
          </div>

          <CitationList
            citations={result.data.citations}
            unverified={result.data.unverified_citations}
          />

          <details className="skipped">
            <summary>
              Kaynaklar ({result.data.sources.length} kod parcasi)
            </summary>
            <div className="chunk-list chunk-list--open">
              {result.data.sources.map((source) => (
                <article
                  key={source.chunk_id}
                  id={`source-${source.chunk_id}`}
                  className="chunk"
                >
                  <header className="chunk-header">
                    <span className="chunk-title">
                      {source.symbol_name && (
                        <span className="symbol">
                          <span className="symbol-kind">
                            {source.symbol_type}
                          </span>{' '}
                          {source.symbol_name}
                        </span>
                      )}
                      <code className="file-path">
                        {source.file_path}:{source.start_line}&ndash;
                        {source.end_line}
                      </code>
                    </span>
                    <span className="score-badge">
                      benzerlik {source.score.toFixed(3)}
                    </span>
                  </header>
                  <pre className="chunk-preview">{source.content}</pre>
                </article>
              ))}
            </div>
          </details>

          <p className="turn-meta">
            {result.data.model} · arama {result.data.retrieval_ms} ms · cevap{' '}
            {(result.data.generation_ms / 1000).toFixed(1)} sn
          </p>
        </div>
      )}
    </article>
  )
}

export default ChatMessage
