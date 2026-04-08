import unittest

from fastapi.testclient import TestClient

from remarkable.client import DocumentBlob, RemarkableItem
from webapp import app, get_client


class FakeClient:
    def __init__(self):
        self.calls = []

    def logical_tree(self, folders_only=False):
        self.calls.append(("logical_tree", folders_only))
        children = [
            {
                "uuid": "folder-1",
                "name": "Books",
                "parent_uuid": "",
                "type": "folder",
                "path": "/Books",
                "children": [
                    {
                        "uuid": "doc-1",
                        "name": "Linear Algebra Notes",
                        "parent_uuid": "folder-1",
                        "type": "document",
                        "file_type": "pdf",
                        "path": "/Books/Linear Algebra Notes",
                    }
                ],
            }
        ]
        if folders_only:
            children[0]["children"] = []
        return {"name": "(root)", "path": "/", "type": "root", "children": children}

    def create_folder_path(self, path, parent_ref=""):
        self.calls.append(("mkdir", path, parent_ref))
        return RemarkableItem("folder-2", "Archive", parent_ref, "CollectionType")

    def restart_xochitl(self):
        self.calls.append(("restart",))

    def upload_file(self, path, parent_ref="", visible_name=None):
        self.calls.append(("upload", path, parent_ref, visible_name))
        return RemarkableItem("doc-2", visible_name or "upload", parent_ref, "DocumentType", "pdf")

    def read_document(self, item_ref):
        self.calls.append(("download", item_ref))
        return DocumentBlob("Linear Algebra Notes.pdf", "application/pdf", b"%PDF-test")

    def delete_item(self, target, recursive=False):
        self.calls.append(("delete", target, recursive))
        return [RemarkableItem("doc-1", "Linear Algebra Notes", "folder-1", "DocumentType", "pdf")]

    def move_item(self, target, destination):
        self.calls.append(("move", target, destination))
        return RemarkableItem("doc-1", "Linear Algebra Notes", "folder-2", "DocumentType", "pdf")

    def rename_item(self, target, new_name):
        self.calls.append(("rename", target, new_name))
        return RemarkableItem("doc-1", new_name, "folder-1", "DocumentType", "pdf")


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClient()

        def override_client():
            yield self.fake

        app.dependency_overrides[get_client] = override_client
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_index_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("reMarkable Control Panel", response.text)

    def test_tree_endpoint_returns_logical_tree(self):
        response = self.client.get("/api/tree")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "root")
        self.assertEqual(payload["children"][0]["name"], "Books")

    def test_create_folder_endpoint(self):
        response = self.client.post("/api/folders", json={"path": "Archive", "parent": "/Books"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uuid"], "folder-2")
        self.assertIn(("restart",), self.fake.calls)

    def test_upload_endpoint(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
            data={"parent": "/Books", "name": "Notes"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Notes")
        self.assertEqual(payload["type"], "pdf")

    def test_upload_endpoint_uses_original_filename_when_name_missing(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("physics.epub", b"epub-data", "application/epub+zip")},
            data={"parent": "/Books"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "physics")

    def test_download_endpoint(self):
        response = self.client.get("/api/download", params={"target": "/Books/Linear Algebra Notes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("attachment;", response.headers["content-disposition"])
        self.assertEqual(response.content, b"%PDF-test")

    def test_delete_endpoint(self):
        response = self.client.delete("/api/items", params={"target": "/Books/Linear Algebra Notes"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deleted"][0]["uuid"], "doc-1")

    def test_move_endpoint(self):
        response = self.client.post("/api/move", json={"target": "/Books/Linear Algebra Notes", "destination": "/Archive"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_parent"], "folder-2")

    def test_rename_endpoint(self):
        response = self.client.post("/api/rename", json={"target": "/Books/Linear Algebra Notes", "name": "Renamed Notes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Renamed Notes")


if __name__ == "__main__":
    unittest.main()
