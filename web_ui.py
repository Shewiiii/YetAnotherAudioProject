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
from utils import KNOWN_BRANDS, common_freq, read_file

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
    weights[BASS_WEIGHT_START:BASS_WEIGHT_END] = BASS_COEFF
    weights[MIDRANGE_WEIGHT_START:MIDRANGE_WEIGHT_END] = MIDRANGE_COEFF
    weights[CANAL_WEIGHT_START:CANAL_WEIGHT_END] = CANAL_COEFF
    weights[PINNA_WEIGHT_START:PINNA_WEIGHT_END] = PINNA_COEFF
    weights_sliced = weights[:DATA_LIMIT]

    deltas = {}
    iem_curves_by_id = {}

    for iem, (freq, spl) in frequency_response_dict.items():
        if (not EXCLUDE_PROJECTS or "project" not in iem.lower()) and (
            not ONLY_KNOWN_BRANDS or any(brand in iem.lower() for brand in KNOWN_BRANDS)
        ):
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

    for idx, (iem, raw_delta) in enumerate(sorted_deltas.items()):
        score = round(10 * np.exp(-raw_delta / DECAY_FACTOR), 2)
        scores.append(score)
        color_hex = mcolors.to_hex(cmap(norm(score)))

        items.append(
            {
                "id": idx,
                "rank": idx + 1,
                "name": iem,
                "score": score,
                "raw_delta": raw_delta,
                "color": color_hex,
                "bar_width": min(max(score * 10, 0), 100),
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

        body {
            font-family: "Poppins", -apple-system, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-primary);
            padding: 2.5rem 1.5rem;
            line-height: 1.5;
        }

        .container {
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
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .search-input {
            flex-grow: 1;
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
        }

        .table-container {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
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
            pointer-events: none;
            transition: opacity 0.2s ease;
        }

        .modal-overlay.active {
            opacity: 1;
            pointer-events: auto;
        }

        .modal-card {
            background: #101319;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            width: 100%;
            max-width: 960px;
            padding: 1.5rem;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.7);
            display: flex;
            flex-direction: column;
            gap: 1rem;
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
            height: 52vh;
            min-height: 320px;
            max-height: 520px;
        }

        @media (max-width: 768px) {
            body { padding: 1.25rem 0.75rem; }
            .modal-card { padding: 1rem; width: 96vw; }
            .chart-container { height: 40vh; min-height: 270px; }
            .col-delta { display: none; }
            .col-score { width: 140px; }
            .score-bar-track { display: none; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
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

        .ranking-metadata .weight-item {
            position: relative;
            display: inline-block;
            cursor: default;
            text-decoration: none;
            color: var(--text-muted);
            transition: color 0.15s ease;
        }

        .ranking-metadata .weight-item:hover {
            color: var(--accent);
        }

        .weight-popup {
            visibility: hidden;
            opacity: 0;
            position: absolute;
            bottom: calc(100% + 7px);
            left: 50%;
            transform: translateX(-50%) translateY(3px);
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

        .weight-popup::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border-width: 4px;
            border-style: solid;
            border-color: #30363d transparent transparent transparent;
        }

        .weight-item:hover .weight-popup {
            visibility: visible;
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Target Adherence Ranking</h1>
            <p class="subtitle">{{ target_name }}</p>
            <p class="ranking-metadata">
                <span>Rig:</span> B&amp;K 5128 &nbsp;|&nbsp;
                <span>Norm:</span> {{ norm_freq }} &nbsp;|&nbsp;
                <span>Decay Factor:</span> {{ decay_factor }} &nbsp;|&nbsp;
                <span>Weights:</span> 
                <span class="weight-item">
                    Bass: {{ weights.bass.coeff }}
                    <span class="weight-popup">{{ weights.bass.range }}</span>
                </span> &bull; 
                <span class="weight-item">
                    Mid: {{ weights.mid.coeff }}
                    <span class="weight-popup">{{ weights.mid.range }}</span>
                </span> &bull; 
                <span class="weight-item">
                    Canal: {{ weights.canal.coeff }}
                    <span class="weight-popup">{{ weights.canal.range }}</span>
                </span> &bull; 
                <span class="weight-item">
                    Pinna: {{ weights.pinna.coeff }}
                    <span class="weight-popup">{{ weights.pinna.range }}</span>
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
            <span class="count-tag" id="visible-count">Showing {{ data['total_count'] }} items</span>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th class="col-rank">#</th>
                        <th>Model</th>
                        <th class="col-score">Score (/10)</th>
                        <th class="col-delta">Raw Delta</th>
                    </tr>
                </thead>
                <tbody id="iem-table-body">
                    {% for item in data['items'] %}
                    <tr class="iem-row" data-name="{{ item.name.lower() }}">
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
                        <td class="col-delta">{{ item.raw_delta }}</td>
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
        let chartInstance = null;

        function filterIEMs() {
            const query = document.getElementById('search').value.toLowerCase().trim();
            const rows = document.querySelectorAll('.iem-row');
            let visibleCount = 0;

            rows.forEach(row => {
                const name = row.getAttribute('data-name');
                if (name.includes(query)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            document.getElementById('visible-count').textContent = `Showing ${visibleCount} items`;
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
                                borderWidth: 2.5,
                                fill: 2,
                                backgroundColor: gradient,
                                order: 1
                            },
                            {
                                label: "Shewi Target (DFHRTF)",
                                data: pointsShewi,
                                borderColor: "#877CC1",
                                borderWidth: 2,
                                borderDash: [5, 5],
                                fill: false,
                                order: 2
                            },
                            {
                                label: "JM-1 DF (Tilt -1dB/Oct)",
                                data: pointsJM1,
                                borderColor: "#3a404d",
                                borderWidth: 1.5,
                                fill: false,
                                order: 3
                            },
                            {
                                label: "Preference Bounds (Top)",
                                data: pointsPrefTop,
                                borderColor: "#282e39",
                                borderWidth: 1.5,
                                fill: false,
                                order: 4
                            },
                            {
                                label: "Preference Bounds (Bottom)",
                                data: pointsPrefBottom,
                                borderColor: "#282e39",
                                borderWidth: 1.5,
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
                                font: { family: 'Poppins', size: 11 },
                                callback: function(val) {
                                    const ticks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
                                    if (ticks.includes(val)) {
                                        return val >= 1000 ? (val / 1000) + 'k' : val;
                                    }
                                    return null;
                                }
                            },
                            title: {
                                display: true,
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
                                font: { family: 'Poppins', size: 11 },
                                callback: (val) => `${val} dB`
                            },
                            title: {
                                display: true,
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
                                font: { family: 'Poppins', size: 12 },
                                boxWidth: 24
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(16, 19, 25, 0.95)',
                            titleColor: '#f5f5ff',
                            bodyColor: '#f5f5ff',
                            borderColor: '#30363d',
                            borderWidth: 1,
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
            "bass": {
                "coeff": BASS_COEFF,
                "range": f"{POINT_TO_FREQ.get(BASS_WEIGHT_START, '20Hz')} – {POINT_TO_FREQ.get(BASS_WEIGHT_END, '')}",
            },
            "mid": {
                "coeff": MIDRANGE_COEFF,
                "range": f"{POINT_TO_FREQ.get(MIDRANGE_WEIGHT_START, '')} – {POINT_TO_FREQ.get(MIDRANGE_WEIGHT_END, '')}",
            },
            "canal": {
                "coeff": CANAL_COEFF,
                "range": f"{POINT_TO_FREQ.get(CANAL_WEIGHT_START, '')} – {POINT_TO_FREQ.get(CANAL_WEIGHT_END, '')}",
            },
            "pinna": {
                "coeff": PINNA_COEFF,
                "range": f"{POINT_TO_FREQ.get(PINNA_WEIGHT_START, '')} – {POINT_TO_FREQ.get(PINNA_WEIGHT_END, '')}",
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
