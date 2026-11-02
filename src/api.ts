import { callable } from "@decky/api";

export interface ControlError {
  code: string;
  message: string;
}

export interface AudioState {
  available: boolean;
  volume: number | null;
  muted: boolean | null;
  device_id: string | null;
  device_name: string | null;
  error: ControlError | null;
}

export interface BrightnessState {
  available: boolean;
  percent: number | null;
  levels: number[];
  instance_name: string | null;
  error: ControlError | null;
}

export interface SystemState {
  audio: AudioState;
  brightness: BrightnessState;
  updated_at: string;
}

export interface ControlApi {
  getState(): Promise<SystemState>;
  getCapabilities(): Promise<unknown>;
  getDiagnostics(): Promise<unknown>;
  setVolume(percent: number, expectedDeviceId: string): Promise<SystemState>;
  setMute(muted: boolean, expectedDeviceId: string): Promise<SystemState>;
  setBrightness(percent: number, expectedInstanceName: string): Promise<SystemState>;
}

export const api: ControlApi = {
  getState: callable<[], SystemState>("get_state"),
  getCapabilities: callable<[], unknown>("get_capabilities"),
  getDiagnostics: callable<[], unknown>("get_diagnostics"),
  setVolume: callable<[percent: number, expected_device_id: string], SystemState>("set_volume"),
  setMute: callable<[muted: boolean, expected_device_id: string], SystemState>("set_mute"),
  setBrightness: callable<[percent: number, expected_instance_name: string], SystemState>("set_brightness"),
};
