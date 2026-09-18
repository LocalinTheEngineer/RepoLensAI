import { SKIP_LABELS } from '../api'
import type {
  Async,
  ChunkScan,
  FileScan,
  Health,
  IndexResult,
  Repository,
} from '../api'
import HealthBadge from './HealthBadge'
import RepoForm from './RepoForm'

type Props = {
  health: Async<Health>
  onHealthRetry: () => void

  url: string
  onUrlChange: (value: string) => void
  onSubmit: () => void
  busy: boolean

  clone: Async<Repository>
  scan: Async<FileScan>
  chunks: Async<ChunkScan>
  indexState: Async<IndexResult>
  onIndex: () => void
}

/** Sayi + etiket seklinde tek bir istatistik. */
function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

/**
 * Sol panel: repository ekleme, dosya ozeti ve indeksleme.
 *
 * Sohbet alani sagda kalir; buradaki her sey "hangi repo, neyi indeksledik"
 * sorusunu cevaplar.
 */
function Sidebar({
  health,
  onHealthRetry,
  url,
  onUrlChange,
  onSubmit,
  busy,
  clone,
  scan,
  chunks,
  indexState,
  onIndex,
}: Props) {
  const indexed = indexState.kind === 'ok' && indexState.data.state === 'ready'
  const indexBusy =
    indexState.kind === 'loading' ||
    (indexState.kind === 'ok' && !indexed)
  const stateLabels: Record<string, string> = {
    queued: 'Kuyrukta...',
    cloning: 'Indiriliyor...',
    parsing: 'Parcalaniyor...',
    embedding: 'Embedding hesaplaniyor...',
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <h1 className="brand">RepoLens AI</h1>
        <HealthBadge state={health} onRetry={onHealthRetry} />
      </div>

      <RepoForm
        url={url}
        onUrlChange={onUrlChange}
        onSubmit={onSubmit}
        busy={busy}
      />

      {clone.kind === 'error' && (
        <p className="sidebar-error">{clone.message}</p>
      )}

      {clone.kind === 'loading' && (
        <p className="note">Repository indiriliyor&hellip;</p>
      )}

      {clone.kind === 'ok' && (
        <section className="sidebar-block">
          <h2 className="sidebar-title">
            {clone.data.owner}/{clone.data.name}
          </h2>
          <p className="note">
            commit <code>{clone.data.commit.slice(0, 10)}</code>
            {clone.data.already_cloned && ' · daha once indirilmisti'}
          </p>
        </section>
      )}

      {scan.kind === 'loading' && <p className="note">Dosyalar taraniyor&hellip;</p>}
      {scan.kind === 'error' && <p className="sidebar-error">{scan.message}</p>}

      {scan.kind === 'ok' && (
        <section className="sidebar-block">
          <div className="stat-row">
            <Stat label="dosya" value={scan.data.selected_count} />
            <Stat label="satir" value={scan.data.total_lines} />
            {chunks.kind === 'ok' && (
              <Stat label="parca" value={chunks.data.chunk_count} />
            )}
          </div>

          {Object.keys(scan.data.by_extension).length > 0 && (
            <ul className="pill-list">
              {Object.entries(scan.data.by_extension).map(([ext, count]) => (
                <li key={ext} className="pill">
                  <code>{ext}</code> {count}
                </li>
              ))}
            </ul>
          )}

          {scan.data.skipped_count > 0 && (
            <details className="skipped">
              <summary>{scan.data.skipped_count} dosya elendi</summary>
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

          <details className="skipped">
            <summary>Dosyalar</summary>
            <div className="file-list">
              {scan.data.files.map((file) => (
                <div key={file.path} className="file-row">
                  <code className="file-path">{file.path}</code>
                  <span className="file-lines">{file.lines}</span>
                </div>
              ))}
            </div>
          </details>
        </section>
      )}

      {scan.kind === 'ok' && chunks.kind === 'ok' && (
        <section className="sidebar-block">
          <h3 className="sidebar-title">Yapi</h3>

          <ul className="pill-list">
            {Object.entries(scan.data.top_level_dirs).map(([dir, count]) => (
              <li key={dir} className="pill">
                <code>{dir}/</code> {count}
              </li>
            ))}
          </ul>

          {Object.keys(chunks.data.symbol_counts).length > 0 && (
            <ul className="pill-list">
              {Object.entries(chunks.data.symbol_counts).map(
                ([type, count]) => (
                  <li key={type} className="pill">
                    {type} {count}
                  </li>
                ),
              )}
            </ul>
          )}

          <details className="skipped">
            <summary>En buyuk dosyalar</summary>
            <div className="file-list">
              {scan.data.largest_files.map((file) => (
                <div key={file.path} className="file-row">
                  <code className="file-path">{file.path}</code>
                  <span className="file-lines">{file.lines}</span>
                </div>
              ))}
            </div>
          </details>
        </section>
      )}

      {chunks.kind === 'ok' && (
        <section className="sidebar-block">
          <h3 className="sidebar-title">Indeksleme</h3>

          {indexed ? (
            <p className="note">
              <span className="dot dot--ok" />
              {indexState.data.stored_count} parca arama veritabaninda
            </p>
          ) : (
            <p className="note">
              <span className="dot" />
              Henuz indekslenmedi
            </p>
          )}

          <button
            type="button"
            className="repo-button repo-button--block"
            onClick={onIndex}
            disabled={indexBusy}
          >
            {indexBusy
              ? (indexState.kind === 'ok' && stateLabels[indexState.data.state]) ||
                'Indeksleniyor...'
              : indexed
                ? 'Yeniden indeksle'
                : 'Indeksle'}
          </button>

          {indexState.kind === 'error' && (
            <p className="sidebar-error">{indexState.message}</p>
          )}

          {indexed && (
            <p className="note">
              {(indexState.data.embed_duration_ms / 1000).toFixed(1)} sn
              embedding · {indexState.data.chunk_count} parca islendi
            </p>
          )}
        </section>
      )}
    </aside>
  )
}

export default Sidebar
