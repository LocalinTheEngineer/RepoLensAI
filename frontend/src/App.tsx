import { useEffect, useState } from 'react'
import './App.css'
import {
  API_URL,
  describeError,
  fetchJson,
  postJson,
  type Async,
  type AskResult,
  type ChunkScan,
  type FileScan,
  type Health,
  type IndexResult,
  type Repository,
  type SearchMode,
  type SearchResult,
} from './api'
import type { ChatTurn } from './components/ChatMessage'
import ChatPanel from './components/ChatPanel'
import SearchPanel from './components/SearchPanel'
import Sidebar from './components/Sidebar'

/** Ana alanda hangi sekme acik. */
type Tab = 'chat' | 'search'

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

  const [tab, setTab] = useState<Tab>('chat')

  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])

  const [query, setQuery] = useState('')
  const [searchMode, setSearchMode] = useState<SearchMode>('hybrid')
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
    setTurns([])
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

  /** Soruyu sohbete ekler, cevabi geldiginde ayni turu gunceller. */
  async function handleAsk() {
    if (clone.kind !== 'ok' || question.trim() === '') return
    const { owner, name } = clone.data

    const id = crypto.randomUUID()
    const asked = question

    setTurns((previous) => [
      ...previous,
      { id, question: asked, result: { kind: 'loading' } },
    ])
    setQuestion('')

    /** Yalnizca bu turu gunceller; digerlerine dokunmaz. */
    function updateTurn(result: ChatTurn['result']) {
      setTurns((previous) =>
        previous.map((turn) => (turn.id === id ? { ...turn, result } : turn)),
      )
    }

    try {
      updateTurn({
        kind: 'ok',
        data: await fetchJson<AskResult>(
          `/repositories/${owner}/${name}/ask`,
          postJson({ question: asked, limit: 5 }),
        ),
      })
    } catch (error) {
      updateTurn({ kind: 'error', message: describeError(error) })
    }
  }

  /** Ham arama: LLM olmadan en yakin kod parcalari. */
  async function handleSearch() {
    if (clone.kind !== 'ok') return
    const { owner, name } = clone.data

    setSearch({ kind: 'loading' })
    try {
      setSearch({
        kind: 'ok',
        data: await fetchJson<SearchResult>(
          `/repositories/${owner}/${name}/search`,
          postJson({ query, limit: 5, mode: searchMode }),
        ),
      })
    } catch (error) {
      setSearch({ kind: 'error', message: describeError(error) })
    }
  }

  const loadingRepo =
    clone.kind === 'loading' ||
    scan.kind === 'loading' ||
    chunks.kind === 'loading'

  const asking = turns.some((turn) => turn.result.kind === 'loading')
  const indexed = indexState.kind === 'ok'

  return (
    <div className="shell">
      <Sidebar
        health={health}
        onHealthRetry={() => setAttempt((n) => n + 1)}
        url={url}
        onUrlChange={setUrl}
        onSubmit={handleClone}
        busy={loadingRepo}
        clone={clone}
        scan={scan}
        chunks={chunks}
        indexState={indexState}
        onIndex={handleIndex}
      />

      <main className="main">
        <nav className="tabs">
          <button
            type="button"
            className={`tab ${tab === 'chat' ? 'tab--active' : ''}`}
            onClick={() => setTab('chat')}
          >
            Sohbet
          </button>
          <button
            type="button"
            className={`tab ${tab === 'search' ? 'tab--active' : ''}`}
            onClick={() => setTab('search')}
          >
            Ham arama
          </button>
        </nav>

        {tab === 'chat' ? (
          <ChatPanel
            turns={turns}
            question={question}
            onQuestionChange={setQuestion}
            onSubmit={handleAsk}
            ready={indexed}
            busy={asking}
          />
        ) : (
          <div className="search-tab">
            <SearchPanel
              state={search}
              query={query}
              onQueryChange={setQuery}
              mode={searchMode}
              onModeChange={setSearchMode}
              onSubmit={handleSearch}
              ready={indexed}
            />
          </div>
        )}
      </main>
    </div>
  )
}

export default App
