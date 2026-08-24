import { useEffect, useLayoutEffect, useRef, useState } from "react";

export interface AudioWaveformProps {
  audioUrl: string;
  segmentStart: number;
  segmentDuration: number;
  currentTime: number;
  onSeek: (time: number) => void;
  ariaLabel: string;
}

interface WaveformSize {
  width: number;
  height: number;
}

const DEFAULT_WIDTH = 300;
const DEFAULT_HEIGHT = 40;
const BAR_WIDTH = 2;
const BAR_GAP = 2;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function finiteNonNegative(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

function getAudioContextConstructor(): typeof AudioContext | undefined {
  if (typeof window === "undefined") return undefined;

  return window.AudioContext
    ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

function readWaveformColor(
  canvas: HTMLCanvasElement,
  customProperty: string,
  tokenProperty: string,
  fallback: string,
): string {
  const styles = window.getComputedStyle(canvas);
  return styles.getPropertyValue(customProperty).trim()
    || styles.getPropertyValue(tokenProperty).trim()
    || fallback;
}

/**
 * Renders the decoded samples for one audio segment. `currentTime` and values
 * emitted through `onSeek` are relative to the start of that segment.
 */
export default function AudioWaveform({
  audioUrl,
  segmentStart,
  segmentDuration,
  currentTime,
  onSeek,
  ariaLabel,
}: AudioWaveformProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);
  const [size, setSize] = useState<WaveformSize>({
    width: DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
  });

  const duration = finiteNonNegative(segmentDuration);
  const rangeValue = clamp(finiteNonNegative(currentTime), 0, duration);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let audioContext: AudioContext | null = null;

    setAudioBuffer(null);

    if (!audioUrl) {
      return () => controller.abort();
    }

    const decodeAudio = async () => {
      try {
        // Media elements can populate Chrome's cache with an opaque range
        // response before this CORS fetch runs. Bypass that cache so decoding
        // always receives the API response with its CORS headers intact.
        const response = await fetch(audioUrl, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error(`Audio request failed with ${response.status}`);

        const encodedAudio = await response.arrayBuffer();
        if (disposed) return;

        const AudioContextConstructor = getAudioContextConstructor();
        if (!AudioContextConstructor) return;

        audioContext = new AudioContextConstructor();
        const decodedAudio = await audioContext.decodeAudioData(encodedAudio.slice(0));
        if (!disposed) setAudioBuffer(decodedAudio);
      } catch {
        if (!disposed) setAudioBuffer(null);
      } finally {
        if (audioContext) {
          try {
            await audioContext.close();
          } catch {
            // Decoding failure must not affect the accessible seek fallback.
          }
        }
      }
    };

    void decodeAudio();

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [audioUrl]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const updateSize = (width: number, height: number) => {
      if (width <= 0 || height <= 0) return;

      setSize((previous) => {
        if (previous.width === width && previous.height === height) return previous;
        return { width, height };
      });
    };

    const initialRect = container.getBoundingClientRect();
    updateSize(initialRect.width, initialRect.height);

    if (typeof ResizeObserver === "undefined") return undefined;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      updateSize(entry.contentRect.width, entry.contentRect.height);
    });
    observer.observe(container);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    const width = Math.max(1, size.width);
    const height = Math.max(1, size.height);
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1);
    const pixelWidth = Math.max(1, Math.round(width * pixelRatio));
    const pixelHeight = Math.max(1, Math.round(height * pixelRatio));

    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;

    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, width, height);

    if (!audioBuffer || duration <= 0) return;

    const startTime = finiteNonNegative(segmentStart);
    const sampleRate = audioBuffer.sampleRate;
    const sampleCount = audioBuffer.length;
    const channelData = Array.from(
      { length: audioBuffer.numberOfChannels },
      (_, channelIndex) => audioBuffer.getChannelData(channelIndex),
    );
    if (channelData.length === 0 || sampleRate <= 0 || sampleCount <= 0) return;

    const barStride = BAR_WIDTH + BAR_GAP;
    const barCount = Math.max(1, Math.floor((width + BAR_GAP) / barStride));
    const secondsPerBar = duration / barCount;
    const playedWidth = width * (rangeValue / duration);
    const playedColor = readWaveformColor(
      canvas,
      "--audio-waveform-played",
      "--blue",
      "#124fe5",
    );
    const remainingColor = readWaveformColor(
      canvas,
      "--audio-waveform-remaining",
      "--line-strong",
      "#cdd5e2",
    );

    const peaks = Array.from({ length: barCount }, () => 0);

    for (let barIndex = 0; barIndex < barCount; barIndex += 1) {
      const barStartTime = startTime + barIndex * secondsPerBar;
      const barEndTime = startTime + (barIndex + 1) * secondsPerBar;
      const firstSample = clamp(Math.floor(barStartTime * sampleRate), 0, sampleCount);
      const lastSample = clamp(Math.ceil(barEndTime * sampleRate), 0, sampleCount);

      for (const samples of channelData) {
        for (let sampleIndex = firstSample; sampleIndex < lastSample; sampleIndex += 1) {
          peaks[barIndex] = Math.max(peaks[barIndex], Math.abs(samples[sampleIndex] ?? 0));
        }
      }
    }

    // Normalize against the segment's 95th-percentile peak. This keeps quiet
    // source files legible without changing the relative shape of their audio.
    const audiblePeaks = peaks.filter((peak) => peak > 0.00001).sort((a, b) => a - b);
    const referencePeak = audiblePeaks.length > 0
      ? audiblePeaks[Math.floor((audiblePeaks.length - 1) * 0.95)]
      : 0;

    for (let barIndex = 0; barIndex < barCount; barIndex += 1) {
      const peak = peaks[barIndex];
      const normalizedPeak = referencePeak > 0 ? clamp(peak / referencePeak, 0, 1) : 0;

      const x = barIndex * barStride;
      const barHeight = peak > 0.00001
        ? Math.max(3, normalizedPeak * height * 0.86)
        : 2;
      context.fillStyle = x + BAR_WIDTH / 2 <= playedWidth ? playedColor : remainingColor;
      context.fillRect(x, (height - barHeight) / 2, BAR_WIDTH, barHeight);
    }
  }, [audioBuffer, duration, rangeValue, segmentStart, size]);

  return (
    <div
      ref={containerRef}
      className="audio-waveform"
      data-waveform-state={audioBuffer ? "ready" : "fallback"}
    >
      <canvas ref={canvasRef} className="audio-waveform__canvas" aria-hidden="true" />
      <input
        className="audio-waveform__range"
        type="range"
        min={0}
        max={duration}
        step={0.01}
        value={rangeValue}
        disabled={duration <= 0}
        aria-label={ariaLabel}
        onChange={(event) => onSeek(clamp(Number(event.currentTarget.value), 0, duration))}
      />
    </div>
  );
}
