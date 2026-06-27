import argparse
import math
from pathlib import Path

import numpy as np

from SkyReg_Lib import gps_from_frame_npz, load_frame_npz


MEAN_EARTH_RADIUS_M = 6371008.8


def wrap_lon_diff_deg(d):
    return ((d + 180.0) % 360.0) - 180.0


def load_prediction_latlon(pred_npz_path):
    """Load predicted per-pixel lat/lon from common NPZ layouts."""
    with np.load(pred_npz_path) as data:
        keys = set(data.files)

        if {"lat", "lon"}.issubset(keys):
            lat = data["lat"].astype(np.float64)
            lon = data["lon"].astype(np.float64)
        elif {"lat_deg", "lon_deg"}.issubset(keys):
            lat = data["lat_deg"].astype(np.float64)
            lon = data["lon_deg"].astype(np.float64)
        elif "gps" in keys:
            gps = data["gps"].astype(np.float64)
            lat = gps[..., 0]
            lon = gps[..., 1]
        elif "arr_0" in keys and data["arr_0"].ndim == 3 and data["arr_0"].shape[-1] >= 2:
            gps = data["arr_0"].astype(np.float64)
            lat = gps[..., 0]
            lon = gps[..., 1]
        else:
            raise KeyError(
                f"{pred_npz_path} does not contain lat/lon. "
                f"Expected lat+lon, lat_deg+lon_deg, gps, or arr_0. Found: {sorted(keys)}"
            )

        if "valid_mask" in keys:
            valid = data["valid_mask"].astype(bool)
        elif "valid" in keys:
            valid = data["valid"].astype(bool)
        else:
            valid = np.isfinite(lat) & np.isfinite(lon)

    if lat.shape != lon.shape:
        raise ValueError(f"Prediction lat/lon shapes differ: {lat.shape} vs {lon.shape}")
    if valid.shape != lat.shape:
        raise ValueError(f"Prediction valid mask shape {valid.shape} does not match lat/lon {lat.shape}")

    return lat, lon, valid


def load_skyreg_gt_latlon(frame_npz_path):
    """Reconstruct SkyReg GT per-pixel lat/lon from a frame-style NPZ."""
    gps = gps_from_frame_npz(frame_npz_path)
    depth, _, _, _, _, _ = load_frame_npz(frame_npz_path)
    lat = gps[..., 0]
    lon = gps[..., 1]
    valid = np.isfinite(depth) & (depth > 0) & np.isfinite(lat) & np.isfinite(lon)
    return lat, lon, valid


