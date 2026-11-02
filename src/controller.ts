import type { ControlApi, ControlError, SystemState } from "./api";
import { WriteQueue } from "./writeQueue.js";

type WriteKind = "volume" | "mute" | "brightness";
type Write = { kind: WriteKind; target: string; value: number | boolean; version: number };

export interface PanelModel {
  state: SystemState | null;
  loading: boolean;
  connectionError: string | null;
  audioError: string | null;
  brightnessError: string | null;
  draftVolume: number | null;
  draftMute: boolean | null;
  draftBrightness: number | null;
}

export const initialModel: PanelModel = {
  state: null, loading: true, connectionError: null,
  audioError: null, brightnessError: null,
  draftVolume: null, draftMute: null, draftBrightness: null,
};

export function controlError(error: ControlError | null | undefined): string | null {
  if (!error) return null;
  const messages: Record<string, string> = {
    unsupported: "Este control no está disponible en el dispositivo.",
    device_unavailable: "Dispositivo no disponible. Vuelve a conectar la salida.",
    device_changed: "El dispositivo ha cambiado. Ajusta de nuevo el control.",
    stale_device: "El dispositivo ha cambiado. Ajusta de nuevo el control.",
    access_denied: "Windows no ha permitido el cambio.",
    timeout: "El control no responde. Recarga el plugin para reintentarlo.",
    operation_failed: "No se pudo completar la operación.",
  };
  return messages[error.code] ?? "No se pudo acceder al control de Windows.";
}

/** One mounted panel owns its polling and independent audio/brightness queues. */
export class PanelController {
  private backend: ControlApi;
  private changed: (model: PanelModel) => void;
  private model: PanelModel = { ...initialModel };
  private active = true;
  private polling = false;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private request = 0;
  private applied = { audio: 0, brightness: 0 };
  private versions = { volume: 0, mute: 0, brightness: 0 };
  private settled = { volume: 0, mute: 0, brightness: 0 };
  private interactionTargets = new Map<"volume" | "brightness", string>();
  private audioQueue: WriteQueue<Write>;
  private brightnessQueue: WriteQueue<Write>;

  constructor(backend: ControlApi, changed: (model: PanelModel) => void) {
    this.backend = backend;
    this.changed = changed;
    this.audioQueue = new WriteQueue((write) => this.execute(write));
    this.brightnessQueue = new WriteQueue((write) => this.execute(write));
  }

  start(): void {
    void this.poll();
  }

  refresh(): void {
    if (this.pollTimer !== null) clearTimeout(this.pollTimer);
    this.pollTimer = null;
    void this.poll();
  }

  setVolume(percent: number): void {
    const audio = this.model.state?.audio;
    if (!audio?.available || !audio.device_id || !Number.isFinite(percent)) return;
    if (this.interactionTargets.has("volume") && this.interactionTargets.get("volume") !== audio.device_id) return;
    const value = Math.max(0, Math.min(100, Math.round(percent)));
    this.update({ draftVolume: value, audioError: null });
    this.audioQueue.push({ kind: "volume", target: audio.device_id, value, version: ++this.versions.volume });
  }

  setMute(muted: boolean): void {
    const audio = this.model.state?.audio;
    if (!audio?.available || !audio.device_id) return;
    this.update({ draftMute: muted, audioError: null });
    this.audioQueue.push({ kind: "mute", target: audio.device_id, value: muted, version: ++this.versions.mute });
    this.audioQueue.flush();
  }

  setBrightness(percent: number): void {
    const brightness = this.model.state?.brightness;
    if (!brightness?.available || !brightness.instance_name || !Number.isFinite(percent)) return;
    if (this.interactionTargets.has("brightness") && this.interactionTargets.get("brightness") !== brightness.instance_name) return;
    const levels = brightness.levels.filter((level) => Number.isFinite(level) && level >= 0 && level <= 100);
    if (!levels.length) return;
    const requested = Math.max(0, Math.min(100, Math.round(percent)));
    const value = levels.reduce((nearest, level) => Math.abs(level - requested) < Math.abs(nearest - requested) ? level : nearest);
    this.update({ draftBrightness: value, brightnessError: null });
    this.brightnessQueue.push({ kind: "brightness", target: brightness.instance_name, value, version: ++this.versions.brightness });
  }

  flushAudio(): void { this.audioQueue.flush(); }
  flushBrightness(): void { this.brightnessQueue.flush(); }

  beginInteraction(kind: "volume" | "brightness"): void {
    if (this.interactionTargets.has(kind)) return;
    const target = kind === "volume" ? this.model.state?.audio.device_id : this.model.state?.brightness.instance_name;
    if (target) this.interactionTargets.set(kind, target);
  }

