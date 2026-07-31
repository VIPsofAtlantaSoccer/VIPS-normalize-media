# VIPS-normalize-media

Normalize, convert, resize, rename, and preserve metadata for image and video files.

## Features

- Scans one or more configured directories recursively.
- Converts supported image formats to WebP.
- Extracts embedded JPEG images from Nikon NEF files.
- Resizes images while preserving their aspect ratio.
- Preserves image metadata and file timestamps.
- Converts supported video formats to MP4.
- Renames files using available metadata dates.
- Removes configured unwanted file types.
- Processes files using configurable thread counts.
- Sends deleted files to the Windows Recycle Bin.

The script scans each path listed in `config.toml` under `[Directories]`, categorizes the files, and processes them using the configured settings.

>**Important**: The script modifies, renames, converts, and removes files. Test it against a temporary directory and files before using it on your primary media library.

## Requirements

- Python 3.11 or newer
- FFmpeg
- ExifTool
- ImageMagick with HEIC support

Python packages are listed in `requirements.txt`.

## Installation

Clone the repository and create a virtual environment:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuration
Copy the example configuration file, `config.example.toml` to `config.toml`


Update config.toml with the paths and settings for your system.

config.toml contains your local information and **should not** be committed to a repository. 

## Usage

```
# Activate the virtual environment:
.venv\Scripts\activate

# Execute the script
python VIPs_Normalize_Media.py
```