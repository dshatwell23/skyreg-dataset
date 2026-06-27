# SkyReg OneDrive Upload

Run these commands on the CRCV cluster after cloning this repository there.

Defaults baked into `upload_skyreg_to_onedrive.py`:

```text
dataset root: /home/qi940700/SkyReg
temp dir:     /home/da625117/skyreg-dataset/onedrive_upload/onedrive_upload_tmp
state dir:    /home/da625117/skyreg-dataset/onedrive_upload/onedrive_upload_state
remote root:  onedrive_eccv2026:SkyReg
```

Generate JSON unit manifests:

```bash
python3 onedrive_upload/upload_skyreg_to_onedrive.py plan
```

Upload sequentially:

```bash
python3 onedrive_upload/upload_skyreg_to_onedrive.py run
```

Refresh the plan and upload:

```bash
python3 onedrive_upload/upload_skyreg_to_onedrive.py run --plan
```

Retry failed units:

```bash
python3 onedrive_upload/upload_skyreg_to_onedrive.py run --retry-failed
```

Process one unit for debugging:

```bash
python3 onedrive_upload/upload_skyreg_to_onedrive.py run --unit landmark_scene_0001
```

Print current state:

```bash
python3 onedrive_upload/upload_skyreg_to_onedrive.py status
```

Packaging policy:

- Landmark: one tar per scene ID, containing all available Landmark modalities for that scene.
- Suburban: one tar per city/sequence, containing all available Suburban modalities for that city/sequence.
- Urban: one tar per city, modality, and frame directory.
- Helpers: `SkyReg_Lib.py` and files under `demo/` are uploaded directly without tar.

Tar files are written with paths relative to `/home/qi940700/SkyReg`, so extraction recreates the original dataset folder structure.

The script excludes `.git`, `.agents`, and `.DS_Store` from archive contents.
