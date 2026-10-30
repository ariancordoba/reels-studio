// Si una pantalla falla, mostrar un aviso con salida (en vez de dejar toda la ventana en blanco)
// y mandar el error al log de la app para poder diagnosticarlo.
import { Component, type ReactNode } from "react";

interface State { error: Error | null }

export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    fetch("/api/log", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: String(error?.message ?? error), stack: error?.stack ?? "", component: info.componentStack ?? "", url: location.href }),
    }).catch(() => {});
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card p-10 text-center max-w-xl mx-auto mt-10">
        <div className="h-card">Algo falló en esta pantalla</div>
        <div className="label mt-2">No se perdió nada: tus proyectos y archivos están a salvo. Ya quedó anotado para revisarlo.</div>
        <div className="font-mono text-[12px] text-ink-muted mt-4 break-all">{String(this.state.error.message).slice(0, 200)}</div>
        <div className="flex gap-2 justify-center mt-6">
          <button className="btn-primary" onClick={() => { this.setState({ error: null }); location.hash = "#/inicio"; }}>Volver al inicio</button>
          <button className="btn-secondary" onClick={() => location.reload()}>Recargar</button>
        </div>
      </div>
    );
  }
}
