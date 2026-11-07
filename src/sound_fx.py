import io
import math
import struct
import wave
import threading
import random
import winsound


class SoundFX:
    """
    Subtle, warm, acoustic sound design for desktop interactions.
    Avoids harsh raw synthesizer tones in favor of bandpass-filtered,
    dampened micro-interactions (soft clicks, gentle airflow, muted resonance).
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._cache = {}
        self._pregenerate_sounds()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def _create_wav_bytes(self, samples: list[float], sample_rate: int = 44100) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            frames = bytearray()
            for s in samples:
                clamped = max(-1.0, min(1.0, s))
                val = int(clamped * 32767)
                frames.extend(struct.pack('<h', val))
            w.writeframes(frames)
        return buf.getvalue()

    def _pregenerate_sounds(self):
        sr = 44100

        # 1. Soft Sonar Ping: Warm, resonant marimba/bell ping (880Hz -> 440Hz harmonic decay)
        duration = 0.22
        n_samples = int(sr * duration)
        samples = []
        for i in range(n_samples):
            t = i / sr
            # Smooth attack (4ms) and exponential decay
            attack = min(1.0, t / 0.004)
            decay = math.exp(-t * 16.0)
            env = attack * decay
            f1 = 784.0  # G5
            f2 = 1568.0 # G6 harmonic
            val = (math.sin(2 * math.pi * f1 * t) * 0.75 + math.sin(2 * math.pi * f2 * t) * 0.25) * env * 0.28
            samples.append(val)
        self._cache['ping'] = self._create_wav_bytes(samples, sr)

        # 2. Tactile Intake Click/Pop: Acoustic cavity resonance (220Hz damped thump)
        duration = 0.08
        n_samples = int(sr * duration)
        samples = []
        for i in range(n_samples):
            t = i / sr
            attack = min(1.0, t / 0.002)
            decay = math.exp(-t * 45.0)
            env = attack * decay
            freq = 280.0 - 120.0 * (t / duration)
            val = math.sin(2 * math.pi * freq * t) * env * 0.35
            samples.append(val)
        self._cache['pop'] = self._create_wav_bytes(samples, sr)

        # 3. Motor Strain Rumble: Low frequency filtered mechanical vibration (60-80Hz)
        duration = 0.45
        n_samples = int(sr * duration)
        samples = []
        for i in range(n_samples):
            t = i / sr
            decay = math.exp(-t * 3.5)
            # Low hum with smooth modulation
            mod = 1.0 + 0.3 * math.sin(2 * math.pi * 24.0 * t)
            val = math.sin(2 * math.pi * 68.0 * t) * mod * decay * 0.25
            samples.append(val)
        self._cache['strain'] = self._create_wav_bytes(samples, sr)

        # 4. Haptic Lift Alert: Crisp double-click (mechanical micro-switch actuation)
        duration = 0.12
        n_samples = int(sr * duration)
        samples = []
        for i in range(n_samples):
            t = i / sr
            val = 0.0
            # Click 1 at t=0
            if t < 0.04:
                c_env = math.exp(-t * 120.0)
                val += math.sin(2 * math.pi * 1200.0 * t) * c_env * 0.3
            # Click 2 at t=0.05
            if t >= 0.05:
                t2 = t - 0.05
                c_env2 = math.exp(-t2 * 120.0)
                val += math.sin(2 * math.pi * 950.0 * t2) * c_env2 * 0.25
            samples.append(val)
        self._cache['squeak'] = self._create_wav_bytes(samples, sr)

        # 5. Clean Dock Chime: Subtle two-tone acoustic chime (E5 -> B5, soft and elegant)
        notes = [(659.25, 0.10, 0.0), (987.77, 0.22, 0.08)]
        duration = 0.35
        n_samples = int(sr * duration)
        samples = [0.0] * n_samples
        for freq, dur, start_time in notes:
            start_idx = int(start_time * sr)
            note_len = int(dur * sr)
            for i in range(note_len):
                idx = start_idx + i
                if idx < n_samples:
                    t = i / sr
                    attack = min(1.0, t / 0.005)
                    decay = math.exp(-t * 9.0)
                    env = attack * decay
                    val = math.sin(2 * math.pi * freq * t) * env * 0.22
                    samples[idx] += val
        self._cache['victory'] = self._create_wav_bytes(samples, sr)

    def play(self, name: str):
        if not self.enabled:
            return
        data = self._cache.get(name)
        if not data:
            return

        def _worker():
            try:
                winsound.PlaySound(data, winsound.SND_MEMORY)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()


sound_fx = SoundFX(enabled=True)