  endInteraction(kind: "volume" | "brightness"): void {
    this.interactionTargets.delete(kind);
    if (kind === "volume") this.audioQueue.flush();
    else this.brightnessQueue.flush();
    if (this.settled[kind] === this.versions[kind]) {
      this.update({ [kind === "volume" ? "draftVolume" : "draftBrightness"]: null });
    }
  }

  dispose(): void {
    this.active = false;
    if (this.pollTimer !== null) clearTimeout(this.pollTimer);
    this.pollTimer = null;
    this.audioQueue.dispose();
    this.brightnessQueue.dispose();
  }

  private update(patch: Partial<PanelModel>): void {
    if (!this.active) return;
    this.model = { ...this.model, ...patch };
    this.changed(this.model);
  }

  private accept(state: SystemState, request: number, scope: "both" | "audio" | "brightness" = "both", blocked = { audio: false, brightness: false }): void {
    if (!this.active) return;
    const previous = this.model.state;
    const sameAudio = previous?.audio.device_id === state.audio.device_id && state.audio.available;
    const sameBrightness = previous?.brightness.instance_name === state.brightness.instance_name && state.brightness.available;
    const audioPending = blocked.audio || this.model.draftVolume !== null || this.model.draftMute !== null;
    const brightnessPending = blocked.brightness || this.model.draftBrightness !== null;
    const acceptAudio = scope !== "brightness" && request >= this.applied.audio && !(scope === "both" && sameAudio && audioPending);
    const acceptBrightness = scope !== "audio" && request >= this.applied.brightness && !(scope === "both" && sameBrightness && brightnessPending);
    const audio = acceptAudio ? state.audio : previous?.audio ?? state.audio;
    const brightness = acceptBrightness ? state.brightness : previous?.brightness ?? state.brightness;
    if (acceptAudio) this.applied.audio = request;
    if (acceptBrightness) this.applied.brightness = request;
    const patch: Partial<PanelModel> = {
      state: { audio, brightness, updated_at: state.updated_at },
      loading: false, connectionError: null,
    };
    if (previous && (previous.audio.device_id !== audio.device_id || !audio.available)) {
      this.audioQueue.clear();
      ++this.versions.volume;
      ++this.versions.mute;
      patch.draftVolume = null;
      patch.draftMute = null;
      patch.audioError = null;
    }
    if (previous && (previous.brightness.instance_name !== brightness.instance_name || !brightness.available)) {
      this.brightnessQueue.clear();
      ++this.versions.brightness;
      patch.draftBrightness = null;
      patch.brightnessError = null;
    }
    this.update(patch);
  }

  private async poll(): Promise<void> {
    if (!this.active || this.polling) return;
    this.polling = true;
    const request = ++this.request;
    const blocked = { audio: this.model.draftVolume !== null || this.model.draftMute !== null, brightness: this.model.draftBrightness !== null };
    try {
      this.accept(await this.backend.getState(), request, "both", blocked);
    } catch {
      if (request >= Math.max(this.applied.audio, this.applied.brightness)) {
        this.update({ loading: false, connectionError: "No se pudo consultar Windows. Comprueba que el backend de Decky está disponible." });
      }
    } finally {
      this.polling = false;
      if (this.active) this.pollTimer = setTimeout(() => { this.pollTimer = null; void this.poll(); }, 1000);
    }
  }

  private async execute(write: Write): Promise<void> {
    if (!this.active) return;
    const brightness = write.kind === "brightness";
    const current = brightness ? this.model.state?.brightness.instance_name : this.model.state?.audio.device_id;
    if (current !== write.target) return;
    const request = ++this.request;
    try {
      const state = write.kind === "volume"
        ? await this.backend.setVolume(write.value as number, write.target)
        : write.kind === "mute"
          ? await this.backend.setMute(write.value as boolean, write.target)
          : await this.backend.setBrightness(write.value as number, write.target);
      this.accept(state, request, brightness ? "brightness" : "audio");
      if (!this.active || this.versions[write.kind] !== write.version) return;
      const error = controlError(brightness ? state.brightness.error : state.audio.error);
      this.update({ [brightness ? "brightnessError" : "audioError"]: error });
    } catch {
      if (this.versions[write.kind] === write.version) {
        this.update({ [brightness ? "brightnessError" : "audioError"]: "No se pudo confirmar el cambio. Se consultará el valor real." });
      }
    } finally {
      if (this.active && this.versions[write.kind] === write.version) {
        this.settled[write.kind] = write.version;
        if (write.kind === "mute" || !this.interactionTargets.has(write.kind)) {
          this.update({ [write.kind === "volume" ? "draftVolume" : write.kind === "mute" ? "draftMute" : "draftBrightness"]: null });
        }
      }
    }
  }
}
