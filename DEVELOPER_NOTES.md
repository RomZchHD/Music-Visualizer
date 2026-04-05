# Developer Notes

## Architecture Decisions

### 1. Qt-native UI plus custom painting

I chose `PySide6` with custom `QPainter`-based renderers instead of layering `pyqtgraph` on top. That keeps the visualizer plug-in surface small and makes it straightforward to build non-cartesian modes like the radial spectrum without introducing another scene abstraction.

### 2. Source abstraction before feature branching

The app now uses a real source layer:

- [`app/audio_sources/file_playback.py`](/d:/Music%20Visualizer/app/audio_sources/file_playback.py)
- [`app/audio_sources/system_loopback.py`](/d:/Music%20Visualizer/app/audio_sources/system_loopback.py)
- [`app/audio_engine.py`](/d:/Music%20Visualizer/app/audio_engine.py) as the source controller

That keeps file playback and Windows loopback capture separate while preserving one `AnalysisFrame` contract for the UI and visualizers.

### 3. Analysis is separate from drawing

The DSP layer lives in [`app/dsp.py`](/d:/Music%20Visualizer/app/dsp.py), source lifecycle lives under [`app/audio_sources`](/d:/Music%20Visualizer/app/audio_sources), and the renderers live in [`app/visualizers`](/d:/Music%20Visualizer/app/visualizers). The UI only consumes the latest snapshot plus the latest analysis frame.

### 4. Two timing models, one visual contract

File playback uses a `sounddevice.OutputStream` callback so playback timing still drives file-mode visuals. Windows system audio capture uses a background loopback worker thread with fixed-size analysis blocks. Both paths reuse the same analyzer and feed the same renderer contract.

### 5. Reliability over streaming complexity

For the MVP, audio files are decoded fully into memory when opened. This avoids a lot of edge cases around disk I/O, codec state, pause/resume, and stream starvation. The same philosophy was applied to system audio: stability and clean lifecycle management were chosen over extremely aggressive low-latency tuning.

### 6. Extensibility path

Adding a new mode should only require:

- a new renderer class
- optional new DSP helpers if the mode needs extra derived data
- registration in the visualizer registry

If microphone input is added later, the current design can be extended with a second input source that feeds the same `AudioAnalyzer` contract.

## Suggested Next Refactors

- Add a transport model with seeking and elapsed/remaining time formatting.
- Add a streaming decoder path for very large media files.
- Add another source implementation if microphone capture or recording is needed later.
- Add beat/onset detection and expose it on `AnalysisFrame`.
- Add theme presets and persisted user settings.
