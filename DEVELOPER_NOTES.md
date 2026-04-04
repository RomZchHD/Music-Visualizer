# Developer Notes

## Architecture Decisions

### 1. Qt-native UI plus custom painting

I chose `PySide6` with custom `QPainter`-based renderers instead of layering `pyqtgraph` on top. That keeps the visualizer plug-in surface small and makes it straightforward to build non-cartesian modes like the radial spectrum without introducing another scene abstraction.

### 2. Analysis is separate from drawing

The DSP layer lives in [`app/dsp.py`](/d:/Music%20Visualizer/app/dsp.py), the transport logic lives in [`app/audio_engine.py`](/d:/Music%20Visualizer/app/audio_engine.py), and the renderers live in [`app/visualizers`](/d:/Music%20Visualizer/app/visualizers). The UI only consumes the latest immutable-ish analysis snapshot.

### 3. Callback-driven sync

Playback uses a `sounddevice.OutputStream` callback. The callback advances the playhead, writes the current block, and updates a recent analysis window. The UI then polls the latest frame at the configured UI refresh rate. This keeps audio as the timing source, which helps the visuals stay aligned with playback.

### 4. Reliability over streaming complexity

For the MVP, audio files are decoded fully into memory when opened. This avoids a lot of edge cases around disk I/O, codec state, pause/resume, and stream starvation. It is a conscious tradeoff in favor of a solid first version. A future improvement could switch to chunked decoding with a ring buffer for very large files.

### 5. Extensibility path

Adding a new mode should only require:

- a new renderer class
- optional new DSP helpers if the mode needs extra derived data
- registration in the visualizer registry

If microphone input is added later, the current design can be extended with a second input source that feeds the same `AudioAnalyzer` contract.

## Suggested Next Refactors

- Add a transport model with seeking and elapsed/remaining time formatting.
- Add a streaming decoder path for very large media files.
- Add microphone capture as a second source mode.
- Add beat/onset detection and expose it on `AnalysisFrame`.
- Add theme presets and persisted user settings.
