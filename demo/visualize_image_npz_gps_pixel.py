import argparse
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from SkyReg_Lib import gps_from_frame_npz, load_frame_npz


def imread_rgb(path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise IOError(f"Could not load image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def finite_window_stats(gps_map, x, y, radius):
    h, w, _ = gps_map.shape
    x0 = max(0, x - radius)
    x1 = min(w, x + radius + 1)
    y0 = max(0, y - radius)
    y1 = min(h, y + radius + 1)
    window = gps_map[y0:y1, x0:x1]
    valid = np.isfinite(window).all(axis=-1)
    if not np.any(valid):
        return None
    return np.nanmedian(window[valid], axis=0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Display an image and click pixels to inspect GPS reconstructed from a frame NPZ."
    )
    parser.add_argument("image", type=Path, help="Image path to display.")
    parser.add_argument("frame_npz", type=Path, help="Frame NPZ containing depth/FOV/ECEF pose.")
    parser.add_argument("--window-radius", type=int, default=2)
    return parser.parse_args()


def main():
    args = parse_args()

    image = imread_rgb(args.image)
    depth, width, height, _, pos_ecef, _ = load_frame_npz(args.frame_npz)

    print(f"image: {args.image}")
    print(f"frame_npz: {args.frame_npz}")
    print("Reconstructing GPS map...")
    gps_map = gps_from_frame_npz(args.frame_npz)

    if image.shape[:2] != gps_map.shape[:2]:
        raise ValueError(f"Image shape {image.shape[:2]} does not match NPZ/GPS shape {gps_map.shape[:2]}")

    fig, ax = plt.subplots()
    ax.imshow(image)
    ax.set_title(f"{args.image.name} | click a pixel to inspect GPS")
    marker = ax.scatter([], [], c="red", s=40)

    def on_click(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return

        x = int(round(event.xdata))
        y = int(round(event.ydata))
        if x < 0 or x >= width or y < 0 or y >= height:
            return

        lat, lon, alt = gps_map[y, x]
        marker.set_offsets([[x, y]])
        fig.canvas.draw_idle()

        print()
        print(f"pixel: x={x}, y={y}")
        print(f"depth: {depth[y, x]:.6f} m")
        if not np.isfinite([lat, lon, alt]).all():
            print("gps: invalid / NaN at this pixel")
            return

        print(f"gps: lat={lat:.10f}, lon={lon:.10f}, alt={alt:.3f} m")
        print(f"maps: https://www.google.com/maps?q={lat:.10f},{lon:.10f}")

        median_gps = finite_window_stats(gps_map, x, y, args.window_radius)
        if median_gps is not None:
            size = 2 * args.window_radius + 1
            print(
                f"{size}x{size} median: "
                f"lat={median_gps[0]:.10f}, lon={median_gps[1]:.10f}, alt={median_gps[2]:.3f} m"
            )

        print(
            "camera ecef: "
            f"x={pos_ecef[0]:.3f}, y={pos_ecef[1]:.3f}, z={pos_ecef[2]:.3f}"
        )

    fig.canvas.mpl_connect("button_press_event", on_click)
    plt.show()


if __name__ == "__main__":
    main()
