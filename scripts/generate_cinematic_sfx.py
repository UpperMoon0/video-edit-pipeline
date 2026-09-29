#!/usr/bin/env python3
"""Generate a small reusable cinematic SFX kit without external assets."""

from __future__ import annotations

import argparse
import math
import random
import wave
from pathlib import Path

RATE = 48_000


def clamp(value: float) -> int:
    return max(-32767, min(32767, round(value * 32767)))


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(b"".join(clamp(sample).to_bytes(2, "little", signed=True) for sample in samples))


def whoosh(seconds: float = 0.52) -> list[float]:
    rng = random.Random(4103)
    count = round(seconds * RATE)
    smooth = 0.0
    result = []
    for i in range(count):
        t = i / count
        smooth = 0.86 * smooth + 0.14 * rng.uniform(-1, 1)
        envelope = math.sin(math.pi * t) ** 1.7
        air = math.sin(2 * math.pi * (480 + 820 * t) * i / RATE)
        result.append((0.58 * smooth + 0.12 * air) * envelope)
    return result


def riser(seconds: float = 1.15) -> list[float]:
    rng = random.Random(7201)
    count = round(seconds * RATE)
    smooth = 0.0
    phase = 0.0
    result = []
    for i in range(count):
        t = i / count
        frequency = 105 + 920 * (t**2.1)
        phase += 2 * math.pi * frequency / RATE
        smooth = 0.93 * smooth + 0.07 * rng.uniform(-1, 1)
        envelope = t**1.8
        result.append((0.32 * math.sin(phase) + 0.38 * smooth) * envelope)
    return result


def impact(seconds: float = 0.72) -> list[float]:
    rng = random.Random(991)
    count = round(seconds * RATE)
    phase = 0.0
    result = []
    for i in range(count):
        t = i / RATE
        normalized = i / count
        frequency = 58 - 22 * normalized
        phase += 2 * math.pi * frequency / RATE
        body = math.sin(phase) * math.exp(-5.2 * t)
        transient = rng.uniform(-1, 1) * math.exp(-42 * t)
        result.append(0.72 * body + 0.32 * transient)
    return result


def click(seconds: float = 0.18) -> list[float]:
    rng = random.Random(1207)
    count = round(seconds * RATE)
    result = []
    for i in range(count):
        t = i / RATE
        tone = math.sin(2 * math.pi * 1450 * t) + 0.45 * math.sin(2 * math.pi * 2380 * t)
        result.append((0.35 * tone + 0.18 * rng.uniform(-1, 1)) * math.exp(-31 * t))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assets = {
        "cinematic-whoosh.wav": whoosh(),
        "cinematic-riser.wav": riser(),
        "cinematic-impact.wav": impact(),
        "cinematic-click.wav": click(),
    }
    for name, samples in assets.items():
        destination = args.output.resolve() / name
        write_wav(destination, samples)
        print(destination)


if __name__ == "__main__":
    main()
