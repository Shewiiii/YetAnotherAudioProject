from pathlib import Path

import numpy as np


def read_file(path: str | Path) -> tuple[str, str]:
    data = np.loadtxt(path)
    freq = data[:, 0]
    spl = data[:, 1]

    order = np.argsort(freq)  # Should be sorted anyways
    return freq[order], spl[order]


# Default values of SquigLink ecosystem for some reasons
common_freq = np.geomspace(20, 20186.382308152035, 480)