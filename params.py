EXCLUDE_PROJECTS = True  # Exclude prototypes not on the market
ONLY_KNOWN_BRANDS = False
TARGET = "targets/Shewi Target (DFHRTF).txt"
JM1_TARGET = "targets/JM-1 DF (Tilt_ -1dB_Oct) Target.txt"
FREQUENCY_RESPONSES = "frequency_responses/*.txt"
PREF_BOUNDS_TOP = "targets/pref_bounds_top.txt"
PREF_BOUNDS_BOTTOM = "targets/pref_bounds_bottom.txt"

# Coeffs and normalization parameters
SUB_WEIGHT_START = 0
SUB_WEIGHT_END = 66  # 66: 50Hz
SUB_COEFF = 0.2

BASS_WEIGHT_START = 66
BASS_WEIGHT_END = 112  # 112: 100Hz
BASS_COEFF = 0.5

MIDRANGE_WEIGHT_START = 177 # 177: 250Hz
MIDRANGE_WEIGHT_END = 321 # 321: ~2kHz
MIDRANGE_COEFF = 1  # Many values

CANAL_WEIGHT_START = 321 
CANAL_WEIGHT_END = 367  # 367: ~4kHz
CANAL_COEFF = 2 # Not many values

PINNA_WEIGHT_START = 367  # 272: ~1kHz, 367: ~4kHz
PINNA_WEIGHT_END = 459  # 432: ~10kHz, 459: ~15kHz
PINNA_COEFF = 3


NORMALIZATION_POINT = 272  # 223: ~500hz, 272: ~1kHz, see generated target from average.py
NORMALIZATION_SPL = 60  # in dB but probably does not matter

# Ignore FR above x Hz. 463: ~16kHz, ~~should probably not be changed~~
# I decided to remove the limit to punish very bright IEMs (eg. Daybreak): 
# yes it is not accurate that high in frequency but still relevant on a large scale
# There is not many values anyways
DATA_LIMIT = 481

# Scale factor for exponential decay; lower = agressive drop, higher = flatter
DECAY_FACTOR = 2500

POINT_TO_FREQ = {
    66: "50Hz",
    112: "100Hz",
    177: "250Hz",
    223: "500Hz",
    272: "1kHz",
    321: "2kHz",
    367: "4kHz",
    432: "10kHz",
    459: "15kHz",
    463: "16kHz",
}

KNOWN_BRANDS = (
    "apple",
    "airpods",
    "earpods",
    "beats",
    "bose",
    "sony",
    "sennheiser",
    "audio-technica",
    "audio technica",
    "beyerdynamic",
    "akg",
    "shure",
    "jbl",
    "koss",
    "philips",
    "panasonic",
    "pioneer",
    "jvc",
    "yamaha",
    "denon",
    "bang & olufsen",
    "b&o",
    "bowers & wilkins",
    "b&w",
    "samsung",
    "galaxy buds",
    "google",
    "huawei",
    "xiaomi",
    "oneplus",
    "oppo",
    "lg ",
    "motorola",
    "nothing",
    "jabra",
    "anker",
    "soundcore",
    "marshall",
    "skullcandy",
)