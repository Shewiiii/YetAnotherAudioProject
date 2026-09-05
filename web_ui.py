# Written using Gemini and old projects
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np
from flask import Flask, jsonify, render_template, send_file

from params import *

# Path resolution to handle running from project root or inside web/
BASE_DIR = Path(__file__).resolve().parent
if (
    not (BASE_DIR / "Shewi Target (DFHRTF).txt").exists()
    and (BASE_DIR.parent / "Shewi Target (DFHRTF).txt").exists()
):
    BASE_DIR = BASE_DIR.parent

sys.path.append(str(BASE_DIR))
from utils import common_freq, read_file

app = Flask(__name__)


def normalize(spl: np.ndarray) -> np.ndarray:
    return spl - (spl[NORMALIZATION_POINT] - NORMALIZATION_SPL)


def best_normalized_curve(
    spl: np.ndarray,
    target_spl: np.ndarray,
) -> tuple[np.ndarray, int]:
    candidate_count = min(DATA_LIMIT, spl.size, target_spl.size)
    if candidate_count == 0:
        raise ValueError("Cannot normalize an empty frequency response")

    comparison_limit = min(DATA_LIMIT, candidate_count)
    candidate_curves = spl[:comparison_limit, None] - spl[:candidate_count]
    candidate_curves = spl[None, :comparison_limit] - (
        spl[:candidate_count, None] - NORMALIZATION_SPL
    )
    errors = np.sum(
        np.abs(target_spl[:comparison_limit] - candidate_curves),
        axis=1,
    )
    best_point = int(np.argmin(errors))
    return spl - (spl[best_point] - NORMALIZATION_SPL), best_point


def find_target_file(name_pattern: str) -> Path:
    search_dirs = [
        BASE_DIR,
        Path.cwd(),
        Path(__file__).resolve().parent,
        BASE_DIR.parent,
    ]
    for d in search_dirs:
        p = d / name_pattern
        if p.exists() and p.is_file():
            return p
        matches = list(d.glob(name_pattern))
        if matches and matches[0].is_file():
            return matches[0]
        # Partial match fallbacks
        if "JM" in name_pattern or "jm" in name_pattern:
            matches = list(d.glob("*[Jj][Mm]*1*.txt"))
            if matches and matches[0].is_file():
                return matches[0]
        if "top" in name_pattern.lower() and "pref" in name_pattern.lower():
            matches = list(d.glob("*pref*top*.txt"))
            if matches and matches[0].is_file():
                return matches[0]
        if "bottom" in name_pattern.lower() and "pref" in name_pattern.lower():
            matches = list(d.glob("*pref*bottom*.txt"))
            if matches and matches[0].is_file():
                return matches[0]
    raise FileNotFoundError(f"Could not locate required target file: {name_pattern}")


