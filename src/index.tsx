import { definePlugin, useQuickAccessVisible } from "@decky/api";
import { ButtonItem, PanelSection, PanelSectionRow, SliderField, staticClasses } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { api } from "./api";
import { controlError, initialModel, PanelController } from "./controller";

const sessions = new Set<() => void>();
const noteStyle: CSSProperties = { fontSize: 13, lineHeight: 1.5, opacity: 0.8, margin: "4px 0 12px", overflowWrap: "anywhere" };
const errorStyle: CSSProperties = { ...noteStyle, color: "#f5bd8c", opacity: 1 };

function Status({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div role="status" style={error ? errorStyle : noteStyle}>{children}</div>;
}

function diagnosticRows(value: unknown): [string, string][] {
  if (!value || typeof value !== "object") return [];
  const data = value as Record<string, unknown>;
  const fields: [string, string[]][] = [
    ["Plugin", ["plugin_version"]],
    ["Decky", ["loader_version", "decky_version"]],
    ["Python", ["python_version"]],
    ["Arquitectura", ["architecture", "python_bits", "bits"]],
    ["Sistema", ["platform", "system"]],
    ["COM", ["comtypes_version"]],
  ];
  return fields.flatMap(([label, keys]) => {
    const item = keys.map((key) => data[key]).find((entry) => typeof entry === "string" || typeof entry === "number");
    if (item === undefined) return [];
    const text = String(item);
    // Only selected version/platform fields; never render dumps, paths, or secrets.
    if (text.length > 120 || !/^[\w .()+,\[\]-]+$/.test(text)) return [];
    return [[label, text] as [string, string]];
  });
}

function Content() {
  const visible = useQuickAccessVisible();
  const [model, setModel] = useState({ ...initialModel });
  const controller = useRef<PanelController | null>(null);
  const [diagnostics, setDiagnostics] = useState<[string, string][] | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const diagnosticGeneration = useRef(0);

  useEffect(() => {
    if (!visible) return;
    setModel({ ...initialModel });
    const session = new PanelController(api, setModel);
    controller.current = session;
    const finishInteraction = () => {
      session.endInteraction("volume");
      session.endInteraction("brightness");
    };
    const cleanup = () => {
      session.dispose();
      if (controller.current === session) controller.current = null;
      window.removeEventListener("pointerup", finishInteraction);
      window.removeEventListener("pointercancel", finishInteraction);
      ++diagnosticGeneration.current;
    };
    sessions.add(cleanup);
    window.addEventListener("pointerup", finishInteraction);
    window.addEventListener("pointercancel", finishInteraction);
    session.start();
    return () => { sessions.delete(cleanup); cleanup(); };
  }, [visible]);

  useEffect(() => {
    if (!visible) setDiagnosticsLoading(false);
    return () => { ++diagnosticGeneration.current; };
  }, [visible]);

  const loadDiagnostics = async () => {
    if (diagnosticsOpen) { setDiagnosticsOpen(false); return; }
    setDiagnosticsOpen(true);
    setDiagnosticsLoading(true);
    setDiagnosticsError(null);
    const generation = ++diagnosticGeneration.current;
    try {
      const value = await api.getDiagnostics();
      if (generation !== diagnosticGeneration.current) return;
      const rows = diagnosticRows(value);
      setDiagnostics(rows);
      if (!rows.length) setDiagnosticsError("El backend no ha devuelto información de versión disponible.");
    } catch {
      if (generation === diagnosticGeneration.current) setDiagnosticsError("No se pudo obtener el diagnóstico del backend.");
    } finally {
      if (generation === diagnosticGeneration.current) setDiagnosticsLoading(false);
    }
  };

  const audio = model.state?.audio;
  const brightness = model.state?.brightness;
  const audioReady = visible && !!audio?.available && !!audio.device_id;
  const levels = brightness?.levels.filter((level) => Number.isFinite(level) && level >= 0 && level <= 100) ?? [];
  const brightnessReady = visible && !!brightness?.available && !!brightness.instance_name && levels.length > 0;
  const volume = model.draftVolume ?? audio?.volume ?? null;
  const muted = model.draftMute ?? audio?.muted ?? null;
  const percent = model.draftBrightness ?? brightness?.percent ?? null;
  const audioError = model.audioError ?? controlError(audio?.error);
  const brightnessError = model.brightnessError ?? controlError(brightness?.error);
  const editingProps = (kind: "volume" | "brightness") => ({
    onPointerDownCapture: () => controller.current?.beginInteraction(kind),
    onKeyDownCapture: () => controller.current?.beginInteraction(kind),
    onKeyUpCapture: () => controller.current?.endInteraction(kind),
    onBlurCapture: () => controller.current?.endInteraction(kind),
  });

  return <>
    <PanelSection title="Sonido">
      {model.loading && <Status>Leyendo los controles de Windows…</Status>}
      {model.connectionError && <Status error>{model.connectionError}</Status>}
      <PanelSectionRow>
        <div {...editingProps("volume")}>
          <SliderField
            label="Volumen"
            description={audio?.device_name ?? (model.loading ? "Buscando salida de audio…" : "Sin salida de audio disponible")}
            value={volume ?? 0}
            min={0} max={100} step={1} minimumDpadGranularity={1}
            showValue={volume !== null} valueSuffix=" %"
            disabled={!audioReady || volume === null}
            onChange={(value) => controller.current?.setVolume(value)}
          />
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={!audioReady || muted === null}
          onClick={() => { if (muted !== null) controller.current?.setMute(!muted); }}
        >{muted ? "Activar sonido" : "Silenciar"}</ButtonItem>
      </PanelSectionRow>
      {muted && <Status>Sonido silenciado. El nivel de volumen se conserva.</Status>}
      {audioError && <Status error>{audioError}</Status>}
      {!model.loading && !audioReady && !audioError && !model.connectionError && <Status>Volumen no disponible.</Status>}
    </PanelSection>
    <PanelSection title="Pantalla integrada">
      <PanelSectionRow>
        <div {...editingProps("brightness")}>
          <SliderField
            label="Brillo"
            value={percent ?? 0}
            min={levels.length ? Math.min(...levels) : 0}
            max={levels.length ? Math.max(...levels) : 100}
            step={1} minimumDpadGranularity={1}
            showValue={percent !== null} valueSuffix=" %"
            disabled={!brightnessReady || percent === null}
            onChange={(value) => controller.current?.setBrightness(value)}
          />
        </div>
      </PanelSectionRow>
      {brightnessError && <Status error>{brightnessError}</Status>}
      {!model.loading && !brightnessReady && !brightnessError && !model.connectionError && <Status>Brillo no disponible para la pantalla integrada.</Status>}
    </PanelSection>
    <PanelSection>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => controller.current?.refresh()} disabled={model.loading}>Actualizar estado</ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={diagnosticsLoading} onClick={() => { void loadDiagnostics(); }}>
          {diagnosticsLoading ? "Consultando diagnóstico…" : diagnosticsOpen ? "Ocultar diagnóstico" : "Mostrar diagnóstico"}
        </ButtonItem>
      </PanelSectionRow>
      {diagnosticsOpen && <>
        {diagnosticsError && <Status error>{diagnosticsError}</Status>}
        {diagnostics && <dl style={noteStyle}>{diagnostics.map(([label, value]) => <div key={label}>
          <dt style={{ display: "inline", fontWeight: 600 }}>{label}: </dt>
          <dd style={{ display: "inline", margin: 0 }}>{value}</dd>
        </div>)}</dl>}
      </>}
    </PanelSection>
  </>;
}

function ControlIcon() {
  return <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path d="M4 3v18M12 3v18M20 3v18" />
    <path d="M1 8h6M9 16h6M17 9h6" strokeWidth="4" />
  </svg>;
}

export default definePlugin(() => ({
  name: "Ally System Control",
  titleView: <div className={staticClasses.Title}>Ally System Control</div>,
  content: <Content />,
  icon: <ControlIcon />,
  onDismount() {
    for (const cleanup of sessions) cleanup();
    sessions.clear();
  },
}));
