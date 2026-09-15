import { useEffect, useState } from 'react'
import './App.css'

// Backend'in adresi. Ileride .env dosyasina tasinacak.
const API_URL = 'http://127.0.0.1:8000'

// Backend saglik kontrolunun durumu.
type Health =
  | { kind: 'loading' }
  | { kind: 'ok'; value: string }
  | { kind: 'error'; message: string }

// Backend'in POST /repositories cevabi.
type Repository = {
  owner: string
  name: string
  path: string
  commit: string
  already_cloned: boolean
}

// Clone isleminin durumu.
type Clone =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; repository: Repository }
  | { kind: 'error'; message: string }

/** FastAPI'nin hata cevabindan okunabilir bir mesaj cikarir. */
function readErrorMessage(body: unknown, status: number): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail

    // Bizim firlattigimiz hatalar duz metin gelir.
    if (typeof detail === 'string') return detail

    // Pydantic dogrulama hatalari liste halinde gelir.
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown }
      if (typeof first?.msg === 'string') return first.msg
    }
  }
  return `Sunucu ${status} kodu dondurdu.`
}

function App() {
  const [health, setHealth] = useState<Health>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const [url, setUrl] = useState('')
  const [clone, setClone] = useState<Clone>({ kind: 'idle' })

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch(`${API_URL}/health`, {
          signal: controller.signal,
        })
        if (!response.ok) {
          throw new Error(`Sunucu ${response.status} kodu dondurdu.`)
        }
        const data: { status: string } = await response.json()
        setHealth({ kind: 'ok', value: data.status })
      } catch (error) {
        if (controller.signal.aborted) return
        setHealth({
          kind: 'error',
          message:
            error instanceof TypeError
              ? `Backend'e ulasilamadi. ${API_URL} calisiyor mu?`
              : error instanceof Error
                ? error.message
                : 'Bilinmeyen bir hata olustu.',
        })
      }
    }

    checkHealth()
    return () => controller.abort()
  }, [attempt])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    // Tarayicinin varsayilan davranisi sayfayi yeniden yuklemek; bunu istemiyoruz.
    event.preventDefault()
    setClone({ kind: 'loading' })

    try {
      const response = await fetch(`${API_URL}/repositories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })

      const body: unknown = await response.json()

      if (!response.ok) {
        throw new Error(readErrorMessage(body, response.status))
      }

      setClone({ kind: 'ok', repository: body as Repository })
    } catch (error) {
      setClone({
        kind: 'error',
        message:
          error instanceof TypeError
            ? `Backend'e ulasilamadi. ${API_URL} calisiyor mu?`
            : error instanceof Error
              ? error.message
              : 'Bilinmeyen bir hata olustu.',
      })
    }
  }

  const busy = clone.kind === 'loading'

  return (
    <main className="app">
      <header className="app-header">
        <h1>RepoLens AI</h1>
        <p className="subtitle">Adim 2 &mdash; Repository indirme</p>
      </header>

      {/* Backend saglik durumu: kucuk bir rozet */}
      <div className={`health health--${health.kind}`}>
        {health.kind === 'loading' && <span>Backend durumu: kontrol ediliyor&hellip;</span>}
        {health.kind === 'ok' && <span>Backend durumu: {health.value}</span>}
        {health.kind === 'error' && (
          <>
            <span>Backend durumu: baglanti yok &mdash; {health.message}</span>
            <button type="button" className="link-button" onClick={() => setAttempt((n) => n + 1)}>
              Tekrar dene
            </button>
          </>
        )}
      </div>

      <form className="repo-form" onSubmit={handleSubmit}>
        <label className="repo-label" htmlFor="repo-url">
          Public GitHub repository adresi
        </label>
        <div className="repo-row">
          <input
            id="repo-url"
            className="repo-input"
            type="text"
            placeholder="https://github.com/kullanici/repo"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" className="repo-button" disabled={busy || url.trim() === ''}>
            {busy ? 'Indiriliyor...' : 'Indir'}
          </button>
        </div>
      </form>

      {clone.kind === 'loading' && (
        <section className="result result--loading">
          <p>Repository indiriliyor, bu biraz surebilir&hellip;</p>
        </section>
      )}

      {clone.kind === 'ok' && (
        <section className="result result--ok">
          <h2>
            {clone.repository.owner}/{clone.repository.name}
          </h2>
          <p>
            {clone.repository.already_cloned
              ? 'Bu repository zaten indirilmisti.'
              : 'Repository basariyla indirildi.'}
          </p>
          <dl className="result-details">
            <dt>Commit</dt>
            <dd>
              <code>{clone.repository.commit.slice(0, 10)}</code>
            </dd>
            <dt>Konum</dt>
            <dd>
              <code>{clone.repository.path}</code>
            </dd>
          </dl>
        </section>
      )}

      {clone.kind === 'error' && (
        <section className="result result--error">
          <h2>Indirilemedi</h2>
          <p>{clone.message}</p>
        </section>
      )}
    </main>
  )
}

export default App