def init_data() -> dict:
    # 1. Load target and FR files
    files = sorted((BASE_DIR / "frequency_responses").glob("*.txt"))
    if not files:
        files = sorted(Path().glob(FREQUENCY_RESPONSES))

    file_paths = {file.stem: file for file in files}
    frequency_response_dict = {file.stem: read_file(file) for file in files}
    neutral_files = {
        file.stem: file
        for file in (BASE_DIR / "neutral_fr").glob("*.txt")
        if file.stem in file_paths
    }
    neutral_response_dict = {
        stem: read_file(file) for stem, file in neutral_files.items()
    }

    target_file = find_target_file(TARGET)
    target_freq, target_spl_unnormalized = read_file(target_file)
    target_spl = normalize(
        np.interp(np.log10(common_freq), np.log10(target_freq), target_spl_unnormalized)
    )
    target_spl_sliced = target_spl[:DATA_LIMIT]

    # 2. Load JM-1 Target
    jm1_file = find_target_file(JM1_TARGET)
    jm1_freq, jm1_spl_unnormalized = read_file(jm1_file)
    jm1_spl = normalize(
        np.interp(np.log10(common_freq), np.log10(jm1_freq), jm1_spl_unnormalized)
    )

    # 3. Calculate compensation baseline
    octaves = np.log2(common_freq / common_freq[NORMALIZATION_POINT])
    tilt = -1.0 * octaves
    jm1_df_baseline = jm1_spl - tilt

    shewi_comp = (target_spl - jm1_df_baseline)[:DATA_LIMIT]
    jm1_comp = tilt[:DATA_LIMIT]
    sliced_freqs = [round(float(f), 1) for f in common_freq[:DATA_LIMIT]]

    # 4. Load & normalize Preference Bounds (no compensation baseline, normalized at 500 Hz)
    target_log_freqs = np.log10(common_freq[:DATA_LIMIT])

    top_file = find_target_file(PREF_BOUNDS_TOP)
    top_freq, top_spl = read_file(top_file)
    top_order = np.argsort(top_freq)
    top_freq, top_spl = top_freq[top_order], top_spl[top_order]
    top_spl_interp = np.interp(target_log_freqs, np.log10(top_freq), top_spl)
    top_val_500 = np.interp(np.log10(500.0), np.log10(top_freq), top_spl)
    pref_top_comp = top_spl_interp - top_val_500 + 1.1

    bottom_file = find_target_file(PREF_BOUNDS_BOTTOM)
    bottom_freq, bottom_spl = read_file(bottom_file)
    bottom_order = np.argsort(bottom_freq)
    bottom_freq, bottom_spl = bottom_freq[bottom_order], bottom_spl[bottom_order]
    bottom_spl_interp = np.interp(target_log_freqs, np.log10(bottom_freq), bottom_spl)
    bottom_val_500 = np.interp(np.log10(500.0), np.log10(bottom_freq), bottom_spl)
    pref_bottom_comp = bottom_spl_interp - bottom_val_500 - 1.25

    # 5. Potential calculation
    weights = np.ones_like(common_freq, dtype=float)
    weights[SUB_WEIGHT_START:SUB_WEIGHT_END] = SUB_COEFF
    weights[BASS_WEIGHT_START:BASS_WEIGHT_END] = BASS_COEFF
    weights[MIDRANGE_WEIGHT_START:MIDRANGE_WEIGHT_END] = MIDRANGE_COEFF
    weights[CANAL_WEIGHT_START:CANAL_WEIGHT_END] = CANAL_COEFF
    weights[PINNA_WEIGHT_START:PINNA_WEIGHT_END] = PINNA_COEFF
    weights_sliced = weights[:DATA_LIMIT]

    deltas = {}
    iem_curves_by_id = {}
    neutral_curves_by_id = {}
    iem_normalization_points = {}

    for iem, (freq, spl) in frequency_response_dict.items():
        if not EXCLUDE_PROJECTS or "project" not in iem.lower():
            interpolated_spl = np.interp(np.log10(common_freq), np.log10(freq), spl)
            spl_interp, normalization_point = best_normalized_curve(
                interpolated_spl,
                target_spl,
            )
            deltas[iem] = float(
                np.sum(
                    np.abs(target_spl_sliced - spl_interp[:DATA_LIMIT]) * weights_sliced
                )
            )
            iem_normalization_points[iem] = normalization_point

            comp_spl = (spl_interp - jm1_df_baseline)[:DATA_LIMIT]
            iem_curves_by_id[iem] = [round(float(v), 2) for v in comp_spl]

            neutral_curve = neutral_response_dict.get(iem)
            if neutral_curve is not None:
                neutral_freq, neutral_spl = neutral_curve
                neutral_interp = np.interp(
                    np.log10(common_freq),
                    np.log10(neutral_freq),
                    neutral_spl,
                )
                neutral_interp, _ = best_normalized_curve(
                    neutral_interp,
                    target_spl,
                )
                neutral_comp = (neutral_interp - jm1_df_baseline)[:DATA_LIMIT]
                neutral_curves_by_id[iem] = [
                    round(float(v), 2) for v in neutral_comp
                ]

    sorted_deltas = dict(sorted(deltas.items(), key=lambda item: item[1]))

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

    items = []
    potentials = []
    curves_indexed = {}
    files_indexed = {}

    for idx, (iem, weighted_delta) in enumerate(sorted_deltas.items()):
        potential = round(10 * np.exp(-weighted_delta / DECAY_FACTOR), 2)
        potentials.append(potential)
        color_hex = mcolors.to_hex(cmap(norm(potential)))

        items.append(
            {
                "id": idx,
                "rank": idx + 1,
                "name": iem,
                "potential": potential,
                "weighted_delta": round(weighted_delta),
                "color": color_hex,
                "bar_width": min(max(potential * 10, 0), 100),
                "mainstream": any(
                    brand.lower() in iem.lower() for brand in KNOWN_BRANDS
                ),
            }
        )
        curves_indexed[idx] = {
            "name": iem,
            "data": iem_curves_by_id[iem],
            "neutral_data": neutral_curves_by_id.get(iem),
        }
        files_indexed[idx] = str(file_paths[iem])

    return {
        "items": items,
        "total_count": len(items),
        "median_potential": round(float(np.median(potentials)), 2)
        if potentials
        else 0.0,
        "top_potential": potentials[0] if potentials else 0.0,
        "lowest_potential": potentials[-1] if potentials else 0.0,
        "freqs": sliced_freqs,
        "shewi_comp": [round(float(v), 2) for v in shewi_comp],
        "jm1_comp": [round(float(v), 2) for v in jm1_comp],
        "pref_top": [round(float(v), 2) for v in pref_top_comp],
        "pref_bottom": [round(float(v), 2) for v in pref_bottom_comp],
        "iem_curves": curves_indexed,
        "iem_normalization_points": {
            idx: iem_normalization_points[iem]
            for idx, (iem, _) in enumerate(sorted_deltas.items())
        },
        "iem_files": files_indexed,
    }


