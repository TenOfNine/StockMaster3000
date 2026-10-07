import { Component, type ErrorInfo, type ReactNode } from "react";

/** Fängt Darstellungsfehler ab, damit ein einzelner Bereich nicht die ganze Seite mitreißt. */
export class Fehlergrenze extends Component<{ children: ReactNode; ersatz: (fehler: Error) => ReactNode }, { fehler: Error | null }> {
  state: { fehler: Error | null } = { fehler: null };

  static getDerivedStateFromError(fehler: Error) {
    return { fehler };
  }

  componentDidCatch(fehler: Error, info: ErrorInfo) {
    console.error("Darstellungsfehler", fehler, info.componentStack);
  }

  render() {
    return this.state.fehler ? this.props.ersatz(this.state.fehler) : this.props.children;
  }
}

/** Schützt einen Seitenbereich: bei einem Darstellungsfehler erscheint nur dort ein Hinweis mit technischer Meldung. */
export function Geschuetzt({ name, children }: { name: string; children: ReactNode }) {
  return (
    <Fehlergrenze
      ersatz={(fehler) => (
        <div role="alert" className="mb-4 rounded-xl border border-schlecht/30 bg-schlecht-flaeche px-4 py-3 text-[13px] text-text">
          <b>{name}</b> konnte nicht angezeigt werden. Technische Meldung: <span className="font-mono">{fehler.message}</span>
          <details className="mt-1 text-text-3">
            <summary className="cursor-pointer">Einzelheiten</summary>
            <pre className="mt-1 max-h-40 overflow-auto font-mono text-[11px] whitespace-pre-wrap">{(fehler.stack ?? "").split("\n").slice(0, 8).join("\n")}</pre>
          </details>
        </div>
      )}
    >
      {children}
    </Fehlergrenze>
  );
}
