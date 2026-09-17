import cytoscape from 'cytoscape'
import { useEffect, useRef } from 'react'
import type { Async, DependencyGraph } from '../api'

type Props = {
  state: Async<DependencyGraph>
  ready: boolean
  onLoad: () => void
}

/** Dosyanin sadece son ismini gosterir; tam yol dugumun tooltip'inde/id'sinde kalir. */
function shortLabel(path: string): string {
  return path.split('/').pop() ?? path
}

/** Dosya-seviyesi bagimlilik grafigi: repo-ici importlar, cytoscape ile cizilir. */
function DependencyGraphPanel({ state, ready, onLoad }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (state.kind !== 'ok' || !containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...state.data.nodes.map((path) => ({
          data: { id: path, label: shortLabel(path) },
        })),
        ...state.data.edges.map((edge) => ({
          data: {
            id: `${edge.source}->${edge.target}`,
            source: edge.source,
            target: edge.target,
          },
        })),
      ],
      layout: { name: 'cose', animate: false },
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-size': 8,
            width: 16,
            height: 16,
            'background-color': '#5b8dee',
            color: '#c7ccd4',
            'text-valign': 'bottom',
            'text-margin-y': 4,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1,
            'line-color': '#4a5160',
            'target-arrow-color': '#4a5160',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.7,
            'curve-style': 'bezier',
          },
        },
      ],
    })

    return () => cy.destroy()
  }, [state])

  return (
    <section className="result scan">
      <h2>Bagimlilik grafigi</h2>
      <p className="note">
        Dosyalarin birbirini nasil import ettigini gosterir. Dis kutuphaneler
        (flask, react...) grafige girmez; yalnizca repo-ici bagimliliklar.
      </p>

      {!ready && (
        <p className="note">
          Grafigi cikartabilmek icin once repository&apos;yi indekslemelisin.
        </p>
      )}

      {ready && state.kind === 'idle' && (
        <button type="button" className="repo-button" onClick={onLoad}>
          Grafigi cikart
        </button>
      )}

      {state.kind === 'loading' && (
        <p className="note">Grafik cikartiliyor&hellip;</p>
      )}

      {state.kind === 'error' && (
        <p className="query-error">{state.message}</p>
      )}

      {state.kind === 'ok' && (
        <>
          <p className="note">
            {state.data.nodes.length} dosya &middot; {state.data.edges.length}{' '}
            bagimlilik
          </p>
          <div ref={containerRef} className="dependency-graph" />
        </>
      )}
    </section>
  )
}

export default DependencyGraphPanel
