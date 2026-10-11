"""Where the recordings and results live, in one place.

The recorder writes into data/. Older recordings were moved aside into backupData/; both folders
are read, so every tool sees the whole history. Files are ordered by name (their date), and a name
that occurs in both folders gives two files: they hold different parts of that day.
"""
import glob
import os

ADSB = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ADSB)
DATA = os.path.join(PROJ, "data")
DATA_DIRS = [os.path.join(PROJ, "backupData"), DATA]
RAW_IQ = os.path.join(DATA, "raw_iq")
RESULTS = os.path.join(ADSB, "results")


def data_files(pattern):
    """Recording files matching a glob pattern (e.g. 'sbs_t_*.txt') in every data folder, by date."""
    paths = [p for d in DATA_DIRS for p in glob.glob(os.path.join(d, pattern))]
    return sorted(paths, key=lambda p: (os.path.basename(p), DATA_DIRS.index(os.path.dirname(p))))


def label(path):
    """Short unique name for a recording: the file name, prefixed by its folder unless it is data/."""
    folder = os.path.basename(os.path.dirname(path))
    return os.path.basename(path) if folder == "data" else f"{folder}/{os.path.basename(path)}"
