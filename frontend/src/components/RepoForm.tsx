type Props = {
  url: string
  onUrlChange: (value: string) => void
  onSubmit: () => void
  busy: boolean
}

/** Kullanicinin GitHub adresini girdigi form. */
function RepoForm({ url, onUrlChange, onSubmit, busy }: Props) {
  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    // Tarayicinin varsayilan davranisi sayfayi yeniden yuklemek; bunu istemiyoruz.
    event.preventDefault()
    onSubmit()
  }

  return (
    <form className="repo-form" onSubmit={handleSubmit}>
      <label className="repo-label" htmlFor="repo-url">
        Public GitHub repository adresi
      </label>
      <div className="repo-row">
        <input
          id="repo-url"
          className="repo-input"
          type="text"
          placeholder="https://github.com/kullanici/repo"
          value={url}
          onChange={(event) => onUrlChange(event.target.value)}
          disabled={busy}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="submit"
          className="repo-button"
          disabled={busy || url.trim() === ''}
        >
          {busy ? 'Calisiyor...' : 'Indir'}
        </button>
      </div>
    </form>
  )
}

export default RepoForm
