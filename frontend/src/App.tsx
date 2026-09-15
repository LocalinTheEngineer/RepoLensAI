import { useEffect, useState } from 'react'
import './App.css'

// Backend'in adresi. Ileride .env dosyasina tasinacak (Adim 2).
const API_URL = 'http://127.0.0.1:8000'

// Ekranin icinde bulunabilecegi uc durumdan biri.
type Status =
  | { kind: 'loading' }
  | { kind: 'ok'; value: string }
  | { kind: 'error'; message: string }

function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    // Bilesen ekrandan kalkarsa yarim kalan istegi iptal etmek icin.
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
        setStatus({ kind: 'ok', value: data.status })
      } catch (error) {
        // Istek bilerek iptal edildiyse hata gosterme.
        if (controller.signal.aborted) return

        const message =
          error instanceof TypeError
            ? `Backend'e ulasilamadi. ${API_URL} adresinde sunucu calisiyor mu?`
            : error instanceof Error
              ? error.message
              : 'Bilinmeyen bir hata olustu.'

        setStatus({ kind: 'error', message })
      }
    }

    checkHealth()

    return () => controller.abort()
  }, [attempt])

  function retry() {
    setStatus({ kind: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  return (
    <main className="app">
      <header className="app-header">
        <h1>RepoLens AI</h1>
        <p className="subtitle">Adim 1 &mdash; Proje iskeleti</p>
      </header>

      <section className={`status-card status-card--${status.kind}`}>
        {status.kind === 'loading' && (
          <p className="status-line">Backend durumu: kontrol ediliyor&hellip;</p>
        )}

        {status.kind === 'ok' && (
          <p className="status-line">Backend durumu: {status.value}</p>
        )}

        {status.kind === 'error' && (
          <>
            <p className="status-line">Backend durumu: baglanti kurulamadi</p>
            <p className="status-detail">{status.message}</p>
            <p className="status-hint">
              Backend'i baslatmak icin <code>backend</code> klasorunde:
              <br />
              <code>uvicorn app.main:app --reload</code>
            </p>
          </>
        )}

        <button
          type="button"
          className="retry-button"
          onClick={retry}
          disabled={status.kind === 'loading'}
        >
          Tekrar dene
        </button>
      </section>
    </main>
  )
}

export default App
