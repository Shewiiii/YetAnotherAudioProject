from pathlib import Path
from typing import Dict
import numpy as np
from utils import read_file, common_freq


# Find the closest frequency responses to the following target
TARGET = "Shewi Target (DFHRTF).txt"
FREQUENCY_RESPONSES = "frequency_responses/*.txt"
COUNT = 10
NORMALIZATION_POINT = 223  # 223 is ~500hz, see generated target from average.py
NORMALIZATION_SPL = 60  # in dB but probably does not matter
EXCLUDE_PROJECTS = True  # Excluse prototypes not on the market

# Gives more weight to the upper midrange/treble
WEIGHT_START = 272  # 272: ~1kHz, 367: ~4kHz
WEIGHT_END = 460  # 432: ~10kHz, 460: ~17kHz
COEFF = 3

files = sorted(Path().glob(FREQUENCY_RESPONSES))
frequency_response_dict_unnormalized = {}
for file in files:
    frequency_response_dict_unnormalized[file.stem] = read_file(file)


def normalize(spl):
    return spl - (spl[NORMALIZATION_POINT] - NORMALIZATION_SPL)


spl_dict = {}
target_freq, target_spl_unnormalized = read_file(TARGET)
target_spl = normalize(
    np.interp(np.log10(common_freq), np.log10(target_freq), target_spl_unnormalized)
)

for iem, (freq, spl) in frequency_response_dict_unnormalized.items():
    # Interpolate and normalize spl data
    spl_interp = normalize(np.interp(np.log10(common_freq), np.log10(freq), spl))
    spl_dict[iem] = spl_interp

# Score the delta vs. the target
deltas: Dict[str, int] = {}
weights = np.ones_like(common_freq, dtype=float)
weights[WEIGHT_START:WEIGHT_END] = COEFF

deltas: Dict[str, int] = {}
for iem, spl in spl_dict.items():
    if not EXCLUDE_PROJECTS or "project" not in iem.lower():
        deltas[iem] = int(np.sum(np.abs(target_spl - spl) * weights))

deltas = dict(sorted(deltas.items(), key=lambda item: item[1]))


deltas_iem = list(deltas.keys())
deltas_score = list(deltas.values())
print(f"Closest IEMs to {TARGET}: ")
for i in range(COUNT):
    print(f"{i + 1}. {deltas_iem[i]} with {deltas_score[-1] - deltas_score[i]} points")
