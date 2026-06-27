from pathlib import Path

import numpy as np
import pymap3d as pm
from scipy.spatial.transform import Rotation as R


def load_frame_npz(path):
    path = Path(path)
    with np.load(path, allow_pickle=True) as data:
        depth = data["depth"].astype(np.float64, copy=False)
        width = int(data["width"])
        height = int(data["height"])
        fov_vertical = float(data["fov_vertical"])
        pos_ecef = data["pos_ecef"].astype(np.float64, copy=False)
        rot_euler_xyz_deg = data["rot_euler_xyz_deg"].astype(np.float64, copy=False)

    if depth.shape != (height, width):
        raise ValueError(f"Depth shape {depth.shape} does not match height/width {(height, width)}")

    return depth, width, height, fov_vertical, pos_ecef, rot_euler_xyz_deg


def intrinsics_from_vertical_fov(width, height, fov_vertical_degrees):
    fy = (height / 2.0) / np.tan(np.deg2rad(fov_vertical_degrees) / 2.0)
    fx = fy
    cx = width / 2.0
    cy = height / 2.0
    return fx, fy, cx, cy


def ecef_pointmap_to_geodetic(pointmap_ecef, valid_mask=None, deg=True, ell="wgs84_mean"):
    ellipsoid = pm.Ellipsoid.from_name(ell)
    pointmap_ecef = np.asarray(pointmap_ecef, dtype=np.float64)
    if pointmap_ecef.shape[-1] != 3:
        raise ValueError("pointmap_ecef must have shape (H, W, 3)")

    valid = np.isfinite(pointmap_ecef).all(axis=-1)
    if valid_mask is not None:
        valid &= np.asarray(valid_mask, dtype=bool)

    x = pointmap_ecef[..., 0].copy()
    y = pointmap_ecef[..., 1].copy()
    z = pointmap_ecef[..., 2].copy()
    x[~valid] = np.nan
    y[~valid] = np.nan
    z[~valid] = np.nan

    lat, lon, alt = pm.ecef2geodetic(x, y, z, ell=ellipsoid, deg=deg)
    return np.stack([lat, lon, alt], axis=-1).astype(np.float64, copy=False)


def gps_from_frame_npz(frame_npz):
    """Return an (H, W, 3) array of per-pixel [lat, lon, alt] from a frame NPZ."""
    depth, width, height, fov_vertical, pos_ecef, rot_euler_xyz_deg = load_frame_npz(frame_npz)
    fx, fy, cx, cy = intrinsics_from_vertical_fov(width, height, fov_vertical)

    u, v = np.meshgrid(np.arange(width), np.arange(height))
    z = depth.astype(np.float64, copy=False)
    x = (u.astype(np.float64) - cx) * z / fx
    y = (v.astype(np.float64) - cy) * z / fy
    points_cam = np.stack([x, y, z], axis=-1)

    cam_to_ecef = R.from_euler("XYZ", rot_euler_xyz_deg, degrees=True).as_matrix().T
    points_ecef = points_cam @ cam_to_ecef + pos_ecef
    valid_mask = np.isfinite(depth) & (depth > 0)
    return ecef_pointmap_to_geodetic(points_ecef, valid_mask=valid_mask)
