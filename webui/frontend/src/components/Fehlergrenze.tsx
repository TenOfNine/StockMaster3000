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
