# PulseCanvas Music Visualizer

PulseCanvas is a desktop music visualizer built with Python, `PySide6`, `numpy`, `sounddevice`, `soundfile`, and Windows loopback capture via `soundcard`.

It supports two source modes:

- `File`: open and play a local audio file while visualizing it
- `System Audio (Windows)`: visualize whatever Windows is currently sending to a selected output device through WASAPI loopback

The app keeps playback/capture, DSP, UI, and visualizers separate so new source types and renderer modes can be added without rewriting the whole project.

## Features

- open an audio file from disk
- open an audio file by dragging it onto the window
- play, pause, stop, and replay files after they finish
- visualize live Windows system audio without microphone capture
- choose the Windows output device used for loopback capture
- refresh the device list without restarting the app
- compute real-time waveform, FFT spectrum, peak, RMS, and bass/mids/treble energy
- switch visualizer modes while audio is active
- render three built-in modes:
  - spectrum bars
  - waveform
  - radial spectrum
- control playback volume for file mode
- control visualizer intensity separately from audio volume
- show the active source, status, and either playback time or selected device
- toggle fullscreen

## Windows System Audio Support

System audio mode is Windows 10 only for now.

It uses WASAPI loopback capture through the `soundcard` package:

- it captures the selected Windows output device
- it does not use a microphone
- it does not require Stereo Mix or vendor-specific drivers
- it does not play the captured audio back out, so it does not create monitoring echo

If nothing is currently playing through Windows, the visuals naturally settle toward silence.

## Supported Audio Formats

Direct decode path:

- `.wav`
- `.flac`
- `.ogg`
- `.mp3`
- `.aiff`
- `.aif`

`ffmpeg` fallback path:

- `.aac`
- `.opus`

If `soundfile` cannot decode a file directly, PulseCanvas automatically tries `ffmpeg` when it is available on `PATH`.

## Controls

Main controls:

- `Source`: switch between `File` and `System Audio (Windows)`
- `Open File`: load a local track in file mode
- `Play` / `Pause`: file transport control
- `Start Capture`: start Windows loopback capture in system-audio mode
- `Stop`: stop file playback or stop system-audio capture
- `Output`: choose the Windows output device used for loopback capture
- `Refresh Devices`: rescan Windows output devices
- `Mode`: switch visualizer renderer
- `Volume`: file playback volume
- `Intensity`: visual response shaping

Source-specific behavior:

- In `File` mode, transport controls behave like a normal player.
- In `System Audio (Windows)` mode, file-only controls are disabled and the app shows the selected output device instead of file position.
- Drag-and-drop always loads a file and switches the app back to `File` mode.

Keyboard shortcuts:

- `Space`: play/pause in file mode, start capture in system-audio mode
- `1`: spectrum bars
- `2`: waveform
- `3`: radial spectrum
- `F`: fullscreen

## Project Layout

```text
main.py
app/
  __init__.py
  __main__.py
  main.py
  audio_engine.py
  audio_sources/
    __init__.py
    base.py
    file_playback.py
    system_loopback.py
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
  conftest.py
  test_audio_engine.py
  test_dsp.py
  test_system_loopback.py
  test_ui.py
DEVELOPER_NOTES.md
pyproject.toml
```

## Architecture

High-level flow:

1. [`app/audio_engine.py`](/d:/Music%20Visualizer/app/audio_engine.py) owns the active source mode and exposes one controller API to the UI.
2. [`app/audio_sources/file_playback.py`](/d:/Music%20Visualizer/app/audio_sources/file_playback.py) handles decoded file playback through `sounddevice`.
3. [`app/audio_sources/system_loopback.py`](/d:/Music%20Visualizer/app/audio_sources/system_loopback.py) handles Windows WASAPI loopback capture through `soundcard`.
4. [`app/dsp.py`](/d:/Music%20Visualizer/app/dsp.py) turns recent samples into waveform, spectrum, peak, RMS, and band-energy data.
5. [`app/ui.py`](/d:/Music%20Visualizer/app/ui.py) polls the latest `AnalysisFrame` and repaints the active visualizer.

Both source types feed the same `AnalysisFrame`, so the visualizers do not need a separate code path for file playback versus system audio.

## Installation

Requirements:

- Python 3.11+
- Windows 10 for `System Audio (Windows)` mode
- `ffmpeg` on `PATH` if you want AAC/Opus fallback support

Install in editable mode:

```powershell
py -3.11 -m pip install -e ".[dev]"
```

Install without editable mode:

```powershell
py -3.11 -m pip install ".[dev]"
```

On Windows, the `soundcard` dependency is installed automatically from `pyproject.toml`.

## Run

From the repo:

```powershell
py -3.11 main.py
```

Module entrypoint:

```powershell
py -3.11 -m app
```

Installed script:

```powershell
music-visualizer
```

## Testing

Run the suite:

```powershell
py -3.11 -m pytest
```

Current coverage includes:

- DSP helper behavior
- replaying after end-of-file
- source-mode switching lifecycle
- loopback chunk normalization and rechunking
- loopback cleanup behavior
- UI state toggles between file and system-audio modes
- AAC/Opus loading when `ffmpeg` is available

## How To Use System Audio Mode

1. Launch the app on Windows 10.
2. Change `Source` to `System Audio (Windows)`.
3. Choose the desired speaker/output device in `Output`.
4. Click `Start Capture`.
5. Play audio in another app such as a browser, media player, or Spotify.
6. Click `Stop` to release the loopback device.

If the selected output device changes or disappears, use `Refresh Devices` and choose the new one.

## How To Add A New Visualizer Mode

1. Create a new renderer under [`app/visualizers`](/d:/Music%20Visualizer/app/visualizers).
2. Subclass [`BaseVisualizer`](/d:/Music%20Visualizer/app/visualizers/base.py).
3. Add a unique `mode_id` and `display_name`.
4. Implement `render(self, painter, rect, frame)`.
5. Register the class in [`app/visualizers/__init__.py`](/d:/Music%20Visualizer/app/visualizers/__init__.py).

The shared `AnalysisFrame` already includes:

- `waveform`
- `spectrum`
- `bands`
- `peak`
- `rms`
- `sample_rate`
- `timestamp`

## Known Limitations

- System audio mode is implemented for Windows 10 only.
- There is no microphone capture path.
- Files are still decoded fully into memory when opened.
- There is no seek/scrub transport yet.
- AAC/Opus fallback depends on `ffmpeg` being installed and reachable from `PATH`.
- Loopback startup can still depend on the selected device and Windows audio-driver behavior.
- Rendering smoothness can vary by GPU driver, Qt backend, and display refresh rate.

## Troubleshooting

- If a file will not open, try a WAV file first to confirm the base decode path works.
- If AAC or Opus files fail, verify `ffmpeg -version` works in your terminal.
- If `System Audio (Windows)` is unavailable, confirm you installed the Windows dependency set and that the `soundcard` package imports correctly.
- If capture starts but you see silence, check that Windows is currently sending audio to the selected output device.
- If you change speakers or unplug an interface, use `Refresh Devices` before starting capture again.