def find_prediction_for_gt(gt_path, pred_root):
    candidates = [
        pred_root / gt_path.name,
        pred_root / gt_path.with_suffix(".npz").name,
        pred_root / f"{gt_path.stem}.npz",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def median_latlon(lat, lon, valid):
    valid = valid & np.isfinite(lat) & np.isfinite(lon)
    num_valid = int(valid.sum())
    if num_valid == 0:
        raise ValueError("No valid pixels for median GPS")

    return {
        "lat": float(np.median(lat[valid])),
        "lon": float(np.median(lon[valid])),
        "num_valid": num_valid,
    }


def haversine_m(lat1_deg, lon1_deg, lat2_deg, lon2_deg, radius_m=MEAN_EARTH_RADIUS_M):
    lat1 = np.deg2rad(lat1_deg)
    lon1 = np.deg2rad(lon1_deg)
    lat2 = np.deg2rad(lat2_deg)
    lon2 = np.deg2rad(lon2_deg)
    dphi = lat2 - lat1
    dlmb = lon2 - lon1
    a = np.sin(dphi / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlmb / 2) ** 2
    return float(2 * radius_m * np.arcsin(np.minimum(1.0, np.sqrt(a))))


def compare_median_latlon(lat_gt, lon_gt, valid_gt, lat_pred, lon_pred, valid_pred, radius_m=MEAN_EARTH_RADIUS_M):
    gt = median_latlon(lat_gt, lon_gt, valid_gt)
    pred = median_latlon(lat_pred, lon_pred, valid_pred)

    dlat = pred["lat"] - gt["lat"]
    dlon = float(wrap_lon_diff_deg(pred["lon"] - gt["lon"]))
    dist_m = haversine_m(gt["lat"], gt["lon"], pred["lat"], pred["lon"], radius_m=radius_m)

    mean_lat_rad = math.radians(gt["lat"])
    m_per_deg_lat = math.pi / 180.0 * radius_m
    m_per_deg_lon = math.pi / 180.0 * radius_m * math.cos(mean_lat_rad)

    return {
        "gt_median_lat_deg": gt["lat"],
        "gt_median_lon_deg": gt["lon"],
        "pred_median_lat_deg": pred["lat"],
        "pred_median_lon_deg": pred["lon"],
        "gt_num_valid": gt["num_valid"],
        "pred_num_valid": pred["num_valid"],
        "abs_dlat_deg": float(abs(dlat)),
        "abs_dlon_deg": float(abs(dlon)),
        "dist_m": dist_m,
        "signed_dlat_deg": float(dlat),
        "signed_dlon_deg": float(dlon),
        "bias_north_m": float(dlat * m_per_deg_lat),
        "bias_east_m": float(dlon * m_per_deg_lon),
    }


def compare_skyreg_frame_median_to_prediction(gt_frame_npz_path, pred_npz_path, radius_m=MEAN_EARTH_RADIUS_M):
    lat_gt, lon_gt, valid_gt = load_skyreg_gt_latlon(gt_frame_npz_path)
    lat_pred, lon_pred, valid_pred = load_prediction_latlon(pred_npz_path)
    return compare_median_latlon(lat_gt, lon_gt, valid_gt, lat_pred, lon_pred, valid_pred, radius_m=radius_m)


def print_stats(stats, prefix=""):
    for key, value in stats.items():
        print(f"{prefix}{key}: {value}")


def run_single(args):
    stats = compare_skyreg_frame_median_to_prediction(args.gt_frame_npz, args.pred_npz, radius_m=args.radius_m)
    print_stats(stats)


def run_folder(args):
    gt_root = Path(args.gt_root)
    pred_root = Path(args.pred_root)
    gt_files = sorted(gt_root.rglob("*.npz"))

    if args.limit is not None:
        gt_files = gt_files[: args.limit]

    count = 0
    missing = 0
    failed = 0
    distances = []
    abs_dlat = []
    abs_dlon = []
    less_than = {20: 0, 30: 0, 40: 0, 50: 0}

    for gt_path in gt_files:
        rel = gt_path.relative_to(gt_root)
        pred_path = pred_root / rel
        if not pred_path.exists():
            pred_path = find_prediction_for_gt(gt_path, pred_root)

        if pred_path is None or not pred_path.exists():
            missing += 1
            print(f"missing prediction: {rel}")
            continue

        try:
            stats = compare_skyreg_frame_median_to_prediction(gt_path, pred_path, radius_m=args.radius_m)
        except Exception as exc:
            failed += 1
            print(f"failed: {rel}: {exc}")
            continue

        dist = stats["dist_m"]
        distances.append(dist)
        abs_dlat.append(stats["abs_dlat_deg"])
        abs_dlon.append(stats["abs_dlon_deg"])
        count += 1
        for threshold in less_than:
            if dist <= threshold:
                less_than[threshold] += 1

        print(
            f"{rel}: median-point-dist={dist:.3f}m "
            f"dlat={stats['signed_dlat_deg']:.8f}deg dlon={stats['signed_dlon_deg']:.8f}deg"
        )

    print("")
    print(f"evaluated: {count}")
    print(f"missing predictions: {missing}")
    print(f"failed: {failed}")
    if distances:
        print(f"mean_dist_m: {float(np.mean(distances)):.3f}")
        print(f"median_dist_m: {float(np.median(distances)):.3f}")
        print(f"p95_dist_m: {float(np.percentile(distances, 95)):.3f}")
        print(f"max_dist_m: {float(np.max(distances)):.3f}")
        print(f"mean_abs_dlat_deg: {float(np.mean(abs_dlat))}")
        print(f"mean_abs_dlon_deg: {float(np.mean(abs_dlon))}")
        for threshold, value in less_than.items():
            print(f"dist <= {threshold}m: {value}")


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compare prediction against SkyReg frame NPZ GT by reducing each per-pixel GPS map "
            "to its median lat/lon point first."
        )
    )
    parser.add_argument("--radius-m", type=float, default=MEAN_EARTH_RADIUS_M)
    parser.add_argument("--limit", type=int, default=None, help="Only evaluate the first N GT files in folder mode.")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--gt-frame-npz", type=Path, help="Single SkyReg frame-style GT NPZ.")
    mode.add_argument("--gt-root", type=Path, help="Folder of SkyReg frame-style GT NPZ files.")

    parser.add_argument("--pred-npz", type=Path, help="Single predicted lat/lon NPZ.")
    parser.add_argument("--pred-root", type=Path, help="Folder of predicted lat/lon NPZ files.")
    args = parser.parse_args()

    if args.gt_frame_npz is not None and args.pred_npz is None:
        parser.error("--gt-frame-npz requires --pred-npz")
    if args.gt_root is not None and args.pred_root is None:
        parser.error("--gt-root requires --pred-root")

    return args


def main():
    args = parse_args()
    if args.gt_frame_npz is not None:
        run_single(args)
    else:
        run_folder(args)


if __name__ == "__main__":
    main()
