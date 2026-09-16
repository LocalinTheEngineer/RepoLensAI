import { useEffect, useState } from 'react'
import './App.css'
import {
  API_URL,
  describeError,
  fetchJson,
  postJson,
  type Async,
  type ChunkScan,
  type FileScan,
  type Health,
  type IndexResult,
  type Repository,
  type SearchResult,
} from './api'
import ChunkCard from './components/ChunkCard'
import CloneCard from './components/CloneCard'
import Feedback from './components/Feedback'
import FileScanCard from './components/FileScanCard'
import HealthBadge from './components/HealthBadge'
import IndexPanel from './components/IndexPanel'
import RepoForm from './components/RepoForm'
import SearchPanel from './components/SearchPanel'

function App() {
  const [health, setHealth] = useState<Async<Health>>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const [url, setUrl] = useState('')
  const [clone, setClone] = useState<Async<Repository>>({ kind: 'idle' })
  const [scan, setScan] = useState<Async<FileScan>>({ kind: 'idle' })
  const [chunks, setChunks] = useState<Async<ChunkScan>>({ kind: 'idle' })
  const [indexState, setIndexState] = useState<Async<IndexResult>>({
    kind: 'idle',
  })

  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<Async<SearchResult>>({ kind: 'idle' })

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
        setHealth({ kind: 'ok', data: await response.json() })
      } catch (error) {
        if (controller.signal.aborted) return
        setHealth({ kind: 'error', message: describeError(error) })
      }
    }

    checkHealth()
    return () => controller.abort()
  }, [attempt])

  /** Repoyu indirir, ardindan dosyalari tarar ve parcalara ayirir. */
  async function handleClone() {
    setClone({ kind: 'loading' })
    setScan({ kind: 'idle' })
    setChunks({ kind: 'idle' })
    setIndexState({ kind: 'idle' })
    setSearch({ kind: 'idle' })

    let repository: Repository
    try {
      repository = await fetchJson<Repository>(
        '/repositories',
        postJson({ url }),
      )
      setClone({ kind: 'ok', data: repository })
    } catch (error) {
      setClone({ kind: 'error', message: describeError(error) })
      return
    }

    const base = `/repositories/${repository.owner}/${repository.name}`

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

  /** Parcalari vektore cevirip veritabanina yazar. */
  async function handleIndex() {
    if (clone.kind !== 'ok') return
    const { owner, name } = clone.data

    setIndexState({ kind: 'loading' })
    try {
      setIndexState({
        kind: 'ok',
        data: await fetchJson<IndexResult>(
          `/repositories/${owner}/${name}/index`,
          postJson({}),
        ),
      })
    } catch (error) {
      setIndexState({ kind: 'error', message: describeError(error) })
    }
  }

  /** Sorguya anlamca en yakin kod parcalarini getirir. */
  async function handleSearch() {
    if (clone.kind !== 'ok') return
    const { owner, name } = clone.data

    setSearch({ kind: 'loading' })
    try {
      setSearch({
        kind: 'ok',
        data: await fetchJson<SearchResult>(
          `/repositories/${owner}/${name}/search`,
          postJson({ query, limit: 5 }),
        ),
      })
    } catch (error) {
      setSearch({ kind: 'error', message: describeError(error) })
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
        <p className="subtitle">Adim 7 &mdash; Anlamsal kod aramasi</p>
      </header>

      <HealthBadge state={health} onRetry={() => setAttempt((n) => n + 1)} />

      <RepoForm
        url={url}
        onUrlChange={setUrl}
        onSubmit={handleClone}
        busy={busy}
      />

      <Feedback
        state={clone}
        loadingText="Repository indiriliyor, bu biraz surebilir..."
        errorTitle="Indirilemedi"
      />
      {clone.kind === 'ok' && <CloneCard repository={clone.data} />}

      <Feedback
        state={scan}
        loadingText="Dosyalar taraniyor..."
        errorTitle="Dosyalar taranamadi"
      />
      {scan.kind === 'ok' && <FileScanCard scan={scan.data} />}

      <Feedback
        state={chunks}
        loadingText="Kod parcalara ayriliyor..."
        errorTitle="Parcalama basarisiz"
      />
      {chunks.kind === 'ok' && <ChunkCard chunks={chunks.data} />}

      {chunks.kind === 'ok' && (
        <IndexPanel
          state={indexState}
          chunkCount={chunks.data.chunk_count}
          onIndex={handleIndex}
        />
      )}

      <Feedback
        state={indexState}
        loadingText="Parcalar vektore cevrilip kaydediliyor..."
        errorTitle="Indeksleme basarisiz"
      />

      {clone.kind === 'ok' && (
        <SearchPanel
          state={search}
          query={query}
          onQueryChange={setQuery}
          onSubmit={handleSearch}
          ready={indexState.kind === 'ok'}
        />
      )}
    </main>
  )
}

export default App
