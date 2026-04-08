"""Core reMarkable client operations backed by SSH/SFTP."""

from __future__ import annotations

import json
import os
import posixpath
import shlex
import time
import uuid
from dataclasses import dataclass
from typing import Iterable

import paramiko


class RemarkableError(RuntimeError):
    """Raised when a reMarkable operation fails."""


@dataclass(frozen=True)
class RemarkableItem:
    """Logical item stored in xochitl."""

    uuid: str
    visible_name: str
    parent_uuid: str
    item_type: str
    file_type: str = ""
    created_time: int = 0
    last_modified: int = 0
    size_bytes: int | None = None

    @property
    def is_folder(self) -> bool:
        return self.item_type == "CollectionType"

    @property
    def is_document(self) -> bool:
        return self.item_type == "DocumentType"


@dataclass(frozen=True)
class DocumentBlob:
    """Downloaded document payload."""

    filename: str
    media_type: str
    content: bytes


def load_config(config_path: str | None = None) -> dict:
    """Load local connection config."""
    if config_path is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(root, "config.json")

    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class RemarkableClient:
    """High-level logical operations on reMarkable storage."""

    def __init__(self, config: dict):
        self.config = config
        self.xochitl_path = config["xochitl_path"]
        self.ssh: paramiko.SSHClient | None = None
        self.sftp: paramiko.SFTPClient | None = None

    def __enter__(self) -> "RemarkableClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        if self.ssh is not None:
            return
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            self.config["host"],
            username=self.config["username"],
            password=self.config["password"],
        )
        self.ssh = ssh
        self.sftp = ssh.open_sftp()

    def close(self) -> None:
        if self.sftp is not None:
            self.sftp.close()
            self.sftp = None
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None

    def exec_command(self, command: str) -> tuple[int, str, str]:
        """Run a shell command on the device."""
        if self.ssh is None:
            raise RemarkableError("SSH connection is not open")
        _, stdout, stderr = self.ssh.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, stdout.read().decode(), stderr.read().decode()

    def restart_xochitl(self) -> None:
        """Restart xochitl so the device reflects filesystem changes."""
        # reMarkable ships xochitl with a strict systemd start limit. After a
        # few restarts in a short window, plain "restart" can hit
        # start-limit-hit and trigger the device emergency target, which in
        # turn reboots the whole tablet. Reset the unit state first so our own
        # maintenance restarts do not accumulate against that counter.
        self.exec_command("systemctl reset-failed xochitl.service")
        exit_code, stdout, stderr = self.exec_command("systemctl restart xochitl.service")
        if exit_code == 0:
            return

        # Some device-side restarts can transiently drop the command channel and
        # produce exit=-1 even though xochitl comes back successfully.
        time.sleep(1.0)
        status_code, status_stdout, status_stderr = self.exec_command("systemctl is-active xochitl.service")
        if status_code == 0 and status_stdout.strip() == "active":
            return

        details = " | ".join(
            part for part in [
                f"exit={exit_code}",
                f"stdout={stdout.strip()}" if stdout.strip() else "",
                f"stderr={stderr.strip()}" if stderr.strip() else "",
                f"is-active-exit={status_code}",
                f"is-active={status_stdout.strip()}" if status_stdout.strip() else "",
                f"is-active-stderr={status_stderr.strip()}" if status_stderr.strip() else "",
            ]
            if part
        )
        raise RemarkableError(f"Failed to restart xochitl: {details}")

    def list_items(self) -> list[RemarkableItem]:
        """Load the logical item graph from xochitl metadata files."""
        metadata_paths = self._list_metadata_paths()
        items: list[RemarkableItem] = []
        for metadata_path in metadata_paths:
            try:
                metadata = self._read_json(metadata_path)
            except (OSError, json.JSONDecodeError):
                continue

            item_type = metadata.get("type")
            if item_type not in ("CollectionType", "DocumentType"):
                continue

            item_uuid = posixpath.basename(metadata_path).replace(".metadata", "")
            parent_uuid = metadata.get("parent") or ""
            visible_name = metadata.get("visibleName") or item_uuid
            created_time = self._safe_int(metadata.get("createdTime"))
            last_modified = self._safe_int(metadata.get("lastModified"))
            file_type = ""
            size_bytes = None
            if item_type == "DocumentType":
                try:
                    content = self._read_json(self._remote_path(f"{item_uuid}.content"))
                    file_type = content.get("fileType") or ""
                except (OSError, json.JSONDecodeError):
                    file_type = ""
                if file_type:
                    try:
                        size_bytes = self.sftp.stat(self._remote_path(f"{item_uuid}.{file_type}")).st_size if self.sftp else None
                    except OSError:
                        size_bytes = None

            items.append(
                RemarkableItem(
                    uuid=item_uuid,
                    visible_name=visible_name,
                    parent_uuid=parent_uuid,
                    item_type=item_type,
                    file_type=file_type,
                    created_time=created_time,
                    last_modified=last_modified,
                    size_bytes=size_bytes,
                )
            )

        return items

    def format_tree(self, show_uuid: bool = False, folders_only: bool = False) -> list[str]:
        """Render the logical tree for CLI or future web/API use."""
        items = self.list_items()
        children_by_parent = self._children_map(items, folders_only=folders_only)
        item_by_uuid = {item.uuid: item for item in items}
        lines = ["(root)"]

        def sort_key(item: RemarkableItem) -> tuple[int, str, str]:
            return (0 if item.is_folder else 1, item.visible_name.lower(), item.uuid)

        def item_label(item: RemarkableItem) -> str:
            suffix = "/" if item.is_folder else (f" ({item.file_type})" if item.file_type else "")
            uuid_part = f" [{item.uuid}]" if show_uuid else ""
            return f"{item.visible_name}{suffix}{uuid_part}"

        def walk(parent_uuid: str, prefix: str = "") -> None:
            children = sorted(children_by_parent.get(parent_uuid, []), key=sort_key)
            for index, child in enumerate(children):
                is_last = index == len(children) - 1
                branch = "└─ " if is_last else "├─ "
                child_prefix = prefix + ("   " if is_last else "│  ")
                lines.append(f"{prefix}{branch}{item_label(child)}")
                if child.is_folder:
                    walk(child.uuid, child_prefix)

        walk("")

        orphan_roots = sorted(
            parent_uuid for parent_uuid in children_by_parent
            if parent_uuid and parent_uuid not in item_by_uuid
        )
        if orphan_roots:
            lines.append("")
            lines.append("Orphan items:")
            for orphan_parent_uuid in orphan_roots:
                walk(orphan_parent_uuid)

        return lines

    def logical_tree(self, folders_only: bool = False) -> dict:
        """Return a structured logical tree for APIs and UIs."""
        items = self.list_items()
        children_by_parent = self._children_map(items, folders_only=folders_only)

        def sort_key(item: RemarkableItem) -> tuple[int, str, str]:
            return (0 if item.is_folder else 1, item.visible_name.lower(), item.uuid)

        def build_node(item: RemarkableItem) -> dict:
            node = {
                "uuid": item.uuid,
                "name": item.visible_name,
                "parent_uuid": item.parent_uuid,
                "type": "folder" if item.is_folder else "document",
                "path": self._build_path(item, items),
                "created_time": item.created_time,
                "last_modified": item.last_modified,
                "size_bytes": item.size_bytes,
            }
            if item.is_document:
                node["file_type"] = item.file_type
            if item.is_folder:
                node["children"] = [
                    build_node(child)
                    for child in sorted(children_by_parent.get(item.uuid, []), key=sort_key)
                ]
            return node

        roots = [
            build_node(item)
            for item in sorted(children_by_parent.get("", []), key=sort_key)
        ]
        return {"name": "(root)", "path": "/", "type": "root", "children": roots}

    def create_folder_path(self, folder_path: str, parent_ref: str = "") -> RemarkableItem:
        """Create a nested folder path, reusing existing folders."""
        parts = [part.strip() for part in folder_path.split("/") if part.strip()]
        if not parts:
            raise RemarkableError("Folder path is empty")

        items = self.list_items()
        current_parent_uuid = self._resolve_folder_ref(parent_ref, items)
        current_item: RemarkableItem | None = None

        for part in parts:
            sibling = self._find_child(items, current_parent_uuid, part, folders_only=True)
            if sibling is not None:
                current_parent_uuid = sibling.uuid
                current_item = sibling
                continue

            self._ensure_no_conflict(items, current_parent_uuid, part)
            current_item = self._create_folder(part, current_parent_uuid)
            items.append(current_item)
            current_parent_uuid = current_item.uuid

        return current_item

    def upload_file(self, local_path: str, parent_ref: str = "", visible_name: str | None = None) -> RemarkableItem:
        """Upload a document into a logical folder."""
        if self.sftp is None:
            raise RemarkableError("SFTP connection is not open")
        if not os.path.isfile(local_path):
            raise RemarkableError(f"File not found: {local_path}")

        file_type = self._file_type_for_path(local_path)
        items = self.list_items()
        parent_uuid = self._resolve_folder_ref(parent_ref, items)
        display_name = visible_name or os.path.splitext(os.path.basename(local_path))[0]
        self._ensure_no_conflict(items, parent_uuid, display_name)

        doc_uuid = str(uuid.uuid4())
        self.sftp.put(local_path, self._remote_path(f"{doc_uuid}.{file_type}"))
        self._write_text(self._remote_path(f"{doc_uuid}.metadata"), self._build_document_metadata(display_name, parent_uuid))
        self._write_text(self._remote_path(f"{doc_uuid}.content"), self._build_document_content(file_type))
        self._mkdir_if_missing(self._remote_path(doc_uuid))
        self._write_text(self._remote_path(f"{doc_uuid}.pagedata"), "")

        return RemarkableItem(
            uuid=doc_uuid,
            visible_name=display_name,
            parent_uuid=parent_uuid,
            item_type="DocumentType",
            file_type=file_type,
            created_time=int(time.time() * 1000),
            last_modified=int(time.time() * 1000),
            size_bytes=os.path.getsize(local_path),
        )

    def download_file(self, item_ref: str, output_path: str | None = None) -> str:
        """Download a document to a local path."""
        if self.sftp is None:
            raise RemarkableError("SFTP connection is not open")

        items = self.list_items()
        item = self._resolve_item_ref(item_ref, items)
        if not item.is_document:
            raise RemarkableError("Only documents can be downloaded.")

        extension = item.file_type or "bin"
        filename = f"{item.visible_name}.{extension}"
        destination = output_path or filename
        if os.path.isdir(destination):
            destination = os.path.join(destination, filename)

        remote_doc = self._remote_path(f"{item.uuid}.{extension}")
        self.sftp.get(remote_doc, destination)
        return destination

    def read_document(self, item_ref: str) -> DocumentBlob:
        """Read a document for HTTP download responses."""
        if self.sftp is None:
            raise RemarkableError("SFTP connection is not open")

        items = self.list_items()
        item = self._resolve_item_ref(item_ref, items)
        if not item.is_document:
            raise RemarkableError("Only documents can be downloaded.")

        extension = item.file_type or "bin"
        remote_doc = self._remote_path(f"{item.uuid}.{extension}")
        with self.sftp.open(remote_doc, "rb") as handle:
            content = handle.read()
        media_type = {
            "pdf": "application/pdf",
            "epub": "application/epub+zip",
        }.get(extension, "application/octet-stream")
        return DocumentBlob(
            filename=f"{item.visible_name}.{extension}",
            media_type=media_type,
            content=content,
        )

    def delete_item(self, item_ref: str, recursive: bool = False) -> list[RemarkableItem]:
        """Delete a document or folder by logical path or UUID."""
        items = self.list_items()
        item = self._resolve_item_ref(item_ref, items)
        descendants = self._descendants(item.uuid, items)
        if item.is_folder and descendants and not recursive:
            raise RemarkableError("Folder is not empty. Use --recursive to delete it.")

        delete_order = sorted(descendants, key=lambda descendant: self._depth(descendant, items), reverse=True)
        delete_order.append(item)
        deleted: list[RemarkableItem] = []
        for target in delete_order:
            self._delete_item_artifacts(target.uuid)
            deleted.append(target)
        return deleted

    def move_item(self, item_ref: str, destination_ref: str) -> RemarkableItem:
        """Move an item into a different folder."""
        items = self.list_items()
        item = self._resolve_item_ref(item_ref, items)
        destination_uuid = self._resolve_folder_ref(destination_ref, items)

        if item.uuid == destination_uuid:
            raise RemarkableError("Cannot move an item into itself.")
        if item.is_folder and self._is_descendant(destination_uuid, item.uuid, items):
            raise RemarkableError("Cannot move a folder into its own descendant.")
        if item.parent_uuid == destination_uuid:
            return item

        self._ensure_no_conflict(items, destination_uuid, item.visible_name, ignore_uuid=item.uuid)
        metadata = self._read_json(self._remote_path(f"{item.uuid}.metadata"))
        metadata["parent"] = destination_uuid
        metadata["lastModified"] = str(int(time.time() * 1000))
        self._write_text(self._remote_path(f"{item.uuid}.metadata"), json.dumps(metadata, indent=4))

        return RemarkableItem(
            uuid=item.uuid,
            visible_name=item.visible_name,
            parent_uuid=destination_uuid,
            item_type=item.item_type,
            file_type=item.file_type,
            created_time=item.created_time,
            last_modified=int(time.time() * 1000),
            size_bytes=item.size_bytes,
        )

    def rename_item(self, item_ref: str, new_name: str) -> RemarkableItem:
        """Rename a document or folder."""
        normalized_name = new_name.strip()
        if not normalized_name:
            raise RemarkableError("New name cannot be empty.")
        if "/" in normalized_name:
            raise RemarkableError("New name cannot contain '/'.")

        items = self.list_items()
        item = self._resolve_item_ref(item_ref, items)
        if item.visible_name == normalized_name:
            return item

        self._ensure_no_conflict(items, item.parent_uuid, normalized_name, ignore_uuid=item.uuid)
        metadata = self._read_json(self._remote_path(f"{item.uuid}.metadata"))
        metadata["visibleName"] = normalized_name
        metadata["lastModified"] = str(int(time.time() * 1000))
        self._write_text(self._remote_path(f"{item.uuid}.metadata"), json.dumps(metadata, indent=4))

        return RemarkableItem(
            uuid=item.uuid,
            visible_name=normalized_name,
            parent_uuid=item.parent_uuid,
            item_type=item.item_type,
            file_type=item.file_type,
            created_time=item.created_time,
            last_modified=int(time.time() * 1000),
            size_bytes=item.size_bytes,
        )

    def _remote_path(self, name: str) -> str:
        return posixpath.join(self.xochitl_path, name)

    def _list_metadata_paths(self) -> list[str]:
        quoted = shlex.quote(self.xochitl_path)
        exit_code, stdout, stderr = self.exec_command(
            f"find {quoted} -maxdepth 1 -type f -name '*.metadata' | sort"
        )
        if exit_code != 0:
            raise RemarkableError(f"Failed to list metadata files: {stderr.strip()}")
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def _read_json(self, remote_path: str) -> dict:
        if self.sftp is None:
            raise RemarkableError("SFTP connection is not open")
        with self.sftp.open(remote_path, "r") as handle:
            return json.loads(handle.read().decode())

    def _write_text(self, remote_path: str, text: str) -> None:
        if self.sftp is None:
            raise RemarkableError("SFTP connection is not open")
        with self.sftp.open(remote_path, "w") as handle:
            handle.write(text)

    def _mkdir_if_missing(self, remote_path: str) -> None:
        if self.sftp is None:
            raise RemarkableError("SFTP connection is not open")
        try:
            self.sftp.mkdir(remote_path)
        except OSError:
            pass

    def _create_folder(self, visible_name: str, parent_uuid: str) -> RemarkableItem:
        folder_uuid = str(uuid.uuid4())
        self._write_text(
            self._remote_path(f"{folder_uuid}.metadata"),
            self._build_folder_metadata(visible_name, parent_uuid),
        )
        self._write_text(self._remote_path(f"{folder_uuid}.content"), json.dumps([], indent=4))
        self._write_text(self._remote_path(f"{folder_uuid}.pagedata"), "\n")
        return RemarkableItem(
            uuid=folder_uuid,
            visible_name=visible_name,
            parent_uuid=parent_uuid,
            item_type="CollectionType",
            created_time=int(time.time() * 1000),
            last_modified=int(time.time() * 1000),
        )

    def _build_document_metadata(self, visible_name: str, parent_uuid: str) -> str:
        now_ms = str(int(time.time() * 1000))
        return json.dumps(
            {
                "createdTime": now_ms,
                "lastModified": now_ms,
                "lastOpened": "0",
                "lastOpenedPage": 0,
                "new": True,
                "parent": parent_uuid,
                "pinned": False,
                "source": "",
                "type": "DocumentType",
                "visibleName": visible_name,
            },
            indent=4,
        )

    def _build_folder_metadata(self, visible_name: str, parent_uuid: str) -> str:
        now_ms = str(int(time.time() * 1000))
        return json.dumps(
            {
                "createdTime": now_ms,
                "lastModified": now_ms,
                "metadatamodified": False,
                "modified": False,
                "parent": parent_uuid,
                "pinned": False,
                "synced": False,
                "type": "CollectionType",
                "version": 0,
                "visibleName": visible_name,
            },
            indent=4,
        )

    def _build_document_content(self, file_type: str) -> str:
        return json.dumps(
            {
                "cPages": {
                    "original": {
                        "timestamp": "1:0",
                        "value": -1,
                    },
                    "pages": [],
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
                "textScale": 1,
            },
            indent=4,
        )

    def _children_map(self, items: Iterable[RemarkableItem], folders_only: bool = False) -> dict[str, list[RemarkableItem]]:
        children: dict[str, list[RemarkableItem]] = {}
        for item in items:
            if folders_only and not item.is_folder:
                continue
            children.setdefault(item.parent_uuid, []).append(item)
        return children

    def _resolve_folder_ref(self, folder_ref: str, items: list[RemarkableItem]) -> str:
        if folder_ref in ("", "/", "(root)", None):
            return ""
        item = self._resolve_item_ref(folder_ref, items)
        if not item.is_folder:
            raise RemarkableError(f"Destination is not a folder: {folder_ref}")
        return item.uuid

    def _resolve_item_ref(self, item_ref: str, items: list[RemarkableItem]) -> RemarkableItem:
        if not item_ref or item_ref in ("/", "(root)"):
            raise RemarkableError("Root is not a valid item target for this operation.")

        uuid_match = next((item for item in items if item.uuid == item_ref), None)
        if uuid_match is not None:
            return uuid_match

        path = item_ref.strip("/")
        if not path:
            raise RemarkableError("Root is not a valid item target for this operation.")

        current_parent = ""
        current_item: RemarkableItem | None = None
        for raw_part in path.split("/"):
            part = raw_part.strip()
            if not part:
                continue
            matches = [
                item for item in items
                if item.parent_uuid == current_parent and item.visible_name == part
            ]
            if not matches:
                raise RemarkableError(f"Path not found: {item_ref}")
            if len(matches) > 1:
                raise RemarkableError(f"Ambiguous path segment '{part}' in '{item_ref}'")
            current_item = matches[0]
            current_parent = current_item.uuid

        if current_item is None:
            raise RemarkableError(f"Path not found: {item_ref}")
        return current_item

    def _find_child(self, items: list[RemarkableItem], parent_uuid: str, name: str, folders_only: bool = False) -> RemarkableItem | None:
        matches = [
            item for item in items
            if item.parent_uuid == parent_uuid and item.visible_name == name and (item.is_folder or not folders_only)
        ]
        if len(matches) > 1:
            raise RemarkableError(f"Ambiguous child '{name}' under parent '{parent_uuid or '(root)'}'")
        return matches[0] if matches else None

    def _ensure_no_conflict(
        self,
        items: list[RemarkableItem],
        parent_uuid: str,
        visible_name: str,
        ignore_uuid: str | None = None,
    ) -> None:
        conflicts = [
            item for item in items
            if item.parent_uuid == parent_uuid and item.visible_name == visible_name and item.uuid != ignore_uuid
        ]
        if conflicts:
            raise RemarkableError(
                f"An item named '{visible_name}' already exists in '{parent_uuid or '(root)'}'"
            )

    def _build_path(self, item: RemarkableItem, items: list[RemarkableItem]) -> str:
        item_by_uuid = {candidate.uuid: candidate for candidate in items}
        parts = [item.visible_name]
        current_parent = item.parent_uuid
        while current_parent:
            parent = item_by_uuid.get(current_parent)
            if parent is None:
                break
            parts.append(parent.visible_name)
            current_parent = parent.parent_uuid
        return "/" + "/".join(reversed(parts))

    def _descendants(self, parent_uuid: str, items: list[RemarkableItem]) -> list[RemarkableItem]:
        descendants: list[RemarkableItem] = []
        child_map = self._children_map(items)
        stack = list(child_map.get(parent_uuid, []))
        while stack:
            item = stack.pop()
            descendants.append(item)
            if item.is_folder:
                stack.extend(child_map.get(item.uuid, []))
        return descendants

    def _is_descendant(self, candidate_uuid: str, ancestor_uuid: str, items: list[RemarkableItem]) -> bool:
        parent_by_uuid = {item.uuid: item.parent_uuid for item in items}
        current = candidate_uuid
        while current:
            if current == ancestor_uuid:
                return True
            current = parent_by_uuid.get(current, "")
        return False

    def _delete_item_artifacts(self, item_uuid: str) -> None:
        quoted_root = shlex.quote(self.xochitl_path)
        quoted_uuid = shlex.quote(item_uuid)
        command = (
            f"find {quoted_root} -maxdepth 1 "
            f"\\( -name {quoted_uuid} -o -name {quoted_uuid}.* \\) "
            "-exec rm -rf {} +"
        )
        exit_code, _, stderr = self.exec_command(command)
        if exit_code != 0:
            raise RemarkableError(f"Failed to delete item {item_uuid}: {stderr.strip()}")

    def _depth(self, item: RemarkableItem, items: list[RemarkableItem]) -> int:
        parent_by_uuid = {candidate.uuid: candidate.parent_uuid for candidate in items}
        depth = 0
        current = item.parent_uuid
        while current:
            depth += 1
            current = parent_by_uuid.get(current, "")
        return depth

    def _file_type_for_path(self, local_path: str) -> str:
        extension = os.path.splitext(local_path)[1].lower()
        if extension == ".pdf":
            return "pdf"
        if extension == ".epub":
            return "epub"
        raise RemarkableError(f"Unsupported file type '{extension}'. Only .pdf and .epub are supported.")

    def _safe_int(self, value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
