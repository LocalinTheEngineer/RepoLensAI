import { SKIP_LABELS, type FileScan } from '../api'

type Props = {
  scan: FileScan
}

/** Hangi dosyalarin islenecegini, hangilerinin neden elendigini gosterir. */
function FileScanCard({ scan }: Props) {
  return (
    <section className="result scan">
      <h2>Islenecek dosyalar</h2>
      <p>
        Git tarafindan takip edilen <strong>{scan.total_tracked}</strong>{' '}
        dosyadan <strong>{scan.selected_count}</strong> tanesi secildi
        {scan.selected_count > 0 && (
          <>
            {' '}
            &mdash; toplam <strong>{scan.total_lines}</strong> satir
          </>
        )}
        .
      </p>

      {Object.keys(scan.by_extension).length > 0 && (
        <ul className="pill-list">
          {Object.entries(scan.by_extension).map(([extension, count]) => (
            <li key={extension} className="pill">
              <code>{extension}</code> {count}
            </li>
          ))}
        </ul>
      )}

      {scan.skipped_count > 0 && (
        <details className="skipped">
          <summary>{scan.skipped_count} dosya elendi &mdash; neden?</summary>
          <ul>
            {Object.entries(scan.skipped_reasons).map(([reason, count]) => (
              <li key={reason}>
                {SKIP_LABELS[reason] ?? reason}: <strong>{count}</strong>
              </li>
            ))}
          </ul>
        </details>
      )}

      {scan.files.length > 0 && (
        <details className="skipped">
          <summary>Dosya listesini goster</summary>
          <div className="file-list">
            {scan.files.map((file) => (
              <div key={file.path} className="file-row">
                <code className="file-path">{file.path}</code>
                <span className="file-lines">{file.lines} satir</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  )
}

export default FileScanCard
