# Silero VAD

`silero_vad.onnx` is the unmodified model from Silero VAD **v6.2**:
https://github.com/snakers4/silero-vad/blob/v6.2/src/silero_vad/data/silero_vad.onnx

MIT license: see `SILERO_LICENSE`. The NumPy ONNX adapter in `../vad.py`
implements the recurrent state/context contract from the upstream wrapper:
https://github.com/snakers4/silero-vad/blob/v6.2/src/silero_vad/utils_vad.py

The model is bundled for offline startup; no Hugging Face account or runtime
model download is needed. Inference uses ONNX Runtime's CPU provider.
1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3  voice_input/assets/silero_vad.onnx
