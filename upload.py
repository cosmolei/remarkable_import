#!/usr/bin/env python3
"""CLI for reMarkable logical file operations."""

from __future__ import annotations

import argparse
import os
import sys

from remarkable import RemarkableClient, RemarkableError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage reMarkable files and folders over SSH")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List logical folders and documents")
    list_parser.add_argument("--folders-only", action="store_true", help="Show folders only")
    list_parser.add_argument("--show-uuid", action="store_true", help="Include UUIDs in list output")

    mkdir_parser = subparsers.add_parser("mkdir", help="Create a folder or nested folder path")
    mkdir_parser.add_argument("path", help="Folder path to create, e.g. Books/Math")
    mkdir_parser.add_argument(
        "--parent",
        default="",
        help="Parent folder UUID or logical path. Default: root",
    )

    upload_parser = subparsers.add_parser("upload", help="Upload a PDF or EPUB")
    upload_parser.add_argument("file", help="Local file to upload")
    upload_parser.add_argument("-n", "--name", help="Visible name on the device")
    upload_parser.add_argument(
        "--parent",
        default="",
        help="Destination folder UUID or logical path. Default: root",
    )

    download_parser = subparsers.add_parser("download", help="Download a document")
    download_parser.add_argument("target", help="Document UUID or logical path to download")
    download_parser.add_argument("output", nargs="?", help="Local file path or directory")

    delete_parser = subparsers.add_parser("delete", help="Delete a document or folder")
    delete_parser.add_argument("target", help="Item UUID or logical path to delete")
    delete_parser.add_argument("--recursive", action="store_true", help="Delete folders recursively")

    move_parser = subparsers.add_parser("move", help="Move an item into another folder")
    move_parser.add_argument("target", help="Item UUID or logical path to move")
    move_parser.add_argument("destination", help="Destination folder UUID or logical path")

    return parser


def handle_list(client: RemarkableClient, args: argparse.Namespace) -> None:
    for line in client.format_tree(show_uuid=args.show_uuid, folders_only=args.folders_only):
        print(line)


def handle_mkdir(client: RemarkableClient, args: argparse.Namespace) -> None:
    item = client.create_folder_path(args.path, parent_ref=args.parent)
    client.restart_xochitl()
    print(f"Created folder: {item.visible_name}/")
    print(f"Path input: {args.path}")
    print(f"UUID: {item.uuid}")


def handle_upload(client: RemarkableClient, args: argparse.Namespace) -> None:
    item = client.upload_file(args.file, parent_ref=args.parent, visible_name=args.name)
    client.restart_xochitl()
    print(f"Uploaded: {os.path.basename(args.file)}")
    print(f"Visible name: {item.visible_name}")
    print(f"UUID: {item.uuid}")
    print(f"Type: {item.file_type}")


def handle_download(client: RemarkableClient, args: argparse.Namespace) -> None:
    destination = client.download_file(args.target, output_path=args.output)
    print(f"Downloaded to: {destination}")


def handle_delete(client: RemarkableClient, args: argparse.Namespace) -> None:
    deleted = client.delete_item(args.target, recursive=args.recursive)
    client.restart_xochitl()
    print(f"Deleted {len(deleted)} item(s):")
    for item in deleted:
        suffix = "/" if item.is_folder else (f" ({item.file_type})" if item.file_type else "")
        print(f"  {item.visible_name}{suffix} [{item.uuid}]")


def handle_move(client: RemarkableClient, args: argparse.Namespace) -> None:
    item = client.move_item(args.target, args.destination)
    client.restart_xochitl()
    print(f"Moved: {item.visible_name}")
    print(f"UUID: {item.uuid}")
    print(f"New parent: {item.parent_uuid or '(root)'}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        with RemarkableClient(load_config()) as client:
            if args.command == "list":
                handle_list(client, args)
            elif args.command == "mkdir":
                handle_mkdir(client, args)
            elif args.command == "upload":
                handle_upload(client, args)
            elif args.command == "download":
                handle_download(client, args)
            elif args.command == "delete":
                handle_delete(client, args)
            elif args.command == "move":
                handle_move(client, args)
            else:
                parser.error(f"Unknown command: {args.command}")
        return 0
    except RemarkableError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
