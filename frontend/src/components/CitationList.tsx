import type { Citation } from '../api'

type Props = {
  citations: Citation[]
  unverified: number
}

/** Her durum icin ekranda gosterilecek etiket ve aciklama. */
const STATUS_INFO: Record<
  Citation['status'],
  { symbol: string; label: string; title: string }
> = {
  verified: {
    symbol: '✓',
    label: 'dogrulandi',
    title: 'Bu satirlar modele gercekten gosterildi.',
  },
  out_of_range: {
    symbol: '!',
    label: 'aralik disi',
    title:
      'Dosya dogru ama bu satirlar modele verilen parcanin disinda kaliyor.',
  },
  unknown_file: {
    symbol: '✕',
    label: 'uydurma',
    title: 'Bu dosya modele hic verilmedi.',
  },
}

/**
 * Cevap metnindeki kaynak referanslarini ve dogrulama sonuclarini gosterir.
 *
 * Amac: modelin yazdigi "dosya:satir" referanslarina koru koru guvenmemek.
 * Her referans, modele GERCEKTEN verilen kod parcalariyla karsilastirilir.
 */
function CitationList({ citations, unverified }: Props) {
  if (citations.length === 0) {
    return (
      <p className="note">
        Bu cevapta satir referansi yok. Asagidaki kaynak kartlari yine de
        cevabin dayandigi kod parcalarini gosteriyor.
      </p>
    )
  }

  return (
    <div className="citations">
      <p className="note">
        {citations.length} referans &middot;{' '}
        {unverified === 0 ? (
          <strong>hepsi dogrulandi</strong>
        ) : (
          <strong className="citation-warning-text">
            {unverified} tanesi dogrulanamadi
          </strong>
        )}
      </p>

      <ul className="citation-list">
        {citations.map((citation) => {
          const info = STATUS_INFO[citation.status]
          const target = citation.chunk_id
          return (
            <li key={`${citation.file_path}:${citation.start_line}-${citation.end_line}`}>
              <button
                type="button"
                className={`citation citation--${citation.status}`}
                title={info.title}
                disabled={target === null}
                onClick={() => {
                  if (!target) return
                  document
                    .getElementById(`source-${target}`)
                    ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
                }}
              >
                <span className="citation-symbol">{info.symbol}</span>
                <code>
                  {citation.file_path}:{citation.start_line}&ndash;
                  {citation.end_line}
                </code>
              </button>
            </li>
          )
        })}
      </ul>

      {unverified > 0 && (
        <p className="citation-warning">
          Isaretli referanslar modele verilen kod parcalariyla eslesmiyor.
          Cevabin o kismina guvenmeden once kaynaklari kendin kontrol et.
        </p>
      )}
    </div>
  )
}

export default CitationList
