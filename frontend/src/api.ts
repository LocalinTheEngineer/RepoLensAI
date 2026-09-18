/** Backend ile konusmak icin gereken tipler ve yardimcilar. */

/**
 * Backend'in adresi.
 *
 * Vite ortam degiskenleri DERLEME aninda gomulur; bu yuzden farkli bir
 * sunucuya deploy ederken `VITE_API_URL` build sirasinda verilmelidir
 * (Dockerfile bunu bir build argumani olarak alir). Verilmezse yerel
 * gelistirme adresi kullanilir.
 */
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

/** Bir istegin icinde bulunabilecegi dort durum. */
export type Async<T> =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: T }
  | { kind: 'error'; message: string }

export type Health = { status: string }

export type Repository = {
  owner: string
  name: string
  path: string
  commit: string
  already_cloned: boolean
}

export type RepositoryFile = {
  path: string
  extension: string
  size_bytes: number
  lines: number
}

export type FileScan = {
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
  top_level_dirs: Record<string, number>
  largest_files: RepositoryFile[]
}

export type ChunkSummary = {
  chunk_id: string
  file_path: string
  start_line: number
  end_line: number
  line_count: number
  preview: string
  symbol_name: string | null
  symbol_type: string | null
}

export type ChunkScan = {
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
  symbol_counts: Record<string, number>
}

/** Adim 20: indeksleme arka planda calisir, bu durumlardan biriyle ilerler. */
export type IndexJobState =
  | 'queued'
  | 'parsing'
  | 'embedding'
  | 'ready'
  | 'failed'

export type IndexResult = {
  owner: string
  name: string
  state: IndexJobState
  error: string | null
  chunk_count: number
  stored_count: number
  embed_duration_ms: number
  store_duration_ms: number
}

export type SearchHit = {
  chunk_id: string
  file_path: string
  start_line: number
  end_line: number
  content: string
  score: number
  symbol_name: string | null
  symbol_type: string | null

  /** Yalnizca hybrid modda dolu: parcayi hangi yontem kacinci sirada buldu. */
  vector_rank: number | null
  keyword_rank: number | null

  /** Yalnizca rerank istendiginde dolu: cross-encoder puani. */
  rerank_score: number | null
}

/**
 * Arama modu: anlamsal (embedding), kelime tabanli (BM25) veya ikisinin
 * sira bazli birlestirilmis hali (hybrid).
 */
export type SearchMode = 'semantic' | 'keyword' | 'hybrid'

export type DependencyEdge = {
  source: string
  target: string
}

/** Dosya-seviyesi import grafigi. Dis kutuphaneler grafige girmez. */
export type DependencyGraph = {
  owner: string
  name: string
  nodes: string[]
  edges: DependencyEdge[]
}

export type SearchResult = {
  owner: string
  name: string
  query: string
  mode: SearchMode
  duration_ms: number

  /** Rerank asamasinin suresi; rerank istenmediyse null. */
  rerank_ms: number | null

  hits: SearchHit[]
}

/**
 * Cevap metninde gecen bir kaynak referansi ve dogrulama sonucu.
 *
 * verified     -> referans araligi, modele verilen bir parcanin icinde
 * out_of_range -> dosya verilmis ama aralik parcalarin disina tasiyor
 * unknown_file -> dosya modele hic verilmemis (uydurma)
 */
export type Citation = {
  file_path: string
  start_line: number
  end_line: number
  status: 'verified' | 'out_of_range' | 'unknown_file'
  chunk_id: string | null
}

export type AskResult = {
  owner: string
  name: string
  question: string
  answer: string
  model: string
  retrieval_ms: number
  rerank_ms: number
  generation_ms: number
  sources: SearchHit[]
  citations: Citation[]
  unverified_citations: number
}

/** Backend'den gelen eleme sebeplerinin ekranda gosterilecek karsiliklari. */
export const SKIP_LABELS: Record<string, string> = {
  uretilmis_klasor: 'uretilmis klasor (node_modules, dist, build ...)',
  desteklenmeyen_uzanti: 'desteklenmeyen uzanti',
  cok_buyuk: 'cok buyuk dosya',
  binary_veya_bozuk: 'binary dosya',
  okunamadi: 'okunamadi',
  sir_iceriyor: 'sir iceriyor (API anahtari, ozel anahtar ...)',
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
export function describeError(error: unknown): string {
  if (error instanceof TypeError) {
    return `Backend'e ulasilamadi. ${API_URL} calisiyor mu?`
  }
  if (error instanceof Error) return error.message
  return 'Bilinmeyen bir hata olustu.'
}

/** Verilen adresten JSON okur; hata durumunda anlasilir mesajla firlatir. */
export async function fetchJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init)
  const body: unknown = await response.json()
  if (!response.ok) {
    throw new Error(readErrorMessage(body, response.status))
  }
  return body as T
}

/** JSON govdeli bir POST istegi hazirlar. */
export function postJson(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

/** Agent'in attigi tek bir adim: hangi araci hangi girdiyle cagirdi. */
export type AgentStep = {
  tool: string
  argument: string
  result_count: number
}

/**
 * Agent'in cevabi. `sources` tek bir aramanin sonucu degil, arastirma
 * boyunca biriken kanit havuzudur.
 */
export type InvestigateResult = {
  owner: string
  name: string
  question: string
  answer: string
  model: string
  duration_ms: number
  steps: AgentStep[]
  sources: SearchHit[]
  citations: Citation[]
  unverified_citations: number
}

/**
 * Adim 19: yalnizca degisen dosyalari yeniden indeksleyen guncelleme.
 * Once klonu son commit'e ceker, sonra icerik hash'lerini karsilastirir.
 */
export type ReindexResult = {
  owner: string
  name: string
  previous_commit: string | null
  commit: string
  added: string[]
  modified: string[]
  deleted: string[]
  unchanged_count: number
  chunk_count: number
  embed_duration_ms: number
  store_duration_ms: number
}
