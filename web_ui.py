# Written using Gemini and old projects
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np
from flask import Flask, jsonify, render_template_string

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

    frequency_response_dict = {file.stem: read_file(file) for file in files}

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

    # 5. Score calculation
    weights = np.ones_like(common_freq, dtype=float)
    weights[SUB_WEIGHT_START:SUB_WEIGHT_END] = SUB_COEFF
    weights[BASS_WEIGHT_START:BASS_WEIGHT_END] = BASS_COEFF
    weights[MIDRANGE_WEIGHT_START:MIDRANGE_WEIGHT_END] = MIDRANGE_COEFF
    weights[CANAL_WEIGHT_START:CANAL_WEIGHT_END] = CANAL_COEFF
    weights[PINNA_WEIGHT_START:PINNA_WEIGHT_END] = PINNA_COEFF
    weights_sliced = weights[:DATA_LIMIT]

    deltas = {}
    iem_curves_by_id = {}

    for iem, (freq, spl) in frequency_response_dict.items():
        if not EXCLUDE_PROJECTS or "project" not in iem.lower():
            spl_interp = normalize(
                np.interp(np.log10(common_freq), np.log10(freq), spl)
            )
            deltas[iem] = int(
                np.sum(
                    np.abs(target_spl_sliced - spl_interp[:DATA_LIMIT]) * weights_sliced
                )
            )

            comp_spl = (spl_interp - jm1_df_baseline)[:DATA_LIMIT]
            iem_curves_by_id[iem] = [round(float(v), 2) for v in comp_spl]

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
    scores = []
    curves_indexed = {}

    for idx, (iem, weighted_delta) in enumerate(sorted_deltas.items()):
        score = round(10 * np.exp(-weighted_delta / DECAY_FACTOR), 2)
        scores.append(score)
        color_hex = mcolors.to_hex(cmap(norm(score)))

        items.append(
            {
                "id": idx,
                "rank": idx + 1,
                "name": iem,
                "score": score,
                "weighted_delta": weighted_delta,
                "color": color_hex,
                "bar_width": min(max(score * 10, 0), 100),
                "mainstream": any(brand.lower() in iem.lower() for brand in KNOWN_BRANDS),
            }
        )
        curves_indexed[idx] = {
            "name": iem,
            "data": iem_curves_by_id[iem],
        }

    return {
        "items": items,
        "total_count": len(items),
        "median_score": round(float(np.median(scores)), 2) if scores else 0.0,
        "top_score": scores[0] if scores else 0.0,
        "lowest_score": scores[-1] if scores else 0.0,
        "freqs": sliced_freqs,
        "shewi_comp": [round(float(v), 2) for v in shewi_comp],
        "jm1_comp": [round(float(v), 2) for v in jm1_comp],
        "pref_top": [round(float(v), 2) for v in pref_top_comp],
        "pref_bottom": [round(float(v), 2) for v in pref_bottom_comp],
        "iem_curves": curves_indexed,
    }


