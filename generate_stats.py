from pathlib import Path
from typing import Dict
import numpy as np
from utils import read_file, common_freq

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors


GRAPH_OF_SCORES = True
SHOW = 50

# Find the closest frequency responses to the following target
TARGET = "Shewi Target (DFHRTF).txt"
FREQUENCY_RESPONSES = "frequency_responses/*.txt"
NORMALIZATION_POINT = 223  # 223 is ~500hz, see generated target from average.py
NORMALIZATION_SPL = 60  # in dB but probably does not matter
EXCLUDE_PROJECTS = True  # Excluse prototypes not on the market

# Coeffs
PINNA_WEIGHT_START = 367  # 272: ~1kHz, 367: ~4kHz
PINNA_WEIGHT_END = 459  # 432: ~10kHz, 459: ~15kHz
PINNA_COEFF = 4

BASS_WEIGHT_START = 0
BASS_WEIGHT_END = 112  # 112: 100Hz
BASS_COEFF = 0.3

# Ignore FR above x Hz. 463: ~16kHz, should probably not be changed
DATA_LIMIT = 463

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
target_spl_sliced = target_spl[:DATA_LIMIT]

for iem, (freq, spl) in frequency_response_dict_unnormalized.items():
    # Interpolate and normalize spl data
    spl_interp = normalize(np.interp(np.log10(common_freq), np.log10(freq), spl))
    spl_dict[iem] = spl_interp

# Score the delta vs. the target
deltas: Dict[str, int] = {}
weights = np.ones_like(common_freq, dtype=float)
weights[PINNA_WEIGHT_START:PINNA_WEIGHT_END] = PINNA_COEFF
weights[BASS_WEIGHT_START:BASS_WEIGHT_END] = BASS_COEFF
weights_sliced = weights[:DATA_LIMIT]  # To match list size of target_spl_sliced for np

deltas: Dict[str, int] = {}
for iem, spl in spl_dict.items():
    if not EXCLUDE_PROJECTS or "project" not in iem.lower():
        deltas[iem] = int(
            np.sum(np.abs(target_spl_sliced - spl[:DATA_LIMIT]) * weights_sliced)
        )

deltas = dict(sorted(deltas.items(), key=lambda item: item[1]))
deltas_iem = list(deltas.keys())
deltas_score = list(deltas.values())

TOTAL_IEM_COUNT = len(deltas_iem)

# Adjust delta_score so the highest score = best adherence
for i in range(TOTAL_IEM_COUNT):
    deltas_score[i] = deltas_score[-1] - deltas_score[i]


# Results
if GRAPH_OF_SCORES:
    top_iem = deltas_iem[:SHOW]
    top_score = deltas_score[:SHOW]
    bottom_score = deltas_score[-SHOW:]
    bottom_iem = deltas_iem[-SHOW:]
    max_limit = max(deltas_score) + 500

    # Cool colors !
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "custom_gradient",
        [
            (0.0, "#570D0D"),
            (0.6, "#BB2E2E"),
            (0.8, "#F5B943"),
            (1.0, "#86E485"),
        ],
    )
    norm = mcolors.Normalize(vmin=min(deltas_score), vmax=max(deltas_score))
    bar_colors_top = [cmap(norm(score)) for score in top_score]
    bar_colors_bottom = [cmap(norm(score)) for score in bottom_score]
    all_colors = [cmap(norm(score)) for score in deltas_score]

    # FIRST PLOT: Top
    plt.figure(figsize=(16, 9))
    plot = plt.barh(top_iem, top_score, color=bar_colors_top)

    plt.xlabel("Score")
    plt.title(
        f"Most target adherent IEMs (Top {SHOW}, {PINNA_WEIGHT_START}~{PINNA_WEIGHT_END} coeff {PINNA_COEFF}, {BASS_WEIGHT_START}~{BASS_WEIGHT_END} coeff {BASS_COEFF})"
    )
    plt.bar_label(plot, padding=5)
    # Show the hole iem name
    plt.tight_layout()
    # Higher score at the top
    plt.gca().invert_yaxis()
    # "Normalize" scale
    plt.xlim(0, max_limit)
    plt.show()

    # SECOND PLOT: Histogram
    plt.figure(figsize=(16, 9))
    plt.bar(
        np.arange(1, TOTAL_IEM_COUNT + 1),
        deltas_score,
        color=all_colors,
        width=1.0,
    )

    step = 25
    x_ticks = sorted(list(range(1, TOTAL_IEM_COUNT + 1, step)) + [TOTAL_IEM_COUNT])
    plt.xticks(x_ticks)
    plt.xlabel("IEMs")
    plt.ylabel("Score")

    plt.title("Score histogram of the whole database")
    plt.grid(axis="y", linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.gca().invert_xaxis()
    plt.show()

    # THIRD PLOT: Worst
    plt.figure(figsize=(16, 9))
    plot = plt.barh(bottom_iem, bottom_score, color=bar_colors_bottom)

    plt.xlabel("Score")
    plt.title(
        f"Worst target adherent IEMs (Top {SHOW}, {PINNA_WEIGHT_START}~{PINNA_WEIGHT_END} coeff {PINNA_COEFF}, {BASS_WEIGHT_START}~{BASS_WEIGHT_END} coeff {BASS_COEFF})"
    )
    plt.bar_label(plot, padding=5)
    # Show the hole iem name
    plt.tight_layout()
    # Higher score at the top
    plt.gca().invert_yaxis()
    # "Normalize" scale
    plt.xlim(0, max_limit)
    plt.show()


else:
    print(f"Closest IEMs to {TARGET}: ")

    for i in range(SHOW):
        print(f"{i + 1}. {deltas_iem[i]} with {deltas_score[i]} points")
