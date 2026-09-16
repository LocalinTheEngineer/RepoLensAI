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

type ChunkSummary = {
  chunk_id: string
  file_path: string
  start_line: number
  end_line: number
  line_count: number
  preview: string
}

type ChunkScan = {
  owner: string
  name: string
  file_count: number
  chunk_count: number
  total_lines: number
  average_lines_per_chunk: number
  chunk_size_lines: number
  chunk_overlap_lines: number
  chunks: ChunkSummary[]
  truncated: boolean
}

type ChunkEmbeddingSample = {
  chunk_id: string
  vector_preview: number[]
}

type RepositoryEmbedding = {
  owner: string
  name: string
  embedding_model: string
  dimensions: number
  chunk_count: number
  duration_ms: number
  chunks_per_second: number
  samples: ChunkEmbeddingSample[]
}

type QueryEmbedding = {
  embedding_model: string
  dimensions: number
  duration_ms: number
  vector_preview: number[]
}

type Async<T> =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: T }
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

/** Verilen adresten JSON okur; hata durumunda anlasilir mesajla firlatir. */
async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init)
  const body: unknown = await response.json()
  if (!response.ok) {
    throw new Error(readErrorMessage(body, response.status))
  }
  return body as T
}

/** Vektorun ilk birkac sayisini okunabilir sekilde yazar. */
function formatVector(values: number[], dimensions: number): string {
  const shown = values.map((value) => value.toFixed(4)).join(', ')
  return `[${shown}, ... ${dimensions - values.length} sayi daha]`
}

