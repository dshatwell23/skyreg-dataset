# Frame NPZ GPS Demo

This folder contains small demo scripts for reconstructing per-pixel GPS from a generated frame NPZ.
The reusable library lives outside this folder at `../SkyReg_Lib.py`.

## Library

```python
from SkyReg_Lib import gps_from_frame_npz

gps = gps_from_frame_npz("/path/to/frame.npz")
print(gps.shape)  # (H, W, 3)
```


The output channels are:

```text
gps[..., 0] = latitude
gps[..., 1] = longitude
gps[..., 2] = altitude
```

## Save GPS Map

```bash
python save_gps_from_frame_npz.py /path/to/frame.npz --output /path/to/gps.npy --overwrite
```

## Visualize And Click Pixels

```bash
python visualize_frame_npz_gps_pixel.py /path/to/frame.npz
```

Optionally display an image instead of the depth colormap:

```bash
python visualize_frame_npz_gps_pixel.py /path/to/frame.npz --image /path/to/image.jpg
```

Or use the simpler image-plus-NPZ demo:

```bash
python visualize_image_npz_gps_pixel.py /path/to/image.jpg /path/to/frame.npz
```
