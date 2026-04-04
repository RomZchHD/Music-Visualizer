# PulseCanvas Music Visualizer

PulseCanvas is a desktop music visualizer built with Python, `PySide6`, `numpy`, `sounddevice`, and `soundfile`.

It is designed as a real, extensible desktop app rather than a one-file demo. The project separates playback, DSP analysis, UI, and visualizer modes so it is easy to keep improving.

## What The App Does

PulseCanvas can:

- open an audio file from disk
- open an audio file by dragging it onto the window
- play, pause, stop, and replay the file after it finishes
- compute real-time waveform and FFT spectrum data
- compute smoothed bass, mids, and treble energy
- switch visualizer modes while audio is playing
- render three built-in modes:
  - spectrum bars
  - waveform oscilloscope
  - radial spectrum
- control playback volume
- control visualizer intensity with a dedicated slider
- show the current track name, transport state, and playback time
- toggle fullscreen

## Supported Audio Formats

Directly supported through the normal decode path:

- `.wav`
- `.flac`
- `.ogg`
- `.mp3`
- `.aiff`
- `.aif`

Also supported through an `ffmpeg` fallback path:

- `.aac`
- `.opus`

If `soundfile` cannot decode a file, PulseCanvas will automatically try `ffmpeg` if it is available on your system `PATH`.

## Controls

- `Open File`: choose a track from disk
- Drag and drop: drop a local audio file anywhere on the window to load it
- `Play`: start playback or replay from the start if the file already ended
- `Pause`: pause playback
- `Stop`: stop playback and reset to the start
- `Mode`: switch between visualizers at runtime
- `Volume`: adjust playback output level
- `Intensity`: scale the visual response without changing the audio volume

Keyboard shortcuts:

- `Space`: play/pause
- `1`: spectrum bars
- `2`: waveform
- `3`: radial spectrum
- `F`: fullscreen

## Architecture

Project layout:

```text
main.py
app/
  __init__.py
  __main__.py
  main.py
  audio_engine.py
  config.py
  dsp.py
  models.py
  ui.py
  utils.py
  visualizers/
    __init__.py
    base.py
    bars.py
    waveform.py
    radial.py
tests/
  test_audio_engine.py
  test_dsp.py
DEVELOPER_NOTES.md
pyproject.toml
```

High-level flow:

1. `soundfile` loads the selected file when possible.
2. If that fails, `ffmpeg` is used as a decode fallback for formats such as AAC and Opus.
3. `sounddevice` plays audio through a low-latency output stream.
4. `AudioAnalyzer` in [`app/dsp.py`](/d:/Music%20Visualizer/app/dsp.py) computes waveform, spectrum, peak, RMS, and band energies.
5. The Qt UI in [`app/ui.py`](/d:/Music%20Visualizer/app/ui.py) polls the latest analysis frame and repaints the active renderer.

## Installation

Requirements:

- Python 3.11+
- `ffmpeg` on `PATH` if you want AAC/Opus fallback support

Install the project:

```powershell
py -3.11 -m pip install -e ".[dev]"
```

If you do not need editable mode:

```powershell
py -3.11 -m pip install ".[dev]"
```

## Run

Run from the repo:

```powershell
py -3.11 main.py
```

Or, after installation:

```powershell
music-visualizer
```

You can also launch with:

```powershell
py -3.11 -m app
```

## Testing

Run the test suite:

```powershell
py -3.11 -m pytest
```

The current tests cover:

- DSP helper behavior
- waveform window responsiveness
- replaying after end-of-file
- loading AAC and Opus files when `ffmpeg` is available

## Major Design Choices

- `PySide6` was chosen for a native desktop UI and flexible custom drawing.
- `numpy` is used for low-overhead frame analysis and FFT-based spectral features.
- `sounddevice` keeps audio playback low-latency and lets audio timing drive the visuals.
- Visualizer modes are plug-in classes with a shared `BaseVisualizer` interface.
- The waveform visualizer now uses a shorter recent window and fixed visual gain with soft clipping, so loud passages respond more immediately instead of visually riding the recent peak.

## Known Limitations

- Files are currently decoded fully into memory when opened.
- There is no seek/scrub transport yet.
- Live microphone or system-loopback input is not implemented yet.
- AAC/Opus fallback depends on `ffmpeg` being installed and reachable from `PATH`.
- Rendering quality and latency can still vary by GPU driver, Qt backend, and audio device.

## How To Add A New Visualizer Mode

1. Create a new renderer class under /d:/Music%20Visualizer/app/visualizers.
2. Subclass [`BaseVisualizer`](/d:/Music%20Visualizer/app/visualizers/base.py).
3. Give the class a unique `mode_id` and `display_name`.
4. Implement `render(self, painter, rect, frame)`.
5. Register the visualizer in [`app/visualizers/__init__.py`](/d:/Music%20Visualizer/app/visualizers/__init__.py).

The shared `AnalysisFrame` already contains:

- `waveform`
- `spectrum`
- `bands`
- `peak`
- `rms`
- `timestamp`

Each renderer also receives the shared intensity multiplier through `BaseVisualizer`.

## Troubleshooting

- If a file will not open, try a WAV file first to confirm the basic decode path works.
- If AAC or Opus files fail, verify `ffmpeg -version` works in your terminal.
- If playback works once but not again, update to the latest project version; replay-after-end is handled explicitly in the current engine.
- If the waveform feels too aggressive or too subtle, adjust the `Intensity` slider instead of the `Volume` slider.
