# reMarkable Import

[中文说明](./README.zh-CN.md)

## Overview

`reMarkable Import` manages documents and folders on a reMarkable tablet over SSH. The project now exposes a logical file model instead of raw metadata files, which makes it a better base for a future web UI.

## Features

- List the logical tree of folders and documents.
- Create folders or nested folder paths.
- Upload `.pdf` and `.epub` documents.
- Download documents.
- Delete documents.
- Delete folders, including recursive delete for non-empty folders.
- Move documents or folders into another folder.
- Resolve targets by UUID or logical path.

## Requirements

- Python 3.8 or later
- `paramiko`
- SSH access to the reMarkable tablet

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy `config.example.json` to `config.json`, then fill in your own connection details:

```json
{
  "host": "10.11.99.1",
  "username": "root",
  "password": "your-password",
  "xochitl_path": "/home/root/.local/share/remarkable/xochitl"
}
```

Field description:

- `host`: IP address or hostname of the reMarkable
- `username`: SSH username
- `password`: SSH password
- `xochitl_path`: Path to the reMarkable `xochitl` storage directory

`config.json` is ignored by Git so your local password is not committed.

## Usage

General syntax:

```bash
python upload.py <command> [options]
```

### List the logical tree

```bash
python upload.py list
```

Show folders only:

```bash
python upload.py list --folders-only
```

Show UUIDs together with logical names:

```bash
python upload.py list --show-uuid
```

Example output:

```text
(root)
├─ Books/
│  ├─ Math/
│  │  └─ Linear Algebra (pdf)
│  └─ Physics (epub)
└─ Notes/
```

### Create folders

Create a folder at root:

```bash
python upload.py mkdir Books
```

Create nested folders in one command:

```bash
python upload.py mkdir Books/Math/Algebra
```

Create under an existing parent by UUID or logical path:

```bash
python upload.py mkdir Algebra --parent Books/Math
```

### Upload a document

Upload to root:

```bash
python upload.py upload ./sample.pdf
```

Upload with a custom visible name:

```bash
python upload.py upload ./sample.pdf --name "Linear Algebra Notes"
```

Upload into a folder by logical path:

```bash
python upload.py upload ./sample.pdf --parent Books/Math
```

Upload into a folder by UUID:

```bash
python upload.py upload ./sample.pdf --parent 12345678-1234-1234-1234-123456789abc
```

### Download a document

Download using a logical path:

```bash
python upload.py download Books/Math/"Linear Algebra Notes"
```

Download to a specific local file path:

```bash
python upload.py download Books/Physics ./downloads/physics.epub
```

### Delete a document or folder

Delete a document:

```bash
python upload.py delete Books/Math/"Linear Algebra Notes"
```

Delete an empty folder:

```bash
python upload.py delete Books/Math/Algebra
```

Delete a non-empty folder recursively:

```bash
python upload.py delete Books --recursive
```

### Move a document or folder

Move a document into another folder:

```bash
python upload.py move Books/Physics Notes
```

Move a folder into another folder:

```bash
python upload.py move Books/Math Archive
```

## Web UI

Start the local web interface:

```bash
python webapp.py
```

Then open `http://127.0.0.1:8000`.

The web UI currently supports:

- Single-directory browsing, starting at root
- Enter folder on click and go back to parent
- Batch upload into the current folder by drag-and-drop or file picker
- In-page folder creation in the current folder
- Rename folders or documents
- Batch delete using row checkboxes
- Download, move, and rename based on the selected item
- Upload progress feedback
- English and Chinese UI switching

You can also choose a custom bind address and port:

```bash
python webapp.py --host 127.0.0.1 --port 8765
```

## Notes

- The CLI works on the logical tree reconstructed from item metadata, not on raw `.metadata` filenames.
- By default, `list` hides UUIDs so the output stays focused on the logical structure.
- After write operations, the script restarts the `xochitl` service so changes appear on the device.
- Before restarting `xochitl`, the client resets the unit's failed state to reduce the chance of hitting the device's systemd start limit during repeated operations.
- Only `.pdf` and `.epub` uploads are supported.
- Ambiguous logical paths are rejected instead of guessing.

## Project Structure

- `upload.py`: CLI entry point
- `remarkable/client.py`: Core logical operations for list, upload, download, move, delete, and mkdir
- `webapp.py`: FastAPI web server
- `templates/` and `static/`: Web UI templates and assets
- `requirements.txt`: Python dependencies
- `config.example.json`: Config template
- `config.json`: Local config, ignored by Git
