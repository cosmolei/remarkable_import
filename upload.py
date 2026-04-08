#!/usr/bin/env python3
"""Upload PDF/EPUB files to reMarkable tablet via SSH."""

import argparse
import json
import os
import sys
import time
import uuid

import paramiko


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def connect_ssh(config):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(config["host"], username=config["username"], password=config["password"])
    return ssh


def get_file_type(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return "pdf"
    elif ext == ".epub":
        return "epub"
    else:
        print(f"Error: unsupported file type '{ext}'. Only .pdf and .epub are supported.")
        sys.exit(1)


def get_visible_name(filepath):
    """Extract display name from filename (without extension)."""
    return os.path.splitext(os.path.basename(filepath))[0]


def list_folders(ssh, xochitl_path):
    """List all folders on the device."""
    cmd = f'grep -rl "CollectionType" {xochitl_path}/*.metadata 2>/dev/null'
    _, stdout, _ = ssh.exec_command(cmd)
    output = stdout.read().decode()

    folders = [{"name": "(root)", "uuid": "", "parent": None}]
    for line in output.strip().split("\n"):
        if not line:
            continue
        metadata_path = line.strip()
        _, stdout2, _ = ssh.exec_command(f"cat '{metadata_path}'")
        try:
            meta = json.loads(stdout2.read().decode())
            folder_uuid = os.path.basename(metadata_path).replace(".metadata", "")
            folders.append({
                "name": meta.get("visibleName", "???"),
                "uuid": folder_uuid,
                "parent": meta.get("parent", ""),
            })
        except json.JSONDecodeError:
            continue

    return folders


def print_folder_tree(folders):
    """Print folders as a tree using parent-child relationships."""
    children_by_parent = {}
    folder_by_uuid = {}

    for folder in folders:
        folder_by_uuid[folder["uuid"]] = folder
        children_by_parent.setdefault(folder["parent"], []).append(folder)

    def sort_key(folder):
        return (folder["name"].lower(), folder["uuid"])

    def walk(parent_uuid, prefix=""):
        children = sorted(children_by_parent.get(parent_uuid, []), key=sort_key)
        for index, folder in enumerate(children):
            is_last = index == len(children) - 1
            branch = "└─ " if is_last else "├─ "
            child_prefix = prefix + ("   " if is_last else "│  ")
            print(f"{prefix}{branch}{folder['name']} [{folder['uuid']}]")
            walk(folder["uuid"], child_prefix)

    print("(root)")
    walk("")

    orphan_parents = sorted(
        parent_uuid for parent_uuid in children_by_parent
        if parent_uuid not in ("", None) and parent_uuid not in folder_by_uuid
    )
    if orphan_parents:
        print("\nOrphan folders:")
        for parent_uuid in orphan_parents:
            walk(parent_uuid)


def build_metadata(visible_name, parent="", file_type="pdf"):
    """Build the .metadata JSON content."""
    now_ms = str(int(time.time() * 1000))
    return json.dumps({
        "createdTime": now_ms,
        "lastModified": now_ms,
        "lastOpened": "0",
        "lastOpenedPage": 0,
        "new": True,
        "parent": parent,
        "pinned": False,
        "source": "",
        "type": "DocumentType",
        "visibleName": visible_name
    }, indent=4)


def build_folder_metadata(visible_name, parent=""):
    """Build the .metadata JSON content for a folder."""
    now_ms = str(int(time.time() * 1000))
    return json.dumps({
        "createdTime": now_ms,
        "lastModified": now_ms,
        "metadatamodified": False,
        "modified": False,
        "parent": parent,
        "pinned": False,
        "synced": False,
        "type": "CollectionType",
        "version": 0,
        "visibleName": visible_name
    }, indent=4)


def build_content(file_type):
    """Build a minimal .content JSON. The device populates pages on first open."""
    return json.dumps({
        "cPages": {
            "original": {
                "timestamp": "1:0",
                "value": -1
            },
            "pages": []
        },
        "coverPageNumber": 0,
        "documentMetadata": {},
        "extraMetadata": {},
        "fileType": file_type,
        "fontName": "",
        "formatVersion": 2,
        "lineHeight": -1,
        "margins": 100,
        "orientation": "portrait",
        "pageCount": 0,
        "pageTags": [],
        "sizeInBytes": "0",
        "textAlignment": "left",
        "textScale": 1
    }, indent=4)


def build_folder_content():
    """Build a minimal .content JSON for a folder."""
    return json.dumps([], indent=4)


def create_folder(ssh, sftp, xochitl_path, visible_name, parent_uuid=""):
    """Create a single folder on the reMarkable and return its UUID."""
    folder_uuid = str(uuid.uuid4())
    remote_meta = f"{xochitl_path}/{folder_uuid}.metadata"
    remote_content = f"{xochitl_path}/{folder_uuid}.content"
    remote_pagedata = f"{xochitl_path}/{folder_uuid}.pagedata"

    with sftp.open(remote_meta, "w") as f:
        f.write(build_folder_metadata(visible_name, parent_uuid))

    with sftp.open(remote_content, "w") as f:
        f.write(build_folder_content())

    with sftp.open(remote_pagedata, "w") as f:
        f.write("\n")

    print(f"Created folder '{visible_name}'")
    print(f"UUID:    {folder_uuid}")
    print(f"Parent:  {parent_uuid or '(root)'}")
    print()
    return folder_uuid


def ensure_folder_path(ssh, sftp, xochitl_path, folder_path, parent_uuid=""):
    """Create a folder path like 'A/B/C', reusing existing folders when possible."""
    folders = list_folders(ssh, xochitl_path)
    current_parent = parent_uuid

    for raw_part in folder_path.split("/"):
        part = raw_part.strip()
        if not part:
            continue

        parent_for_part = current_parent
        existing = next(
            (folder for folder in folders if folder["name"] == part and folder["parent"] == parent_for_part),
            None,
        )
        if existing:
            current_parent = existing["uuid"]
            print(f"Using existing folder '{part}'")
            print(f"UUID:    {current_parent}")
            print()
            continue

        current_parent = create_folder(ssh, sftp, xochitl_path, part, parent_for_part)
        folders.append({"name": part, "uuid": current_parent, "parent": parent_for_part})

    return current_parent


def upload_file(filepath, parent_uuid="", visible_name=None):
    """Upload a PDF or EPUB to the reMarkable."""
    config = load_config()
    file_type = get_file_type(filepath)
    if visible_name is None:
        visible_name = get_visible_name(filepath)

    doc_uuid = str(uuid.uuid4())
    xochitl = config["xochitl_path"]

    print(f"File:    {os.path.basename(filepath)}")
    print(f"Name:    {visible_name}")
    print(f"Type:    {file_type}")
    print(f"UUID:    {doc_uuid}")
    print(f"Parent:  {parent_uuid or '(root)'}")
    print()

    ssh = connect_ssh(config)
    sftp = ssh.open_sftp()

    try:
        # 1. Upload the document file
        remote_doc = f"{xochitl}/{doc_uuid}.{file_type}"
        print(f"Uploading {file_type}...")
        sftp.put(filepath, remote_doc)

        # 2. Write .metadata
        metadata = build_metadata(visible_name, parent_uuid, file_type)
        remote_meta = f"{xochitl}/{doc_uuid}.metadata"
        with sftp.open(remote_meta, "w") as f:
            f.write(metadata)
        print("Created .metadata")

        # 3. Write .content
        content = build_content(file_type)
        remote_content = f"{xochitl}/{doc_uuid}.content"
        with sftp.open(remote_content, "w") as f:
            f.write(content)
        print("Created .content")

        # 4. Create empty directory for annotations
        remote_dir = f"{xochitl}/{doc_uuid}"
        try:
            sftp.mkdir(remote_dir)
        except IOError:
            pass
        print("Created directory")

        # 5. Create empty .pagedata
        remote_pagedata = f"{xochitl}/{doc_uuid}.pagedata"
        with sftp.open(remote_pagedata, "w") as f:
            f.write("")
        print("Created .pagedata")

        # 6. Restart xochitl so the device picks up the new file
        print("\nRestarting xochitl service...")
        _, stdout, stderr = ssh.exec_command("systemctl restart xochitl")
        stdout.channel.recv_exit_status()
        print("Done! The document should appear on your reMarkable.")

    finally:
        sftp.close()
        ssh.close()


def create_folder_path(folder_path, parent_uuid=""):
    """Create one or more folders on the reMarkable."""
    config = load_config()
    xochitl = config["xochitl_path"]
    ssh = connect_ssh(config)
    sftp = ssh.open_sftp()

    try:
        final_uuid = ensure_folder_path(ssh, sftp, xochitl, folder_path, parent_uuid)

        print("Restarting xochitl service...")
        _, stdout, _ = ssh.exec_command("systemctl restart xochitl")
        stdout.channel.recv_exit_status()
        print("Done! The folder should appear on your reMarkable.")
        print(f"Final folder UUID: {final_uuid}")
    finally:
        sftp.close()
        ssh.close()


def main():
    parser = argparse.ArgumentParser(description="Upload PDF/EPUB to reMarkable tablet")
    parser.add_argument("file", nargs="?", help="Path to PDF or EPUB file")
    parser.add_argument("-n", "--name", help="Display name (default: filename without extension)")
    parser.add_argument("-p", "--parent", help="Parent folder UUID (use --list-folders to see options)")
    parser.add_argument("--mkdir", help="Create a folder. Use '/' to create nested folders, e.g. Books/Math")
    parser.add_argument("--list-folders", action="store_true", help="List folders on the device and exit")

    args = parser.parse_args()

    if args.list_folders:
        config = load_config()
        ssh = connect_ssh(config)
        folders = list_folders(ssh, config["xochitl_path"])
        ssh.close()
        print("Folders on device:")
        print_folder_tree([f for f in folders if f["uuid"]])
        return

    if args.mkdir:
        if args.file:
            print("Error: do not pass a file when using --mkdir")
            sys.exit(1)
        create_folder_path(args.mkdir, parent_uuid=args.parent or "")
        return

    if not args.file:
        parser.print_help()
        sys.exit(1)

    if not os.path.isfile(args.file):
        print(f"Error: file not found: {args.file}")
        sys.exit(1)

    upload_file(args.file, parent_uuid=args.parent or "", visible_name=args.name)


if __name__ == "__main__":
    main()