DATA_STORE = init_data()




@app.route("/")
def index():
    return render_template(
        "index.html",
        data=DATA_STORE,
        target_name=TARGET,
        decay_factor=DECAY_FACTOR,
        weights={
            "sub": {
                "coeff": SUB_COEFF,
                "range": f"{POINT_TO_FREQ.get(SUB_WEIGHT_START, '20Hz')} - {POINT_TO_FREQ.get(SUB_WEIGHT_END, '')}",
                "value_count": SUB_WEIGHT_END - SUB_WEIGHT_START,
            },
            "bass": {
                "coeff": BASS_COEFF,
                "range": f"{POINT_TO_FREQ.get(BASS_WEIGHT_START, '')} - {POINT_TO_FREQ.get(BASS_WEIGHT_END, '')}",
                "value_count": BASS_WEIGHT_END - BASS_WEIGHT_START,
            },
            "mids": {
                "coeff": MIDRANGE_COEFF,
                "range": f"{POINT_TO_FREQ.get(MIDRANGE_WEIGHT_START, '')} - {POINT_TO_FREQ.get(MIDRANGE_WEIGHT_END, '')}",
                "value_count": MIDRANGE_WEIGHT_END - MIDRANGE_WEIGHT_START,
            },
            "canal": {
                "coeff": CANAL_COEFF,
                "range": f"{POINT_TO_FREQ.get(CANAL_WEIGHT_START, '')} - {POINT_TO_FREQ.get(CANAL_WEIGHT_END, '')}",
                "value_count": CANAL_WEIGHT_END - CANAL_WEIGHT_START,
            },
            "pinna": {
                "coeff": PINNA_COEFF,
                "range": f"{POINT_TO_FREQ.get(PINNA_WEIGHT_START, '')} - {POINT_TO_FREQ.get(PINNA_WEIGHT_END, '')}",
                "value_count": PINNA_WEIGHT_END - PINNA_WEIGHT_START,
            },
        },
    )


@app.route("/api/graph/<int:iem_id>")
def get_graph_data(iem_id: int):
    curve = DATA_STORE["iem_curves"].get(iem_id)
    if not curve:
        return jsonify({"error": "IEM not found"}), 404
    return jsonify(curve)


@app.route("/api/download/<int:iem_id>")
def download_iem(iem_id: int):
    file_path_str = DATA_STORE.get("iem_files", {}).get(iem_id)
    if not file_path_str:
        return jsonify({"error": "File not found"}), 404

    file_path = Path(file_path_str)
    if not file_path.is_file():
        return jsonify({"error": "File does not exist"}), 404

    return send_file(file_path, as_attachment=True, download_name=file_path.name)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