DATA_STORE = init_data()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Target Adherence Ranking</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-body: #12141b;
            --bg-card: #101319;
            --bg-row-hover: #c6adfc1f;
            --border-color: #fff0;
            --text-primary: #fff;
            --text-secondary: #9aa1b3;
            --text-muted: #5e6677;
            --accent: #af9fff;
            --accent-subtle: #877cc1;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        html, body {
            overflow-x: hidden;
            width: 100%;
        }

        body {
            font-family: "Poppins", -apple-system, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-primary);
            padding: 2.5rem 1.5rem;
            line-height: 1.5;
        }

        .container {
            width: 100%;
            max-width: 1100px;
            margin: 0 auto;
        }

        header {
            margin-bottom: 2rem;
        }

        h1 {
            font-size: 1.85rem;
            font-weight: 500;
            margin-bottom: 0.25rem;
        }

        p.subtitle {
            color: var(--text-secondary);
            font-size: 0.95rem;
            word-break: break-all;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.2rem;
        }

        .stat-card span {
            display: block;
            color: var(--text-secondary);
            font-size: 0.85rem;
            margin-bottom: 0.35rem;
        }

        .stat-card strong {
            font-size: 1.6rem;
            font-weight: 500;
        }

        .toolbar {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto 9rem;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
            min-width: 0;
        }

        .search-input {
            flex-grow: 1;
            width: 100%;
            min-width: 0;
            max-width: 400px;
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 0.65rem 1rem;
            color: var(--text-primary);
            font-size: 0.95rem;
            outline: none;
            transition: border-color 0.15s ease;
        }

        .search-input:focus {
            box-shadow: 0 0 0 3px rgba(104, 78, 235, 0.2);
        }

        .count-tag {
            color: var(--text-secondary);
            font-size: 0.9rem;
            text-align: right;
            max-width: min(30rem, calc(100vw - 2rem));
            white-space: normal;
        }

        .mainstream-filter {
            color: var(--text-secondary);
            font-size: 0.9rem;
            min-width: 0;
        }

        .mainstream-filter input[type="checkbox"] {
            accent-color: var(--accent-subtle);
        }

        .table-container {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.95rem;
        }

        th {
            background-color: #161820;
            padding: 0.85rem 1rem;
            font-weight: 500;
            font-size: 0.85rem;
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover td {
            background-color: var(--bg-row-hover);
        }

        .col-rank {
            width: 60px;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
            font-weight: 600;
        }

        .col-score {
            width: 240px;
            font-size: 0.9rem;
        }

        .col-delta {
            width: 110px;
            text-align: right;
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
            font-size: 0.9rem;
        }

        .score-cell {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .score-pill {
            display: inline-block;
            min-width: 48px;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85rem;
            text-align: center;
            color: #0b0f14;
            font-variant-numeric: tabular-nums;
        }

        .score-bar-track {
            flex-grow: 1;
            height: 6px;
            background-color: #21262d;
            border-radius: 3px;
            overflow: hidden;
        }

        .score-bar-fill {
            height: 100%;
            border-radius: 3px;
        }

        .iem-link {
            background: none;
            border: none;
            color: var(--text-primary);
            font-family: inherit;
            font-size: inherit;
            font-weight: 300;
            cursor: pointer;
            text-align: left;
            padding: 0;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            transition: color 0.15s ease;
            word-break: break-word;
        }

        .iem-link:hover {
            color: var(--accent);
            text-decoration: none;
        }

        .iem-link svg {
            opacity: 0.45;
            flex-shrink: 0;
            transition: opacity 0.15s;
        }

        .iem-link:hover svg {
            opacity: 1;
        }

        /* Modal Overlay */
        .modal-overlay {
            position: fixed;
            inset: 0;
            background-color: rgba(0, 0, 0, 0.78);
            backdrop-filter: blur(6px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            padding: 1rem;
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            overflow-y: auto;
            transition: opacity 0.2s ease, visibility 0.2s ease;
        }

        .modal-overlay.active {
            opacity: 1;
            visibility: visible;
            pointer-events: auto;
        }

        .modal-card {
            background: #101319;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            width: 100%;
            max-width: 820px;
            max-height: 90vh;
            padding: 1.25rem;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.7);
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin: auto;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
        }

        .modal-title {
            font-size: 1.15rem;
            font-weight: 600;
            color: #f5f5ff;
            word-break: break-word;
        }

        .modal-subtitle {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .modal-close {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 1.6rem;
            line-height: 1;
            cursor: pointer;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            transition: color 0.15s, background-color 0.15s;
        }

        .modal-close:hover {
            color: var(--text-primary);
            background-color: var(--bg-row-hover);
        }

        .chart-container {
            position: relative;
            width: 100%;
            height: 44vh;
            min-height: 250px;
            max-height: 440px;
        }

        @media (max-width: 768px) {
            body { padding: 1.25rem 0.75rem; }
            .modal-card { 
                padding: 0.85rem; 
                width: 100%; 
                max-height: 92vh; 
            }
            .chart-container { 
                height: 35vh; 
                min-height: 220px; 
            }
            .toolbar {
                grid-template-columns: minmax(0, 1fr);
                gap: 0.6rem;
            }
            .search-input { max-width: none; }
            .count-tag { text-align: left; max-width: none; }
            .col-delta { display: none; }
            .col-rank { width: 38px; }
            .col-score { width: 72px; }
            th, td { padding: 0.65rem 0.5rem; }
            .score-bar-track { display: none; }
            .stats-grid { 
                grid-template-columns: repeat(2, 1fr); 
                gap: 0.6rem; 
            }
            .stat-card { padding: 0.9rem; }
        }

        .ranking-metadata {
            margin-top: 0.35rem;
            font-size: 0.8rem;
            color: var(--text-muted);
            line-height: 1.4;
        }

        .ranking-metadata span {
            color: var(--text-secondary);
        }

        .ranking-metadata .hoverable-param {
            position: relative;
            display: inline-block;
            cursor: default;
            text-decoration: underline;
            text-decoration-thickness: 1px;
            text-underline-offset: 3px;
            color: var(--text-muted);
            transition: color 0.15s ease;
        }

        .ranking-metadata .hoverable-param:hover {
            color: var(--accent);
            text-decoration-thickness: 1.5px;
        }

        .param-popup.norm-popup {
            width: min(320px, 80vw);
            white-space: normal;
            line-height: 1.35;
            text-align: left;
        }

        .param-popup.decay-popup {
            width: 320px;
            white-space: normal;
            line-height: 1.4;
            text-align: left;
        }

        .decay-chart-container {
            position: relative;
            display: block;
            width: 100%;
            height: 150px;
            margin-top: 0.5rem;
            padding-top: 0.5rem;
        }

        .decay-chart-container canvas {
            width: 100% !important;
            height: 100% !important;
        }

        .decay-formula {
            display: block;
            margin: 0.35rem 0;
            color: #ffffff;
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 1rem;
            text-align: center;
        }

        .param-popup {
            visibility: hidden;
            opacity: 0;
            position: absolute;
            top: calc(100% + 7px);
            left: 50%;
            /* Apply horizontal offset through --shift-x */
            transform: translateX(calc(-50% + var(--shift-x, 0px))) translateY(-3px);
            background-color: #161820;
            color: #f5f5ff;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 0.25rem 0.55rem;
            font-size: 0.75rem;
            white-space: nowrap;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
            pointer-events: none;
            transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s ease;
            z-index: 100;
        }

        .hoverable-param:hover .param-popup {
            visibility: visible;
            opacity: 1;
            transform: translateX(calc(-50% + var(--shift-x, 0px))) translateY(0);
        }

        .param-popup::after {
            content: "";
            position: absolute;
            bottom: 100%;
            /* Compensate arrow position so it stays aligned to the text */
            left: calc(50% - var(--shift-x, 0px));
            transform: translateX(-50%);
            border-width: 4px;
            border-style: solid;
            border-color: transparent transparent #30363d transparent;
        }


    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Target Adherence Ranking</h1>
            <p class="subtitle">{{ target_name }}</p>
            <p class="ranking-metadata">
                <span>Rig:</span>
                <span class="hoverable-param">
                    B&amp;K 5128
                    <span class="param-popup norm-popup">Industry standard measurement rig. Complies with ITU-T Rec. P.58 and has the most accurate acoustic input impedance, which is crutial in the measurement accuracy of high output impedance devices such as IEMs or true wireless earphones.</span>
                </span> &nbsp;|&nbsp;
                <span>Norm:</span>
                <span class="hoverable-param">
                    {{ norm_freq }}
                    <span class="param-popup norm-popup">A fixed normalization is not ideal, as a peak/dip at the normalization frequency could considerably lower the score. However, a choice must be made and good IEMs should not behave that way anyways.</span>
                </span> &nbsp;|&nbsp;
                <span>Decay Factor:</span>
                <span class="hoverable-param" onmouseenter="drawDecayChart()">
                    {{ decay_factor }}
                    <span class="param-popup decay-popup">
                        Controls how quickly the score decreases as the weighted error (Δ) increases.
                        <span class="decay-formula">Score = 10 × e<sup>−Δ / D</sup></span>
                        A larger <i>D</i> makes the score fall less aggressively.
                        <span class="decay-chart-container">
                            <canvas id="decayChart"></canvas>
                        </span>
                    </span>
                </span> &nbsp;|&nbsp;
                <span>Weights:</span>
                <span class="hoverable-param">
                    Sub: {{ weights.sub.coeff }}
                    <span class="param-popup">{{ weights.sub.range }} | {{ weights.sub.value_count }} values</span>
                </span> &bull; 
                <span class="hoverable-param">
                    Bass: {{ weights.bass.coeff }}
                    <span class="param-popup">{{ weights.bass.range }} | {{ weights.bass.value_count }} values</span>
                </span> &bull; 
                <span class="hoverable-param">
                    Mids: {{ weights.mids.coeff }}
                    <span class="param-popup">{{ weights.mids.range }} | {{ weights.mids.value_count }} values</span>
                </span> &bull; 
                <span class="hoverable-param">
                    Canal: {{ weights.canal.coeff }}
                    <span class="param-popup">{{ weights.canal.range }} | {{ weights.canal.value_count }} values</span>
                </span> &bull; 
                <span class="hoverable-param">
                    Pinna: {{ weights.pinna.coeff }}
                    <span class="param-popup">{{ weights.pinna.range }} | {{ weights.pinna.value_count }} values</span>
                </span>
            </p>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <span>Total Evaluated</span>
                <strong>{{ data['total_count'] }}</strong>
            </div>
            <div class="stat-card">
                <span>Median Score</span>
                <strong>{{ data['median_score'] }}</strong>
            </div>
            <div class="stat-card">
                <span>Highest Score</span>
                <strong>{{ data['top_score'] }}</strong>
            </div>
            <div class="stat-card">
                <span>Lowest Score</span>
                <strong>{{ data['lowest_score'] }}</strong>
            </div>
        </div>

        <div class="toolbar">
            <input 
                type="text" 
                id="search" 
                class="search-input" 
                placeholder="Search earphone or brand..." 
                oninput="filterIEMs()"
                autocomplete="off"
            >
            <label class="mainstream-filter">
                <input type="checkbox" id="mainstream-only" {% if ONLY_KNOWN_BRANDS %}checked{% endif %} onchange="filterIEMs()">
                Only include mainstream brands
            </label>
            <span class="count-tag" id="visible-count">Showing {{ data['total_count'] }} items</span>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th class="col-rank">#</th>
                        <th>Model</th>
                        <th class="col-score">Score</th>
                        <th class="col-delta">W Error</th>
                    </tr>
                </thead>
                <tbody id="iem-table-body">
                    {% for item in data['items'] %}
                    <tr class="iem-row" data-name="{{ item.name.lower() }}" data-mainstream="{{ item.mainstream|lower }}">
                        <td class="col-rank">{{ item.rank }}</td>
                        <td class="col-name">
                            <button class="iem-link" onclick="openGraphModal({{ item.id }})">
                                <span>{{ item.name }}</span>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M3 3v18h18"/>
                                    <path d="m19 9-5 5-4-4-3 3"/>
                                </svg>
                            </button>
                        </td>
                        <td class="col-score">
                            <div class="score-cell">
                                <span class="score-pill" style="background-color: {{ item.color }};">
                                    {{ "%.2f"|format(item.score) }}
                                </span>
                                <div class="score-bar-track">
                                    <div class="score-bar-fill" style="width: {{ item.bar_width }}%; background-color: {{ item.color }};"></div>
                                </div>
                            </div>
                        </td>
                        <td class="col-delta">{{ item.weighted_delta }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <!-- Modal Popup for Graph -->
    <div id="graphModal" class="modal-overlay" onclick="handleBackdropClick(event)">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 id="modalTitle" class="modal-title">Frequency Response</h2>
                    <p class="modal-subtitle">Compensated to JM-1 DF (Tilt -1dB/Oct)</p>
                </div>
                <button class="modal-close" onclick="closeGraphModal()">&times;</button>
            </div>
            <div class="chart-container">
                <canvas id="frChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        const freqs = {{ data['freqs'] | tojson }};
        const shewiComp = {{ data['shewi_comp'] | tojson }};
        const jm1Comp = {{ data['jm1_comp'] | tojson }};
        const prefTop = {{ data['pref_top'] | tojson }};
        const prefBottom = {{ data['pref_bottom'] | tojson }};
        const decayFactor = {{ decay_factor | tojson }};
        let chartInstance = null;
        let decayChartInstance = null;

        function drawDecayChart() {
            if (decayChartInstance) return;
            const canvas = document.getElementById('decayChart');
            if (!canvas) return;

            const deltas = [500, 650, 850, 1100, 1450, 1900, 2500, 3300, 4300, 5600, 7300, 10000];
            const points = deltas.map(delta => ({
                x: delta,
                y: 10 * Math.exp(-delta / decayFactor)
            }));
            const ctx = canvas.getContext('2d');
            const gradient = ctx.createLinearGradient(0, 0, 0, 150);
            gradient.addColorStop(0, 'rgba(104, 78, 235, 0.4)');
            gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

            decayChartInstance = new Chart(ctx, {
                type: 'line',
                data: { datasets: [{
                    label: 'Score',
                    data: points,
                    borderColor: '#684EEB',
                    backgroundColor: gradient,
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.25
                }] },
                options: {
                    animation: { duration: 500 },
                    maintainAspectRatio: false,
                    responsive: true,
                    font: { family: 'Poppins' },
                    scales: {
                        x: {
                            type: 'logarithmic', min: 500, max: 10000,
                            grid: { color: '#1f242d', borderColor: '#30363d' },
                            ticks: {
                                color: '#9aa1b3',
                                font: { family: 'Poppins' },
                                autoSkip: false,
                                callback: value => {
                                    const tickValues = [500, 1000, 2000, 5000, 10000];
                                    if (!tickValues.includes(Number(value))) return null;
                                    return value >= 1000 ? `${value / 1000}k` : '500';
                                }
                            },
                            title: { display: true, text: 'Δ', color: '#9aa1b3', font: { family: 'Poppins' } }
                        },
                        y: {
                            min: 0, max: 10,
                            grid: { color: '#1a1f26', borderColor: '#30363d' },
                            ticks: { color: '#9aa1b3', stepSize: 2, font: { family: 'Poppins' } },
                            title: { display: true, text: 'Score', color: '#9aa1b3', font: { family: 'Poppins' } }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            titleFont: { family: 'Poppins' },
                            bodyFont: { family: 'Poppins' },
                            callbacks: {
                                title: items => `Δ = ${Math.round(items[0].parsed.x)}`,
                                label: item => ` Score: ${item.parsed.y.toFixed(2)}`
                            }
                        }
                    }
                }
            });
        }

        function filterIEMs() {
            const query = document.getElementById('search').value.toLowerCase().trim();
            const mainstreamOnly = document.getElementById('mainstream-only').checked;
            const rows = document.querySelectorAll('.iem-row');
            let visibleCount = 0;
            const visibleScores = [];

            rows.forEach(row => {
                const name = row.getAttribute('data-name');
                if (name.includes(query) && (!mainstreamOnly || row.dataset.mainstream === 'true')) {
                    row.style.display = '';
                    visibleCount++;
                    visibleScores.push(parseFloat(row.querySelector('.score-pill').textContent));
                } else {
                    row.style.display = 'none';
                }
            });

            document.getElementById('visible-count').textContent = `Showing ${visibleCount} items`;
            const sortedScores = visibleScores.sort((a, b) => a - b);
            const median = sortedScores.length
                ? (sortedScores.length % 2
                    ? sortedScores[(sortedScores.length - 1) / 2]
                    : (sortedScores[sortedScores.length / 2 - 1] + sortedScores[sortedScores.length / 2]) / 2)
                : 0;
            const stats = document.querySelectorAll('.stat-card strong');
            stats[0].textContent = visibleCount;
            stats[1].textContent = median.toFixed(2);
            stats[2].textContent = visibleScores.length ? Math.max(...visibleScores).toFixed(2) : '0.00';
            stats[3].textContent = visibleScores.length ? Math.min(...visibleScores).toFixed(2) : '0.00';
        }

        function handleBackdropClick(event) {
            if (event.target === document.getElementById('graphModal')) {
                closeGraphModal();
            }
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeGraphModal();
        });

        function closeGraphModal() {
            document.getElementById('graphModal').classList.remove('active');
            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }
        }

        async function openGraphModal(id) {
            const res = await fetch(`/api/graph/${id}`);
            const iem = await res.json();

            // Detect mobile width
            const isMobile = window.innerWidth < 768;

            document.getElementById('modalTitle').textContent = iem.name;
            document.getElementById('graphModal').classList.add('active');

            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }

            const canvas = document.getElementById('frChart');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const gradient = ctx.createLinearGradient(0, 0, 0, 450);
            gradient.addColorStop(0, 'rgba(81, 58, 197, 0.45)');
            gradient.addColorStop(1, 'rgba(0, 0, 0, 0.0)');

            const pointsIEM = iem.data.map((y, i) => ({ x: freqs[i], y: y }));
            const pointsShewi = shewiComp.map((y, i) => ({ x: freqs[i], y: y }));
            const pointsJM1 = jm1Comp.map((y, i) => ({ x: freqs[i], y: y }));
            const pointsPrefTop = prefTop.map((y, i) => ({ x: freqs[i], y: y }));
            const pointsPrefBottom = prefBottom.map((y, i) => ({ x: freqs[i], y: y }));

            requestAnimationFrame(() => {
                chartInstance = new Chart(ctx, {
                    type: 'line',
                    data: {
                        datasets: [
                            {
                                label: iem.name,
                                data: pointsIEM,
                                borderColor: "#684EEB",
                                borderWidth: isMobile ? 1.8 : 2.5,
                                fill: 2,
                                backgroundColor: gradient,
                                order: 1
                            },
                            {
                                label: "Shewi Target (DFHRTF)",
                                data: pointsShewi,
                                borderColor: "#877CC1",
                                borderWidth: isMobile ? 1.5 : 2,
                                borderDash: [5, 5],
                                fill: false,
                                order: 2
                            },
                            {
                                label: "JM-1 DF (Tilt -1dB/Oct)",
                                data: pointsJM1,
                                borderColor: "#3a404d",
                                borderWidth: 1,
                                fill: false,
                                order: 3
                            },
                            {
                                label: "Preference Bounds (Top)",
                                data: pointsPrefTop,
                                borderColor: "#282e39",
                                borderWidth: 1,
                                fill: false,
                                order: 4
                            },
                            {
                                label: "Preference Bounds (Bottom)",
                                data: pointsPrefBottom,
                                borderColor: "#282e39",
                                borderWidth: 1,
                                fill: false,
                                order: 4
                            }
                        ]
                    },
                    options: {
                        animations: {
                            y: {
                                type: 'number',
                                duration: 750,
                                easing: 'easeOutQuart',
                                from: (c) => (c.chart.scales.y ? c.chart.scales.y.getPixelForValue(-20) : c.chart.height)
                            }
                        },
                        maintainAspectRatio: false,
                        responsive: true,
                        interaction: {
                            mode: 'index',
                            intersect: false
                        },
                        elements: {
                            point: { radius: 0 }
                        },
                        layout: {
                            padding: isMobile ? { left: -4, right: 4, top: 0, bottom: 0 } : 0
                        },
                        scales: {
                            x: {
                                type: 'logarithmic',
                                min: 20,
                                max: 20000,
                                grid: {
                                    color: '#1f242d',
                                    borderColor: '#30363d'
                                },
                                ticks: {
                                    color: '#f5f5ff',
                                    font: { family: 'Poppins', size: isMobile ? 8 : 11 },
                                    padding: isMobile ? 2 : 6,
                                    callback: function(val) {
                                        const ticks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
                                        if (ticks.includes(val)) {
                                            return val >= 1000 ? (val / 1000) + 'k' : val;
                                        }
                                        return null;
                                    }
                                },
                                title: {
                                    // Hidden on mobile to reclaim vertical height
                                    display: !isMobile,
                                    text: 'Frequency (Hz)',
                                    color: '#f5f5ff',
                                    font: { family: 'Poppins', size: 11 }
                                }
                            },
                            y: {
                                min: -20,
                                max: 20,
                                grid: {
                                    color: '#1a1f26',
                                    borderColor: '#30363d'
                                },
                                ticks: {
                                    stepSize: 5,
                                    color: '#f5f5ff',
                                    font: { family: 'Poppins', size: isMobile ? 8 : 11 },
                                    padding: isMobile ? 2 : 6,
                                    callback: (val) => `${val} dB`
                                },
                                title: {
                                    // Hidden on mobile to reclaim horizontal left margin
                                    display: !isMobile,
                                    text: 'dB',
                                    color: '#f5f5ff',
                                    font: { family: 'Poppins', size: 11 }
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: {
                                    filter: (item) => !item.text.includes('Preference Bounds'),
                                    color: '#FFFFFF',
                                    font: { family: 'Poppins', size: isMobile ? 9 : 12 },
                                    boxWidth: isMobile ? 12 : 24,
                                    padding: isMobile ? 6 : 10
                                }
                            },
                            tooltip: {
                                backgroundColor: 'rgba(16, 19, 25, 0.95)',
                                titleColor: '#f5f5ff',
                                bodyColor: '#f5f5ff',
                                borderColor: '#30363d',
                                borderWidth: 1,
                                titleFont: { family: 'Poppins', size: isMobile ? 10 : 12 },
                                bodyFont: { family: 'Poppins', size: isMobile ? 9 : 12 },
                                callbacks: {
                                    title: (items) => `${Math.round(items[0].parsed.x)} Hz`,
                                    label: (item) => ` ${item.dataset.label}:${item.parsed.y.toFixed(2)} dB`
                                }
                            }
                        }
                    }
                });
            });
        }

        // So overkill lol
        function updatePopupPosition(item) {
            const popup = item.querySelector('.param-popup');
            if (!popup) return;

            const itemRect = item.getBoundingClientRect();
            const triggerCenter = itemRect.left + itemRect.width / 2;
            const popupWidth = popup.offsetWidth;

            const naturalLeft = triggerCenter - popupWidth / 2;
            const naturalRight = triggerCenter + popupWidth / 2;
            const padding = 16;
            const vw = window.innerWidth;

            let shift = 0;
            if (naturalLeft < padding) {
                shift = padding - naturalLeft;
            } else if (naturalRight > vw - padding) {
                shift = (vw - padding) - naturalRight;
            }

            popup.style.setProperty('--shift-x', `${Math.round(shift)}px`);
        }

        function updateAllPopups() {
            document.querySelectorAll('.hoverable-param').forEach(updatePopupPosition);
        }

        // Pre-calculate on load and resize so values are ready before hovering
        window.addEventListener('resize', updateAllPopups);
        window.addEventListener('DOMContentLoaded', updateAllPopups);
        updateAllPopups();

        // Ensure position is accurate on hover
        document.querySelectorAll('.hoverable-param').forEach(item => {
            item.addEventListener('mouseenter', () => updatePopupPosition(item));
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE,
        data=DATA_STORE,
        target_name=TARGET,
        norm_freq=POINT_TO_FREQ.get(NORMALIZATION_POINT, "1kHz"),
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


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
