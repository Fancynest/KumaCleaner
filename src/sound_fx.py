import io
import math
import struct
import wave
import threading
import winsound


class SoundFX:
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
            frames = []
            for s in samples:
                # Clamp sample between -1.0 and 1.0
                clamped = max(-1.0, min(1.0, s))
                val = int(clamped * 32767)
                frames.append(struct.pack('<h', val))
            w.writeframes(b''.join(frames))
        return buf.getvalue()

    def _pregenerate_sounds(self):
        sr = 44100

        # 1. LiDAR Ping: sweep from 600Hz up to 1400Hz with exponential decay
        duration = 0.15
        total_samples = int(sr * duration)
        samples = []
        for i in range(total_samples):
            t = i / sr
            freq = 600 + (1400 - 600) * (t / duration)
            decay = math.exp(-t * 18)
            val = math.sin(2 * math.pi * freq * t) * decay * 0.4
            samples.append(val)
        self._cache['ping'] = self._create_wav_bytes(samples, sr)

        # 2. Suction Pop / Slurp: pitch slide 300Hz -> 800Hz -> 200Hz
        duration = 0.18
        total_samples = int(sr * duration)
        samples = []
        for i in range(total_samples):
            t = i / sr
            freq = 300 + 600 * math.sin(math.pi * (t / duration))
            envelope = math.sin(math.pi * (t / duration)) ** 1.5
            # Add a bit of white noise for suction texture
            noise = (math.sin(t * 15000) * 0.2)
            val = (math.sin(2 * math.pi * freq * t) * 0.7 + noise) * envelope * 0.5
            samples.append(val)
        self._cache['pop'] = self._create_wav_bytes(samples, sr)

        # 3. Strain Groan (for heavy files): low rumbly frequency modulation 90Hz -> 65Hz
        duration = 0.6
        total_samples = int(sr * duration)
        samples = []
        for i in range(total_samples):
            t = i / sr
            freq = 90 - 25 * (t / duration) + 15 * math.sin(2 * math.pi * 35 * t)
            decay = math.exp(-t * 2.5)
            # Add gravelly harmonics
            val = (
                math.sin(2 * math.pi * freq * t) * 0.6 +
                math.sin(2 * math.pi * (freq * 2) * t) * 0.3 +
                math.sin(2 * math.pi * (freq * 0.5) * t) * 0.4
            ) * decay * 0.6
            samples.append(val)
        self._cache['strain'] = self._create_wav_bytes(samples, sr)

        # 4. Squeak (picked up complain): cute high frequency wobble
        duration = 0.22
        total_samples = int(sr * duration)
        samples = []
        for i in range(total_samples):
            t = i / sr
            freq = 950 + 200 * math.sin(2 * math.pi * 40 * t)
            decay = math.sin(math.pi * (t / duration))
            val = math.sin(2 * math.pi * freq * t) * decay * 0.5
            samples.append(val)
        self._cache['squeak'] = self._create_wav_bytes(samples, sr)

        # 5. Victory Ding: cute cheerful 3-note arpeggio (C5 -> E5 -> G5)
        notes = [(523.25, 0.08), (659.25, 0.08), (783.99, 0.25)]
        samples = []
        for freq, dur in notes:
            n_samples = int(sr * dur)
            for i in range(n_samples):
                t = i / sr
                decay = math.exp(-t * 6.0)
                val = math.sin(2 * math.pi * freq * t) * decay * 0.45
                samples.append(val)
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
