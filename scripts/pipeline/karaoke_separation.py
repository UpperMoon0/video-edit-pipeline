"""Optional UVR MDX instrumental inference from a local ONNX model/config."""
import hashlib
import tempfile
from pathlib import Path
from .common import PipelineError, file_hash, output_transaction, read_json
from .media import ffmpeg_args, run


def separate(source, output, model, model_data, *, provider='cpu'):
    # No model/package download, provider switch or global installation at runtime.
    try:
        import numpy as np
        import onnxruntime as ort
        from scipy import signal
        from scipy.io import wavfile
    except ImportError as exc:
        raise PipelineError('karaoke_dependency', 'separate', 'Install numpy, scipy and an ONNX Runtime provider in a dedicated environment.') from exc
    source, output, model, model_data = map(lambda p: Path(p).resolve(), (source, output, model, model_data))
    if output.suffix.lower() != '.wav':
        raise PipelineError('karaoke_audio_format', 'output', 'The separated master must use a .wav extension.')
    providers = {'cpu': 'CPUExecutionProvider', 'directml': 'DmlExecutionProvider', 'cuda': 'CUDAExecutionProvider'}
    if provider not in providers or providers[provider] not in ort.get_available_providers():
        raise PipelineError('karaoke_provider', 'provider', f'Requested provider is unavailable: {provider}.', str(ort.get_available_providers()))
    hashes = {p: file_hash(p) for p in (source, model, model_data)}
    # UVR's model registry identifies configuration with MD5 of the final 10,240,000 bytes.
    with model.open('rb') as stream:
        stream.seek(max(0, model.stat().st_size - 10000 * 1024))
        key = hashlib.md5(stream.read()).hexdigest()
    cfg = read_json(model_data).get(key)
    if not isinstance(cfg, dict) or cfg.get('primary_stem') != 'Instrumental':
        raise PipelineError('karaoke_model_config', 'model_data', 'Model hash must identify an instrumental-primary UVR MDX configuration.')
    nfft, dimf, frames = cfg.get('mdx_n_fft_scale_set'), cfg.get('mdx_dim_f_set'), cfg.get('mdx_dim_t_set')
    compensate = cfg.get('compensate')
    if (any(type(v) is not int for v in (nfft, dimf, frames)) or not 1024 <= nfft <= 16384 or nfft % 2
            or not 4 <= frames <= 10 or not 3 < dimf <= nfft // 2 + 1
            or type(compensate) not in (int, float) or not np.isfinite(compensate) or not 0 < compensate < 3):
        raise PipelineError('karaoke_model_config', 'model_data', 'Unsupported or unbounded MDX FFT configuration.')
    hop, trim, count = 1024, nfft // 2, 2 ** frames
    size = hop * (count - 1)
    if size <= 2 * trim:
        raise PipelineError('karaoke_model_config', 'model_data', 'FFT configuration leaves no usable chunk interior.')
    window = signal.windows.hann(nfft, sym=False).astype(np.float32)
    scale = window.sum()

    def stft(x):
        z = signal.stft(x, window=window, nperseg=nfft, noverlap=nfft - hop,
                        boundary='even', padded=False, axis=-1)[2] * scale
        return np.stack([z.real, z.imag], axis=1).reshape(1, 4, nfft // 2 + 1, -1)[:, :, :dimf].copy()

    def inverse(x):
        x = np.pad(x, ((0, 0), (0, 0), (0, nfft // 2 + 1 - dimf), (0, 0)))
        x = x.reshape(2, 2, nfft // 2 + 1, -1)
        z = (x[:, 0] + 1j * x[:, 1]) / scale
        return signal.istft(z, window=window, nperseg=nfft, noverlap=nfft - hop, boundary=True)[1].astype(np.float32)

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.enable_mem_pattern = False
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(str(model), sess_options=options, providers=[providers[provider]])
    if providers[provider] not in session.get_providers():
        raise PipelineError('karaoke_provider', 'provider', 'The requested provider failed to initialize; refusing an unnoticed CPU fallback.')
    inputs = session.get_inputs()
    if len(inputs) != 1 or inputs[0].shape[1:] != [4, dimf, count]:
        raise PipelineError('karaoke_model_shape', 'model', 'Model input dimensions do not match its registered FFT configuration.')
    with output_transaction(output, [source, model, model_data]) as temp:
        with tempfile.TemporaryDirectory(prefix='karaoke-separate-') as directory:
            decoded = Path(directory) / 'source.wav'
            run(ffmpeg_args() + ['-i', str(source), '-map', '0:a:0', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_f32le', str(decoded)])
            sr, audio = wavfile.read(decoded)
            mix = audio.T
            gen = size - 2 * trim
            padded = np.pad(mix, ((0, 0), (trim, gen + trim - mix.shape[-1] % gen)))
            result, weights = np.zeros_like(padded), np.zeros(padded.shape[-1], np.float32)
            positions = list(range(0, padded.shape[-1], size // 2))
            for start in positions:
                end = min(start + size, padded.shape[-1])
                actual = end - start
                chunk = np.pad(padded[:, start:end], ((0, 0), (0, size - actual)))
                spectrum = stft(chunk)
                spectrum[:, :, :3] = 0
                positive = session.run(None, {inputs[0].name: spectrum})[0]
                negative = session.run(None, {inputs[0].name: -spectrum})[0]
                separated = inverse((positive - negative) * .5)[:, :actual]
                blend = np.hanning(actual).astype(np.float32)
                result[:, start:end] += separated * blend
                weights[start:end] += blend
            result /= np.maximum(weights, 1e-8)
            result = result[:, trim:trim + mix.shape[-1]] * compensate
            peak = float(np.max(np.abs(result)))
            if result.shape != mix.shape or not np.isfinite(result).all() or peak < 1e-7:
                raise PipelineError('karaoke_separation_output', 'audio', 'Separation returned empty, nonfinite or truncated audio.')
            if peak > .97:
                result *= .97 / peak
            wavfile.write(temp, sr, result.T)
            run(ffmpeg_args() + ['-xerror', '-i', str(temp), '-vn', '-f', 'null', '-'])
            if any(file_hash(p) != h for p, h in hashes.items()):
                raise PipelineError('karaoke_separation_changed', 'source', 'An input changed during separation.')
    return {'output': str(output), 'duration': result.shape[-1] / sr, 'samples': int(result.shape[-1]),
            'sample_rate': sr, 'model_sha256': hashes[model], 'config_hash': key,
            'providers': session.get_providers(), 'output_sha256': file_hash(output),
            'review_required': 'Listen for residual vocals and artifacts; removing vocals does not remove music rights.'}