function App() {
  const [health, setHealth] = useState<Health>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const [url, setUrl] = useState('')
  const [clone, setClone] = useState<Async<Repository>>({ kind: 'idle' })
  const [scan, setScan] = useState<Async<FileScan>>({ kind: 'idle' })
  const [chunks, setChunks] = useState<Async<ChunkScan>>({ kind: 'idle' })

  const [embeddings, setEmbeddings] = useState<Async<RepositoryEmbedding>>({
    kind: 'idle',
  })
  const [query, setQuery] = useState('')
  const [queryVector, setQueryVector] = useState<Async<QueryEmbedding>>({
    kind: 'idle',
  })

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

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    // Tarayicinin varsayilan davranisi sayfayi yeniden yuklemek; bunu istemiyoruz.
    event.preventDefault()
    setClone({ kind: 'loading' })
    setScan({ kind: 'idle' })
    setChunks({ kind: 'idle' })
    setEmbeddings({ kind: 'idle' })

    let repository: Repository
    try {
      repository = await fetchJson<Repository>('/repositories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      setClone({ kind: 'ok', data: repository })
    } catch (error) {
      setClone({ kind: 'error', message: describeError(error) })
      return
    }

    const base = `/repositories/${repository.owner}/${repository.name}`

    // Once hangi dosyalarin islenecegini, sonra onlarin parcalarini getiriyoruz.
    setScan({ kind: 'loading' })
    try {
      setScan({ kind: 'ok', data: await fetchJson<FileScan>(`${base}/files`) })
    } catch (error) {
      setScan({ kind: 'error', message: describeError(error) })
      return
    }

    setChunks({ kind: 'loading' })
    try {
      setChunks({
        kind: 'ok',
        data: await fetchJson<ChunkScan>(`${base}/chunks`),
      })
    } catch (error) {
      setChunks({ kind: 'error', message: describeError(error) })
    }
  }

  /** Parcalari vektore cevirir. Uzun surebilecegi icin ayri bir butona bagli. */
  async function handleEmbed() {
    if (clone.kind !== 'ok') return
    const { owner, name } = clone.data

    setEmbeddings({ kind: 'loading' })
    try {
      setEmbeddings({
        kind: 'ok',
        data: await fetchJson<RepositoryEmbedding>(
          `/repositories/${owner}/${name}/embeddings`,
        ),
      })
    } catch (error) {
      setEmbeddings({ kind: 'error', message: describeError(error) })
    }
  }

  async function handleQuerySubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setQueryVector({ kind: 'loading' })
    try {
      setQueryVector({
        kind: 'ok',
        data: await fetchJson<QueryEmbedding>('/embeddings/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: query }),
        }),
      })
    } catch (error) {
      setQueryVector({ kind: 'error', message: describeError(error) })
    }
  }

  const busy =
    clone.kind === 'loading' ||
    scan.kind === 'loading' ||
    chunks.kind === 'loading'

  return (
    <main className="app">
      <header className="app-header">
        <h1>RepoLens AI</h1>
        <p className="subtitle">Adim 5 &mdash; Embedding uret</p>
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
            {clone.data.owner}/{clone.data.name}
          </h2>
          <p>
            {clone.data.already_cloned
              ? 'Bu repository zaten indirilmisti.'
              : 'Repository basariyla indirildi.'}
          </p>
          <dl className="result-details">
            <dt>Commit</dt>
            <dd>
              <code>{clone.data.commit.slice(0, 10)}</code>
            </dd>
            <dt>Konum</dt>
            <dd>
              <code>{clone.data.path}</code>
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
            Git tarafindan takip edilen <strong>{scan.data.total_tracked}</strong>{' '}
            dosyadan <strong>{scan.data.selected_count}</strong> tanesi secildi
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
            <details className="skipped">
              <summary>Dosya listesini goster</summary>
              <div className="file-list">
                {scan.data.files.map((file) => (
                  <div key={file.path} className="file-row">
                    <code className="file-path">{file.path}</code>
                    <span className="file-lines">{file.lines} satir</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </section>
      )}

      {chunks.kind === 'loading' && (
        <section className="result">
          <p>Kod parcalara ayriliyor&hellip;</p>
        </section>
      )}

      {chunks.kind === 'error' && (
        <section className="result result--error">
          <h2>Parcalama basarisiz</h2>
          <p>{chunks.message}</p>
        </section>
      )}

      {chunks.kind === 'ok' && (
        <section className="result scan">
          <h2>Kod parcalari</h2>
          <p>
            <strong>{chunks.data.file_count}</strong> dosyadan{' '}
            <strong>{chunks.data.chunk_count}</strong> parca uretildi &mdash;
            parca basina ortalama{' '}
            <strong>{chunks.data.average_lines_per_chunk}</strong> satir.
          </p>
          <p className="note">
            Her parca en fazla {chunks.data.chunk_size_lines} satir; ardisik
            parcalar {chunks.data.chunk_overlap_lines} satir ortusur, boylece
            sinira denk gelen bir fonksiyon ikiye bolunup baglamini kaybetmez.
          </p>

          <details className="skipped">
            <summary>Parca onizlemelerini goster</summary>
            <div className="chunk-list">
              {chunks.data.chunks.map((chunk) => (
                <article key={chunk.chunk_id} className="chunk">
                  <header className="chunk-header">
                    <code className="file-path">{chunk.file_path}</code>
                    <span className="file-lines">
                      {chunk.start_line}&ndash;{chunk.end_line} (
                      {chunk.line_count} satir)
                    </span>
                  </header>
                  <pre className="chunk-preview">{chunk.preview}</pre>
                </article>
              ))}
            </div>
          </details>

          <div className="embed-actions">
            <button
              type="button"
              className="repo-button"
              onClick={handleEmbed}
              disabled={embeddings.kind === 'loading'}
            >
              {embeddings.kind === 'loading'
                ? 'Vektorler uretiliyor...'
                : 'Parcalari vektore cevir'}
            </button>
            <span className="note">
              {chunks.data.chunk_count} parca islenecek; ilk calistirmada model
              indirilir.
            </span>
          </div>
        </section>
      )}

      {embeddings.kind === 'loading' && (
        <section className="result">
          <p>Parcalar vektore cevriliyor, bu biraz surebilir&hellip;</p>
        </section>
      )}

      {embeddings.kind === 'error' && (
        <section className="result result--error">
          <h2>Vektor uretilemedi</h2>
          <p>{embeddings.message}</p>
        </section>
      )}

      {embeddings.kind === 'ok' && (
        <section className="result result--ok">
          <h2>Vektorler hazir</h2>
          <p>
            <strong>{embeddings.data.chunk_count}</strong> parca,{' '}
            <strong>{embeddings.data.dimensions}</strong> boyutlu vektorlere
            cevrildi &mdash; {(embeddings.data.duration_ms / 1000).toFixed(1)}{' '}
            saniye ({embeddings.data.chunks_per_second} parca/saniye).
          </p>
          <p className="note">
            Model: <code>{embeddings.data.embedding_model}</code>
          </p>

          <div className="vector-list">
            {embeddings.data.samples.map((sample) => (
              <div key={sample.chunk_id} className="vector-row">
                <code className="file-path">{sample.chunk_id}</code>
                <code className="vector-values">
                  {formatVector(sample.vector_preview, embeddings.data.dimensions)}
                </code>
              </div>
            ))}
          </div>

          <p className="note">
            Vektorler henuz kaydedilmiyor; kalici depolama Adim 6&apos;da Qdrant
            ile gelecek.
          </p>
        </section>
      )}

      <section className="result scan">
        <h2>Sorgu vektoru</h2>
        <p className="note">
          Ayni model kullanici sorgusunu da vektore cevirebilmeli &mdash; arama
          bu iki vektoru karsilastirarak calisacak.
        </p>
        <p className="note warning-note">
          Kullanilan model yalnizca Ingilizce icin egitilmistir; sorgularini
          Ingilizce yaz. Turkce sorgular alakasiz sonuc dondurur.
        </p>

        <form className="repo-form" onSubmit={handleQuerySubmit}>
          <div className="repo-row">
            <input
              className="repo-input"
              type="text"
              placeholder="how does authentication work"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              disabled={queryVector.kind === 'loading'}
              autoComplete="off"
            />
            <button
              type="submit"
              className="repo-button"
              disabled={queryVector.kind === 'loading' || query.trim() === ''}
            >
              {queryVector.kind === 'loading' ? 'Cevriliyor...' : 'Vektore cevir'}
            </button>
          </div>
        </form>

        {queryVector.kind === 'error' && (
          <p className="query-error">{queryVector.message}</p>
        )}

        {queryVector.kind === 'ok' && (
          <div className="vector-list">
            <div className="vector-row">
              <code className="file-path">
                {queryVector.data.dimensions} boyut &middot;{' '}
                {queryVector.data.duration_ms} ms
              </code>
              <code className="vector-values">
                {formatVector(
                  queryVector.data.vector_preview,
                  queryVector.data.dimensions,
                )}
              </code>
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
