import type { Async } from '../api'

type Props = {
  /** Izlenecek istek durumu. */
  state: Async<unknown>
  /** Yuklenirken gosterilecek metin. */
  loadingText: string
  /** Hata kutusunun basligi. */
  errorTitle: string
}

/**
 * Bir istegin "yukleniyor" ve "hata" durumlarini gosterir.
 *
 * Basarili ve bos durumlarda hicbir sey cizmez (null doner); onlari cagiran
 * bilesen kendi icerigiyle gosterir. Boylece her bolumde ayni iki durumu
 * tekrar tekrar yazmaktan kurtuluyoruz.
 */
function Feedback({ state, loadingText, errorTitle }: Props) {
  if (state.kind === 'loading') {
    return (
      <section className="result">
        <p>{loadingText}</p>
      </section>
    )
  }

  if (state.kind === 'error') {
    return (
      <section className="result result--error">
        <h2>{errorTitle}</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  return null
}

export default Feedback
