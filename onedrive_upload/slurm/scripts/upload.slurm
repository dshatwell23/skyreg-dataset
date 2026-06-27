#!/bin/bash
#SBATCH --job-name=upload_skyreg
#SBATCH --output=/home/da625117/skyreg-dataset/onedrive_upload/slurm/logs/%j_upload_skyreg.out
#SBATCH --error=/home/da625117/skyreg-dataset/onedrive_upload/slurm/logs/%j_upload_skyreg.err
#SBATCH -c 16
#SBATCH --mem=160G

# Set up env
source /home/da625117/.bashrc
source /home/da625117/miniconda3/etc/profile.d/conda.sh || { echo "Failed to source conda.sh"; exit 1; }
conda activate /home/da625117/miniconda3/envs/rclone || { echo "Failed to activate conda environment"; exit 1; }

cd /home/da625117/skyreg-dataset || { echo "Failed to enter repo directory"; exit 1; }

python3 onedrive_upload/upload_skyreg_to_onedrive.py run --retry-failed
