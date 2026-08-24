import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AudioWaveform from "./AudioWaveform";

interface DrawCall {
  color: string;
  height: number;
}

const originalCanvasContext = Object.getOwnPropertyDescriptor(
  HTMLCanvasElement.prototype,
  "getContext",
);
const originalDevicePixelRatio = Object.getOwnPropertyDescriptor(window, "devicePixelRatio");

let resizeCallback: ResizeObserverCallback | null = null;
let observedElement: Element | null = null;
let drawCalls: DrawCall[] = [];
let currentFillStyle = "";

const canvasContext = {
  clearRect: vi.fn(),
  fillRect: vi.fn((_x: number, _y: number, _width: number, height: number) => {
    drawCalls.push({ color: currentFillStyle, height });
  }),
  setTransform: vi.fn(),
};

Object.defineProperty(canvasContext, "fillStyle", {
  configurable: true,
  get: () => currentFillStyle,
  set: (value: string) => {
    currentFillStyle = value;
  },
});

class MockResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback;
  }

  observe(target: Element) {
    observedElement = target;
    this.resize(80, 24);
  }

  unobserve() {}

  disconnect() {}

  resize(width: number, height: number) {
    if (!resizeCallback || !observedElement) return;
    resizeCallback(
      [{
        target: observedElement,
        contentRect: { width, height },
      } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
}

function triggerResize(width: number, height: number) {
  if (!resizeCallback || !observedElement) throw new Error("Waveform is not being observed");
  resizeCallback(
    [{
      target: observedElement,
      contentRect: { width, height },
    } as ResizeObserverEntry],
    {} as ResizeObserver,
  );
}

function createDecodedBuffer(): AudioBuffer {
  const samples = Float32Array.from([0, 0, 0, 0, 0.25, 0.5, 1, 0.5]);
  return {
    duration: 2,
    length: samples.length,
    numberOfChannels: 1,
    sampleRate: 4,
    getChannelData: vi.fn(() => samples),
  } as unknown as AudioBuffer;
}

function installSuccessfulDecode() {
  const decodedBuffer = createDecodedBuffer();
  const decodeAudioData = vi.fn().mockResolvedValue(decodedBuffer);
  const close = vi.fn().mockResolvedValue(undefined);

  class MockAudioContext {
    decodeAudioData = decodeAudioData;
    close = close;
  }

  vi.stubGlobal("AudioContext", MockAudioContext);
  return { decodeAudioData, close };
}

beforeEach(() => {
  resizeCallback = null;
  observedElement = null;
  drawCalls = [];
  currentFillStyle = "";
  vi.clearAllMocks();
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 2 });
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    configurable: true,
    value: vi.fn(() => canvasContext as unknown as CanvasRenderingContext2D),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();

  if (originalCanvasContext) {
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", originalCanvasContext);
  }
  if (originalDevicePixelRatio) {
    Object.defineProperty(window, "devicePixelRatio", originalDevicePixelRatio);
  }
});

describe("AudioWaveform", () => {
  it("decodes real audio samples, draws played and remaining peaks, and responds to resize", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => new ArrayBuffer(16),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const { decodeAudioData, close } = installSuccessfulDecode();

    const { container } = render(
      <AudioWaveform
        audioUrl="/api/materials/1/audio"
        segmentStart={1}
        segmentDuration={1}
        currentTime={0.5}
        onSeek={() => undefined}
        ariaLabel="Sentence audio position"
      />,
    );

    await waitFor(() => {
      expect(container.querySelector(".audio-waveform")).toHaveAttribute("data-waveform-state", "ready");
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/materials/1/audio",
      expect.objectContaining({ signal: expect.any(AbortSignal), cache: "no-store" }),
    );
    expect(decodeAudioData).toHaveBeenCalledOnce();
    expect(close).toHaveBeenCalledOnce();
    expect(drawCalls.some(({ color }) => color === "#124fe5")).toBe(true);
    expect(drawCalls.some(({ color }) => color === "#cdd5e2")).toBe(true);
    expect(drawCalls.some(({ height }) => height > 2)).toBe(true);

    const canvas = container.querySelector("canvas");
    expect(canvas).toHaveAttribute("width", "160");
    expect(canvas).toHaveAttribute("height", "48");
    const drawCountBeforeResize = drawCalls.length;

    act(() => triggerResize(120, 32));

    expect(canvas).toHaveAttribute("width", "240");
    expect(canvas).toHaveAttribute("height", "64");
    expect(drawCalls.length).toBeGreaterThan(drawCountBeforeResize);
  });

  it("keeps seek values segment-relative, clamped, and keyboard accessible", () => {
    const onSeek = vi.fn();

    render(
      <AudioWaveform
        audioUrl=""
        segmentStart={12}
        segmentDuration={2}
        currentTime={3}
        onSeek={onSeek}
        ariaLabel="Seek sentence"
      />,
    );

    const range = screen.getByRole("slider", { name: "Seek sentence" });
    expect(range).toHaveAttribute("min", "0");
    expect(range).toHaveAttribute("max", "2");
    expect(range).toHaveValue("2");

    fireEvent.change(range, { target: { value: "0.75" } });
    expect(onSeek).toHaveBeenCalledWith(0.75);
  });

  it("falls back to the seek range without logging when audio cannot be loaded", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchMock);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    const { container } = render(
      <AudioWaveform
        audioUrl="/missing.wav"
        segmentStart={0}
        segmentDuration={1.5}
        currentTime={0.25}
        onSeek={() => undefined}
        ariaLabel="Fallback seek"
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => Promise.resolve());

    expect(container.querySelector(".audio-waveform")).toHaveAttribute("data-waveform-state", "fallback");
    expect(screen.getByRole("slider", { name: "Fallback seek" })).toBeEnabled();
    expect(consoleError).not.toHaveBeenCalled();
  });
});
