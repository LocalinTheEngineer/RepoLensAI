import { useEffect, useRef } from 'react'
import ChatMessage, { type ChatTurn } from './ChatMessage'

type Props = {
  turns: ChatTurn[]
  question: string
  onQuestionChange: (value: string) => void
  onSubmit: () => void
  /** Repository indekslenmeden soru sorulamaz. */
  ready: boolean
  busy: boolean
}

/** Ornek sorular. Flask uzerinde denenip cevaplandigi dogrulananlar. */
const EXAMPLES = [
  'how does request routing work',
  'how is the session cookie signed',
  'how does the CLI find the app',
]

/** Soru-cevap sohbeti: gecmis turlar ve altta soru kutusu. */
function ChatPanel({
  turns,
  question,
  onQuestionChange,
  onSubmit,
  ready,
  busy,
}: Props) {
  const lastTurnRef = useRef<HTMLDivElement>(null)

  // Son turun cevabi hangi durumda? Bagimlilik listesinde kullaniyoruz.
  const lastResultKind = turns[turns.length - 1]?.result.kind

  // Yeni soru sorulunca o turun BASINI ekrana getir.
  //
  // Neden sona degil de basa? Cevap uzun olabiliyor; sona kaydirirsak
  // kullanici cevabin sonunu gorur, basini kacirir.
  //
  // Neden iki kez (uzunluk VE durum degisince)? Soru eklendiginde asagida
  // sadece kisa bir "bekleniyor" balonu vardir, kaydiracak yer yoktur.
  // Cevap gelip icerik uzayinca ikinci kez kaydirmak soruyu tepeye tasir.
  useEffect(() => {
    if (turns.length === 0) return
    lastTurnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [turns.length, lastResultKind])

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <div className="chat">
      <div className="chat-scroll">
        {turns.length === 0 && (
          <div className="chat-empty">
            <h2>Repository hakkinda soru sor</h2>
            <p className="note">
              Cevap yalnizca repository&apos;deki gercek koddan uretilir. Kanit
              bulunamazsa model uydurmaz, bulamadigini soyler. Yazdigi her
              satir referansi, kendisine verilen kodla karsilastirilip
              dogrulanir.
            </p>
            <p className="note warning-note">
              Arama Ingilizce calisir; sorunu Ingilizce yaz.
            </p>

            {ready ? (
              <ul className="pill-list">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      type="button"
                      className="pill pill--button"
                      onClick={() => onQuestionChange(example)}
                    >
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="note">
                Once soldan bir repository ekleyip indeksle.
              </p>
            )}
          </div>
        )}

        {turns.map((turn, index) => (
          <div
            key={turn.id}
            ref={index === turns.length - 1 ? lastTurnRef : undefined}
          >
            <ChatMessage turn={turn} />
          </div>
        ))}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          className="repo-input"
          type="text"
          placeholder={
            ready
              ? 'how does request routing work'
              : 'Once bir repository indeksle'
          }
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          disabled={busy || !ready}
          autoComplete="off"
        />
        <button
          type="submit"
          className="repo-button"
          disabled={busy || !ready || question.trim() === ''}
        >
          {busy ? 'Dusunuyor...' : 'Sor'}
        </button>
      </form>
    </div>
  )
}

export default ChatPanel
