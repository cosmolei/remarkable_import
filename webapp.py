"""FastAPI web interface for reMarkable file management."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from remarkable import RemarkableClient, RemarkableError, load_config


ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def get_client():
    with RemarkableClient(load_config()) as client:
        yield client


app = FastAPI(title="reMarkable Control Panel")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.exception_handler(RemarkableError)
async def handle_remarkable_error(_: Request, exc: RemarkableError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/tree")
def api_tree(
    folders_only: bool = Query(default=False),
    client: RemarkableClient = Depends(get_client),
):
    return client.logical_tree(folders_only=folders_only)


@app.post("/api/folders")
def api_create_folder(
    payload: dict,
    client: RemarkableClient = Depends(get_client),
):
    path = (payload.get("path") or "").strip()
    parent = payload.get("parent") or ""
    if not path:
        raise HTTPException(status_code=400, detail="Folder path is required.")
    item = client.create_folder_path(path, parent_ref=parent)
    client.restart_xochitl()
    return {"uuid": item.uuid, "name": item.visible_name, "parent_uuid": item.parent_uuid}


@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    parent: str = Form(default=""),
    name: str = Form(default=""),
    restart: bool = Form(default=True),
    client: RemarkableClient = Depends(get_client),
):
    suffix = Path(file.filename or "upload.bin").suffix
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = handle.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

        visible_name = name.strip() if name else ""
        if not visible_name:
            original_name = file.filename or Path(temp_path).name
            visible_name = Path(original_name).stem

        item = client.upload_file(temp_path, parent_ref=parent, visible_name=visible_name)
        if restart:
            client.restart_xochitl()
        return {"uuid": item.uuid, "name": item.visible_name, "type": item.file_type}
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/api/download")
def api_download(
    target: str = Query(...),
    client: RemarkableClient = Depends(get_client),
):
    blob = client.read_document(target)
    headers = {"Content-Disposition": f'attachment; filename="{blob.filename}"'}
    return StreamingResponse(iter([blob.content]), media_type=blob.media_type, headers=headers)


@app.delete("/api/items")
def api_delete(
    target: str = Query(...),
    recursive: bool = Query(default=False),
    restart: bool = Query(default=True),
    client: RemarkableClient = Depends(get_client),
):
    deleted = client.delete_item(target, recursive=recursive)
    if restart:
        client.restart_xochitl()
    return {
        "deleted": [
            {"uuid": item.uuid, "name": item.visible_name, "type": "folder" if item.is_folder else "document"}
            for item in deleted
        ]
    }


@app.post("/api/move")
def api_move(
    payload: dict,
    client: RemarkableClient = Depends(get_client),
):
    target = (payload.get("target") or "").strip()
    destination = payload.get("destination") or ""
    if not target:
        raise HTTPException(status_code=400, detail="Target is required.")
    item = client.move_item(target, destination)
    client.restart_xochitl()
    return {"uuid": item.uuid, "new_parent": item.parent_uuid}


@app.post("/api/rename")
def api_rename(
    payload: dict,
    client: RemarkableClient = Depends(get_client),
):
    target = (payload.get("target") or "").strip()
    new_name = (payload.get("name") or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Target is required.")
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required.")
    item = client.rename_item(target, new_name)
    client.restart_xochitl()
    return {"uuid": item.uuid, "name": item.visible_name}


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the reMarkable web interface")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()

    uvicorn.run("webapp:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
