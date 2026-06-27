import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from SkyReg_Lib import gps_from_frame_npz


def parse_args():
    parser = argparse.ArgumentParser(description="Save per-pixel GPS [lat, lon, alt] from a frame NPZ.")
    parser.add_argument("frame_npz", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists: {args.output}")

    gps = gps_from_frame_npz(args.frame_npz)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, gps)
    print(f"Wrote {args.output}")
    print(f"gps shape={gps.shape} dtype={gps.dtype}")


if __name__ == "__main__":
    main()
