from pathlib import Path
import numpy as np
from utils import read_file, common_freq

# Average frequency response files ("phones") in the following folder.
# Each IEM has been EQed as coherently as possible to my DFHRTF (Diffuse Field Head Related Transfer Function, see README)
# by ear, using 5128 data, sinesweeps, and many fails and retries,
# so it "sounds flat" not for the population average, but for me.
# By averaging, my hope is to dilute HpTF effect (variation in frequency response not related to anatomy but the IEM load) and inaccuracies.
# For that exact reason, a "one-fits-all" target does not exist, even at the individual scale, but is still insteresting to establish, as it
# tells what sound signature on average my brain expects to hear.
# Bass shelf level is arbitrary to match preference.

PHONES = "phones/*.txt"
OUTPUT = "Shewi Target (DFHRTF).txt"


files = sorted(Path().glob(PHONES))
phones = [read_file(file) for file in files]

spls = []

for freq, spl in phones:
    # Interpolate and clean spl data
    spl_interp = np.interp(np.log10(common_freq), np.log10(freq), spl)
    spls.append(spl_interp)

mean_spl = np.mean(spls, axis=0)

with open(OUTPUT, "w", encoding="utf-8") as f:
    for freq, spl in zip(common_freq, mean_spl):
        f.write(f"{freq:.15f} {spl:.15f}\n")
