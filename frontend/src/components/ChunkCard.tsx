import type { ChunkScan } from '../api'

type Props = {
  chunks: ChunkScan
}

/** Kodun kac parcaya bolundugunu ve orneklerini gosterir. */
function ChunkCard({ chunks }: Props) {
  return (
    <section className="result scan">
      <h2>Kod parcalari</h2>
      <p>
        <strong>{chunks.file_count}</strong> dosyadan{' '}
        <strong>{chunks.chunk_count}</strong> parca uretildi &mdash; parca
        basina ortalama <strong>{chunks.average_lines_per_chunk}</strong> satir.
      </p>
      <p className="note">
        Her parca en fazla {chunks.chunk_size_lines} satir; ardisik parcalar{' '}
        {chunks.chunk_overlap_lines} satir ortusur, boylece sinira denk gelen
        bir fonksiyon ikiye bolunup baglamini kaybetmez.
      </p>

      <details className="skipped">
        <summary>Parca onizlemelerini goster</summary>
        <div className="chunk-list">
          {chunks.chunks.map((chunk) => (
            <article key={chunk.chunk_id} className="chunk">
              <header className="chunk-header">
                <code className="file-path">{chunk.file_path}</code>
                <span className="file-lines">
                  {chunk.start_line}&ndash;{chunk.end_line} ({chunk.line_count}{' '}
                  satir)
                </span>
              </header>
              <pre className="chunk-preview">{chunk.preview}</pre>
            </article>
          ))}
        </div>
      </details>
    </section>
  )
}

export default ChunkCard
