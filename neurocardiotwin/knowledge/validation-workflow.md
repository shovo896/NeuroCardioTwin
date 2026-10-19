# Validation workflow

Use the local ONNX result only after numeric input validation. The bundled demonstration contains 128 EEG samples and is intended for interface verification, not clinical validation. Record the source type, session identifier, source sampling rate, accepted finite samples, preprocessing version and model checkpoint version. When a result is unexpected, repeat acquisition, inspect artefacts and compare with an independently reviewed reference signal before any research conclusion.
