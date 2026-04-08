# reMarkable Import

[中文说明](./README.zh-CN.md)

## Overview

`reMarkable Import` uploads PDF and EPUB files to a reMarkable tablet over SSH. It can also create folders, create nested folders, and print the current folder structure as a tree.

## Features

- Upload `.pdf` and `.epub` documents to the reMarkable.
- Set a custom display name for uploaded documents.
- Upload documents into a specific parent folder by UUID.
- Create a folder at root or inside another folder.
- Create nested folders in one command, for example `Books/Math/Algebra`.
- List folders as a tree based on parent-child relationships.

## Requirements

- Python 3.8 or later
- `paramiko`
- SSH access to the reMarkable tablet

## Installation

```bash
pip install paramiko
```

## Configuration

Create a `config.json` file in the project root:

```json
{
  "host": "10.11.99.1",
  "username": "root",
  "password": "your-password",
  "xochitl_path": "/home/root/.local/share/remarkable/xochitl"
}
```

Field description:

- `host`: IP address or hostname of the reMarkable.
- `username`: SSH username.
- `password`: SSH password.
- `xochitl_path`: Path to the reMarkable `xochitl` storage directory.

## Usage

General syntax:

```bash
python upload.py [file] [options]
```

### Upload a document

```bash
python upload.py ./sample.pdf
```

This uploads the file using its filename without extension as the visible name.

### Upload with a custom display name

```bash
python upload.py ./sample.pdf --name "Linear Algebra Notes"
```

### Upload into a specific folder

```bash
python upload.py ./sample.pdf --parent 12345678-1234-1234-1234-123456789abc
```

Use `--list-folders` first if you need the folder UUID.

### List folders as a tree

```bash
python upload.py --list-folders
```

Example output:

```text
Folders on device:
(root)
├─ Books [11111111-1111-1111-1111-111111111111]
│  └─ Math [22222222-2222-2222-2222-222222222222]
└─ Notes [33333333-3333-3333-3333-333333333333]
```

### Create a folder

```bash
python upload.py --mkdir Books
```

### Create a subfolder under a specific parent

```bash
python upload.py --mkdir Math --parent 11111111-1111-1111-1111-111111111111
```

### Create nested folders in one command

```bash
python upload.py --mkdir Books/Math/Algebra
```

If a folder in the path already exists under the same parent, the script reuses it and only creates the missing levels.

## Notes

- The script restarts the `xochitl` service after uploading a document or creating folders so changes appear on the device.
- Only `.pdf` and `.epub` are supported.
- Folder selection currently uses UUIDs, not folder paths.

## Project Files

- `upload.py`: Main script
- `config.json`: Local connection configuration

