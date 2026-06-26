# SkyReg Dataset

## Description

SkyReg is a large-scale drone–satellite geo-registration dataset designed for dense, pixel-wise geodetic alignment. It consists of SkyReg-130k for training and SkyReg-Bench for evaluation, covering Urban, Landmarks, and Suburban scenes with diverse locations, camera configurations, viewpoint changes, and scene layouts. Each sample pairs a perspective drone image with a geodetically accurate satellite reference and includes dense annotations such as per-pixel latitude–longitude coordinates, metric depth, camera intrinsics, and 6-DoF camera poses. Urban scenes use orthorectified satellite tiles with LiDAR-derived depth, while Landmark and Suburban scenes use perspective satellite/drone views with SfM-derived depth.

## Dataset Structure

The dataset is organized into three main subsets: `SkyReg-Urban`, `SkyReg-Landmark`, and `SkyReg-Suburban`. `SkyReg-Urban` contains city-level data for Chicago, San Francisco, and Seattle. `SkyReg-Landmark` and `SkyReg-Suburban` contain drone query images, satellite reference images, and their corresponding annotation files. Drone images are stored in `GT_Images` / `GT_Image`, with annotations in `GT_NPZ`; satellite images are stored in `GT_Sat_Images`, with annotations in `GT_Sat_NPZ`. The `.npz` files contain the geometric and geodetic metadata needed for pixel-wise geo-registration. The root directory also includes `SkyReg_Lib.py` for dataset loading utilities and a `demo/` folder with scripts for reading annotations, extracting GPS information, and visualizing pixel-wise GPS coordinates.

## Download Instructions

The SkyReg dataset is hosted on OneDrive and can be accessed through the link below. Users may download individual files from the browser or use the OneDrive “Download” option to retrieve the full dataset archive. Due to the dataset size, we recommend using a stable internet connection and ensuring that sufficient local storage is available before downloading.

Dataset URL: [insert OneDrive link here]

