from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

from utils import KNOWN_BRANDS, common_freq, read_file

# Settings
SHOW = 50
EXCLUDE_PROJECTS = True  # Excluse prototypes not on the market
ONLY_KNOWN_BRANDS = True
TARGET = "Shewi Target (DFHRTF).txt"
FREQUENCY_RESPONSES = "frequency_responses/*.txt"


# Coeffs and normalization parameters
BASS_WEIGHT_START = 0
BASS_WEIGHT_END = 112  # 112: 100Hz
BASS_COEFF = 0.3

MIDRANGE_WEIGHT_START = 177 # 177: 250Hz
MIDRANGE_WEIGHT_END = 321 # 321: ~2kHz
MIDRANGE_COEFF = 1  # Many values

CANAL_WEIGHT_START = 321 
CANAL_WEIGHT_END = 367  # 367: ~4kHz
CANAL_COEFF = 2 # Not many values

PINNA_WEIGHT_START = 367  # 272: ~1kHz, 367: ~4kHz
PINNA_WEIGHT_END = 459  # 432: ~10kHz, 459: ~15kHz
PINNA_COEFF = 4


NORMALIZATION_POINT = 223  # 223 is ~500hz, see generated target from average.py
NORMALIZATION_SPL = 60  # in dB but probably does not matter

# Ignore FR above x Hz. 463: ~16kHz, ~~should probably not be changed~~
# I decided to remove the limit to punish very bright IEMs (eg. Daybreak): 
# yes it is not accurate that high in frequency but still relevant on a large scale
# There is not many values anyways
DATA_LIMIT = 481

# Scale factor for exponential decay; lower = agressive drop, higher = flatter
# Should be adjusted so the median is near 5
DECAY_FACTOR = 3600

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
deltas: dict[str, int] = {}
weights = np.ones_like(common_freq, dtype=float)
weights[BASS_WEIGHT_START:BASS_WEIGHT_END] = BASS_COEFF
weights[MIDRANGE_WEIGHT_START:MIDRANGE_WEIGHT_END] = MIDRANGE_COEFF
weights[CANAL_WEIGHT_START:CANAL_WEIGHT_END] = CANAL_COEFF
weights[PINNA_WEIGHT_START:PINNA_WEIGHT_END] = PINNA_COEFF
weights_sliced = weights[:DATA_LIMIT]  # To match list size of target_spl_sliced for np

deltas: dict[str, int] = {}
for iem, spl in spl_dict.items():
    if (not EXCLUDE_PROJECTS or "project" not in iem.lower()) and (
        not ONLY_KNOWN_BRANDS or any(brand in iem.lower() for brand in KNOWN_BRANDS)
    ):
        deltas[iem] = int(
            np.sum(np.abs(target_spl_sliced - spl[:DATA_LIMIT]) * weights_sliced)
        )

deltas = dict(sorted(deltas.items(), key=lambda item: item[1]))
deltas_iem = list(deltas.keys())
deltas_score = list(deltas.values())

TOTAL_IEM_COUNT = len(deltas_iem)

# Adjust delta_score so the highest score = best adherence
for i in range(TOTAL_IEM_COUNT):
    deltas_score[i] = round(10 * np.exp(-deltas_score[i] / DECAY_FACTOR), 2)

print(f"Median score: {np.median(deltas_score)}")

# Results
def graphs() -> None:
    top_iem = deltas_iem[:SHOW]
    top_score = deltas_score[:SHOW]
    bottom_score = deltas_score[-SHOW:]
    bottom_iem = deltas_iem[-SHOW:]
    bound_score = (
        max(deltas_score) + 0.5
    )  # Padding so the score bars don't go out the graph

    # Colors
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "custom_gradient",
        [
            (0.0, "#570D0D"),
            (0.6, "#BB2E2E"),
            (0.8, "#F5B943"),
            (1.0, "#86E485"),
        ],
    )
    norm = mcolors.Normalize(vmin=0, vmax=8.25)
    bar_colors_top = [cmap(norm(score)) for score in top_score]
    bar_colors_bottom = [cmap(norm(score)) for score in bottom_score]
    all_colors = [cmap(norm(score)) for score in deltas_score]

    # FIRST PLOT: Top
    plt.figure(figsize=(16, 9))
    plot = plt.barh(top_iem, top_score, color=bar_colors_top)

    plt.xlabel("Score")
    plt.xticks(range(0, int(bound_score) + 1, 1))
    plt.grid(axis="x", linestyle="--", alpha=0.5)
    plt.title(
        f"Most target adherent IEMs (Top {SHOW}, weighted)"
    )
    plt.bar_label(plot, padding=5)
    # Show the hole iem name
    plt.tight_layout()
    # Higher score at the top
    plt.gca().invert_yaxis()
    # "Normalize" scale
    plt.xlim(0, bound_score)
    plt.show()

    # SECOND PLOT: Worst
    plt.figure(figsize=(16, 9))
    plot = plt.barh(bottom_iem, bottom_score, color=bar_colors_bottom)

    plt.xlabel("Score")
    plt.xticks(range(0, int(bound_score) + 1, 1))
    plt.grid(axis="x", linestyle="--", alpha=0.5)
    plt.title(
        f"Worst target adherent IEMs (Top {SHOW}, weighted)"
    )
    plt.bar_label(plot, padding=5)
    # Show the hole iem name
    plt.tight_layout()
    # Higher score at the top
    plt.gca().invert_yaxis()
    # "Normalize" scale
    plt.xlim(0, bound_score)
    plt.show()

    # THIRD PLOT: Histogram
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
    plt.yticks(range(0, int(max(deltas_score)) + 1, 1))
    plt.xlabel("IEMs")
    plt.ylabel("Score")

    plt.title("Score histogram")
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.gca().invert_xaxis()
    plt.show()

    # FOURTH PLOT: Distribution
    plt.figure(figsize=(16, 9))
    vertical_bars = [
        "0~0.9",
        "1~1.9",
        "2~2.9",
        "3~3.9",
        "4~4.9",
        "5~5.9",
        "6~6.9",
        "7~7.9",
        "8~8.9",
        "9~10",
    ]
    distribution = [0] * len(vertical_bars)
    for score in deltas_score:
        pos = max(0, min(int(score), len(vertical_bars) - 1))
        distribution[pos] += 1
    plot = plt.bar(vertical_bars, distribution)
    plt.title("Score distribution")
    plt.ylabel("Count")
    plt.yticks(range(0, max(distribution) + 1, 10))
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    graphs()
