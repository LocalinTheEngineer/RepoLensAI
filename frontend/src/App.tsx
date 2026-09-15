import { useEffect, useState } from 'react'
import './App.css'

// Backend'in adresi. Ileride .env dosyasina tasinacak.
const API_URL = 'http://127.0.0.1:8000'

type Health =
  | { kind: 'loading' }
  | { kind: 'ok'; value: string }
  | { kind: 'error'; message: string }

type Repository = {
  owner: string
  name: string
  path: string
  commit: string
  already_cloned: boolean
}

type RepositoryFile = {
  path: string
  extension: string
  size_bytes: number
  lines: number
}

type FileScan = {
  owner: string
  name: string
  total_tracked: number
  selected_count: number
  skipped_count: number
  skipped_reasons: Record<string, number>
  by_extension: Record<string, number>
  total_lines: number
  files: RepositoryFile[]
  truncated: boolean
}

type Clone =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; repository: Repository }
  | { kind: 'error'; message: string }

type Scan =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: FileScan }
  | { kind: 'error'; message: string }

// Backend'den gelen eleme sebeplerinin ekranda gosterilecek karsiliklari.
const SKIP_LABELS: Record<string, string> = {
  uretilmis_klasor: 'uretilmis klasor (node_modules, dist, build ...)',
  desteklenmeyen_uzanti: 'desteklenmeyen uzanti',
  cok_buyuk: 'cok buyuk dosya',
  binary_veya_bozuk: 'binary dosya',
  okunamadi: 'okunamadi',
}

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

/** Yakalanan hatayi kullaniciya gosterilecek metne cevirir. */
function describeError(error: unknown): string {
  if (error instanceof TypeError) {
    return `Backend'e ulasilamadi. ${API_URL} calisiyor mu?`
  }
  if (error instanceof Error) return error.message
  return 'Bilinmeyen bir hata olustu.'
}

function App() {
  const [health, setHealth] = useState<Health>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const [url, setUrl] = useState('')
  const [clone, setClone] = useState<Clone>({ kind: 'idle' })
  const [scan, setScan] = useState<Scan>({ kind: 'idle' })

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
        setHealth({ kind: 'error', message: describeError(error) })
      }
    }

    checkHealth()
    return () => controller.abort()
  }, [attempt])

  /** Indirilen repository'nin islenecek dosyalarini getirir. */
  async function loadFiles(owner: string, name: string) {
    setScan({ kind: 'loading' })
    try {
      const response = await fetch(
        `${API_URL}/repositories/${owner}/${name}/files`,
      )
      const body: unknown = await response.json()
      if (!response.ok) {
        throw new Error(readErrorMessage(body, response.status))
      }
      setScan({ kind: 'ok', data: body as FileScan })
    } catch (error) {
      setScan({ kind: 'error', message: describeError(error) })
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    // Tarayicinin varsayilan davranisi sayfayi yeniden yuklemek; bunu istemiyoruz.
    event.preventDefault()
    setClone({ kind: 'loading' })
    setScan({ kind: 'idle' })

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

      const repository = body as Repository
      setClone({ kind: 'ok', repository })

      // Indirme bitti; hemen ardindan dosyalari tara.
      await loadFiles(repository.owner, repository.name)
    } catch (error) {
      setClone({ kind: 'error', message: describeError(error) })
    }
  }

  const busy = clone.kind === 'loading' || scan.kind === 'loading'

  return (
    <main className="app">
      <header className="app-header">
        <h1>RepoLens AI</h1>
        <p className="subtitle">Adim 3 &mdash; Kaynak dosyalari filtrele</p>
      </header>

      <div className={`health health--${health.kind}`}>
        {health.kind === 'loading' && (
          <span>Backend durumu: kontrol ediliyor&hellip;</span>
        )}
        {health.kind === 'ok' && <span>Backend durumu: {health.value}</span>}
        {health.kind === 'error' && (
          <>
            <span>Backend durumu: baglanti yok &mdash; {health.message}</span>
            <button
              type="button"
              className="link-button"
              onClick={() => setAttempt((n) => n + 1)}
            >
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
          <button
            type="submit"
            className="repo-button"
            disabled={busy || url.trim() === ''}
          >
            {busy ? 'Calisiyor...' : 'Indir'}
          </button>
        </div>
      </form>

      {clone.kind === 'loading' && (
        <section className="result">
          <p>Repository indiriliyor, bu biraz surebilir&hellip;</p>
        </section>
      )}

      {clone.kind === 'error' && (
        <section className="result result--error">
          <h2>Indirilemedi</h2>
          <p>{clone.message}</p>
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

      {scan.kind === 'loading' && (
        <section className="result">
          <p>Dosyalar taraniyor&hellip;</p>
        </section>
      )}

      {scan.kind === 'error' && (
        <section className="result result--error">
          <h2>Dosyalar taranamadi</h2>
          <p>{scan.message}</p>
        </section>
      )}

      {scan.kind === 'ok' && (
        <section className="result scan">
          <h2>Islenecek dosyalar</h2>
          <p>
            Git tarafindan takip edilen{' '}
            <strong>{scan.data.total_tracked}</strong> dosyadan{' '}
            <strong>{scan.data.selected_count}</strong> tanesi secildi
            {scan.data.selected_count > 0 && (
              <>
                {' '}
                &mdash; toplam <strong>{scan.data.total_lines}</strong> satir
              </>
            )}
            .
          </p>

          {Object.keys(scan.data.by_extension).length > 0 && (
            <ul className="pill-list">
              {Object.entries(scan.data.by_extension).map(
                ([extension, count]) => (
                  <li key={extension} className="pill">
                    <code>{extension}</code> {count}
                  </li>
                ),
              )}
            </ul>
          )}

          {scan.data.skipped_count > 0 && (
            <details className="skipped">
              <summary>
                {scan.data.skipped_count} dosya elendi &mdash; neden?
              </summary>
              <ul>
                {Object.entries(scan.data.skipped_reasons).map(
                  ([reason, count]) => (
                    <li key={reason}>
                      {SKIP_LABELS[reason] ?? reason}: <strong>{count}</strong>
                    </li>
                  ),
                )}
              </ul>
            </details>
          )}

          {scan.data.files.length > 0 && (
            <div className="file-list">
              {scan.data.files.map((file) => (
                <div key={file.path} className="file-row">
                  <code className="file-path">{file.path}</code>
                  <span className="file-lines">{file.lines} satir</span>
                </div>
              ))}
            </div>
          )}

          {scan.data.truncated && (
            <p className="note">
              Liste ilk {scan.data.files.length} dosyayla sinirlandi.
            </p>
          )}
        </section>
      )}
    </main>
  )
}

export default App
