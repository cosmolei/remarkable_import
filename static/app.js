const I18N = {
  en: {
    refresh: "Refresh",
    back: "Back",
    up: "Up",
    upload: "Upload",
    newFolder: "New Folder",
    rename: "Rename",
    move: "Move",
    download: "Download",
    delete: "Delete",
    dropZone: "Drop PDF or EPUB here to upload into the current folder",
    currentFolder: "Current Folder",
    nameCol: "Name",
    typeCol: "Type",
    createdCol: "Created",
    sizeCol: "Size",
    newFolderHint: "Create a folder inside the current directory.",
    renameHint: "Change the name of the selected item.",
    moveHint: "Choose a destination folder for the selected item.",
    cancel: "Cancel",
    create: "Create",
    save: "Save",
    root: "Root",
    idle: "Idle",
    ready: "Ready",
    refreshing: "Refreshing...",
    loading: "Loading...",
    creatingFolder: "Creating folder...",
    uploading: "Uploading...",
    uploadDone: "Upload complete",
    moving: "Moving item...",
    deleting: "Deleting item...",
    renaming: "Renaming item...",
    empty: "This folder is empty.",
    folder: "Folder",
    document: "Document",
    items: "items",
    selectedCount: "{count} selected",
    deleteConfirm: "Delete {count} item(s)?",
    deleteFolderRecursive: "Some selected folders are not empty. Delete recursively?",
    chooseItem: "Select item(s) first.",
    chooseSingleItem: "Select exactly one item.",
    chooseSingleDocument: "Select exactly one document.",
    rootSymbol: "/",
  },
  zh: {
    refresh: "刷新",
    back: "返回",
    up: "上级",
    upload: "上传",
    newFolder: "新建目录",
    rename: "重命名",
    move: "移动",
    download: "下载",
    delete: "删除",
    dropZone: "拖拽 PDF 或 EPUB 到这里，上传到当前目录",
    currentFolder: "当前目录",
    nameCol: "名称",
    typeCol: "类型",
    createdCol: "创建时间",
    sizeCol: "大小",
    newFolderHint: "在当前目录中创建一个子目录。",
    renameHint: "修改当前选中项目的名称。",
    moveHint: "为当前选中项目选择一个目标目录。",
    cancel: "取消",
    create: "创建",
    save: "保存",
    root: "根目录",
    idle: "空闲",
    ready: "就绪",
    refreshing: "正在刷新...",
    loading: "处理中...",
    creatingFolder: "正在创建目录...",
    uploading: "正在上传...",
    uploadDone: "上传完成",
    moving: "正在移动项目...",
    deleting: "正在删除项目...",
    renaming: "正在重命名项目...",
    empty: "这个目录为空。",
    folder: "目录",
    document: "文档",
    items: "项",
    selectedCount: "已选择 {count} 项",
    deleteConfirm: "确认删除 {count} 个项目？",
    deleteFolderRecursive: "所选目录中存在非空目录，是否递归删除？",
    chooseItem: "请先选择项目。",
    chooseSingleItem: "请只选择一个项目。",
    chooseSingleDocument: "请只选择一个文档。",
    rootSymbol: "/",
  },
};

const state = {
  locale: "en",
  tree: null,
  currentPath: "/",
  currentNode: null,
  history: ["/"],
  selectedPaths: [],
  busy: false,
};

const itemList = document.getElementById("itemList");
const statusEl = document.getElementById("status");
const currentFolderName = document.getElementById("currentFolderName");
const itemCount = document.getElementById("itemCount");
const pathBar = document.getElementById("pathBar");
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const folderDialog = document.getElementById("folderDialog");
const folderForm = document.getElementById("folderForm");
const folderNameInput = document.getElementById("folderNameInput");
const renameDialog = document.getElementById("renameDialog");
const renameForm = document.getElementById("renameForm");
const renameInput = document.getElementById("renameInput");
const renameTargetLabel = document.getElementById("renameTargetLabel");
const moveDialog = document.getElementById("moveDialog");
const moveDestinationList = document.getElementById("moveDestinationList");
const moveTargetLabel = document.getElementById("moveTargetLabel");
const loadingOverlay = document.getElementById("loadingOverlay");
const loadingText = document.getElementById("loadingText");
const uploadProgress = document.getElementById("uploadProgress");
const uploadProgressBar = document.getElementById("uploadProgressBar");
const uploadProgressLabel = document.getElementById("uploadProgressLabel");
const uploadProgressValue = document.getElementById("uploadProgressValue");

function t(key) {
  return I18N[state.locale][key] || key;
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
}

function setBusy(isBusy, text = "") {
  state.busy = isBusy;
  loadingOverlay.classList.toggle("hidden", !isBusy);
  loadingText.textContent = text || t("loading");
  document.querySelectorAll("button, input").forEach((node) => {
    node.disabled = isBusy;
  });
}

function setUploadProgress(visible, label = "", percent = 0) {
  uploadProgress.classList.toggle("hidden", !visible);
  uploadProgressLabel.textContent = label || t("uploading");
  uploadProgressValue.textContent = `${Math.round(percent)}%`;
  uploadProgressBar.style.width = `${Math.max(0, Math.min(percent, 100))}%`;
}

function applyLocale() {
  document.documentElement.lang = state.locale === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.getElementById("langToggle").textContent = state.locale === "en" ? "中文" : "EN";
  folderNameInput.placeholder = state.locale === "en" ? "Books" : "资料";
  renameInput.placeholder = state.locale === "en" ? "New name" : "新名称";
  uploadProgressLabel.textContent = t("uploading");
  renderCurrentDirectory();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    throw new Error(data.error || data.detail || "Request failed");
  }
  return data;
}

function findNodeByPath(path, node = state.tree) {
  if (!node) return null;
  if (node.path === path) return node;
  for (const child of node.children || []) {
    const found = findNodeByPath(path, child);
    if (found) return found;
  }
  return null;
}

function normalizeFolderPath(path) {
  if (!path || path === "/") return "/";
  return path.endsWith("/") ? path.slice(0, -1) : path;
}

function directoryChildren(node) {
  return [...(node?.children || [])].sort((a, b) => {
    const typeOrder = a.type === b.type ? 0 : a.type === "folder" ? -1 : 1;
    return typeOrder || a.name.localeCompare(b.name);
  });
}

function selectedItems() {
  return state.selectedPaths.map((path) => findNodeByPath(path)).filter(Boolean);
}

function setCurrentPath(path, pushHistory = true) {
  const normalized = normalizeFolderPath(path);
  const node = findNodeByPath(normalized);
  if (!node || node.type === "document") return;
  state.currentPath = normalized;
  state.currentNode = node;
  state.selectedPaths = [];
  if (pushHistory && state.history[state.history.length - 1] !== normalized) {
    state.history.push(normalized);
  }
  renderCurrentDirectory();
}

function renderBreadcrumbs() {
  pathBar.innerHTML = "";
  const parts = state.currentPath === "/" ? [] : state.currentPath.slice(1).split("/");
  const crumbs = [{ name: t("root"), path: "/" }];
  let current = "";
  for (const part of parts) {
    current += `/${part}`;
    crumbs.push({ name: part, path: current });
  }

  crumbs.forEach((crumb, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "crumb";
    if (crumb.path === state.currentPath) button.classList.add("active");
    button.textContent = crumb.name;
    button.addEventListener("click", () => {
      if (!state.busy) setCurrentPath(crumb.path);
    });
    pathBar.appendChild(button);
    if (index < crumbs.length - 1) {
      const sep = document.createElement("span");
      sep.textContent = "/";
      pathBar.appendChild(sep);
    }
  });
}

function rowTypeLabel(item) {
  if (item.type === "folder") return t("folder");
  return item.file_type ? item.file_type.toUpperCase() : t("document");
}

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat(state.locale === "zh" ? "zh-CN" : "en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return "-";
  }
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined) return "-";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function rowIcon(item) {
  if (item.type === "folder") return "▣";
  if (item.file_type === "pdf") return "◫";
  if (item.file_type === "epub") return "◧";
  return "•";
}

function selectionSummary() {
  if (!state.selectedPaths.length) return t("ready");
  return t("selectedCount").replace("{count}", String(state.selectedPaths.length));
}

function renderCurrentDirectory() {
  if (!state.tree) return;
  if (!state.currentNode) {
    state.currentNode = state.tree;
    state.currentPath = "/";
  }

  renderBreadcrumbs();
  currentFolderName.textContent = state.currentPath === "/" ? t("rootSymbol") : state.currentPath;
  const children = directoryChildren(state.currentNode);
  itemCount.textContent = `${children.length} ${t("items")}`;
  itemList.innerHTML = "";
  if (!state.busy) setStatus(selectionSummary());

  if (!children.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = t("empty");
    itemList.appendChild(empty);
    return;
  }

  children.forEach((item) => {
    const row = document.createElement("div");
    row.className = "item-row";
    if (state.selectedPaths.includes(item.path)) row.classList.add("selected");
    row.innerHTML = `
      <input type="checkbox" class="item-check" ${state.selectedPaths.includes(item.path) ? "checked" : ""}>
      <button type="button" class="item-main item-open">
        <span class="item-icon">${rowIcon(item)}</span>
        <div>
          <div class="item-name" title="${item.name}">${item.name}${item.type === "folder" ? "/" : ""}</div>
          <div class="item-path" title="${item.path}">${item.path}</div>
        </div>
      </button>
      <div class="item-type">${rowTypeLabel(item)}</div>
      <div class="item-time">${formatDate(item.created_time)}</div>
      <div class="item-size">${formatSize(item.size_bytes)}</div>
    `;
    row.querySelector(".item-open").addEventListener("click", () => {
      if (state.busy) return;
      if (item.type === "folder") {
        setCurrentPath(item.path);
      }
    });
    row.querySelector(".item-check").addEventListener("click", (event) => {
      event.stopPropagation();
      if (state.busy) return;
      if (event.target.checked) {
        if (!state.selectedPaths.includes(item.path)) state.selectedPaths.push(item.path);
      } else {
        state.selectedPaths = state.selectedPaths.filter((path) => path !== item.path);
      }
      renderCurrentDirectory();
    });
    itemList.appendChild(row);
  });
}

async function refreshTree() {
  setStatus(t("refreshing"));
  setBusy(true, t("refreshing"));
  try {
    state.tree = await fetchJson("/api/tree");
    const currentExists = findNodeByPath(state.currentPath);
    setCurrentPath(currentExists ? state.currentPath : "/", false);
    setStatus(t("ready"));
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function uploadFiles(files) {
  if (!files.length) return;
  setBusy(true, t("uploading"));
  try {
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parent", state.currentPath);
      formData.append("restart", String(index === files.length - 1));
      setStatus(`${t("uploading")} ${file.name}`);
      setUploadProgress(true, `${t("uploading")} ${file.name}`, 0);
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/upload");
        xhr.upload.addEventListener("progress", (event) => {
          if (!event.lengthComputable) return;
          setUploadProgress(true, `${t("uploading")} ${file.name}`, (event.loaded / event.total) * 100);
        });
        xhr.addEventListener("load", () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            setUploadProgress(true, `${t("uploadDone")} ${file.name}`, 100);
            resolve();
            return;
          }
          try {
            const data = JSON.parse(xhr.responseText);
            reject(new Error(data.error || data.detail || "Upload failed"));
          } catch {
            reject(new Error("Upload failed"));
          }
        });
        xhr.addEventListener("error", () => reject(new Error("Upload failed")));
        xhr.send(formData);
      });
    }
    await refreshTree();
  } finally {
    setUploadProgress(false, "", 0);
    setBusy(false);
  }
}

function requireSelection(single = false, documentOnly = false) {
  const items = selectedItems();
  if (!items.length) {
    alert(t("chooseItem"));
    return null;
  }
  if (single && items.length !== 1) {
    alert(documentOnly ? t("chooseSingleDocument") : t("chooseSingleItem"));
    return null;
  }
  if (documentOnly && (items.length !== 1 || items[0].type !== "document")) {
    alert(t("chooseSingleDocument"));
    return null;
  }
  return items;
}

function listFolderDestinations(node = state.tree, acc = []) {
  if (!node) return acc;
  if (node.type === "root" || node.type === "folder") {
    acc.push({ path: node.path, name: node.type === "root" ? t("root") : node.name });
  }
  for (const child of node.children || []) {
    if (child.type === "folder") listFolderDestinations(child, acc);
  }
  return acc;
}

document.getElementById("refreshButton").addEventListener("click", refreshTree);
document.getElementById("langToggle").addEventListener("click", () => {
  if (state.busy) return;
  state.locale = state.locale === "en" ? "zh" : "en";
  applyLocale();
});
document.getElementById("backButton").addEventListener("click", () => {
  if (state.busy || state.history.length <= 1) return;
  state.history.pop();
  setCurrentPath(state.history[state.history.length - 1], false);
});
document.getElementById("upButton").addEventListener("click", () => {
  if (state.busy || state.currentPath === "/") return;
  const parts = state.currentPath.slice(1).split("/");
  parts.pop();
  setCurrentPath(parts.length ? `/${parts.join("/")}` : "/");
});
document.getElementById("createFolderButton").addEventListener("click", () => {
  if (state.busy) return;
  folderNameInput.value = "";
  folderDialog.showModal();
  folderNameInput.focus();
});
document.getElementById("folderCancel").addEventListener("click", () => folderDialog.close());
folderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = folderNameInput.value.trim();
  if (!name) return;
  try {
    setStatus(t("creatingFolder"));
    setBusy(true, t("creatingFolder"));
    await fetchJson("/api/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: name, parent: state.currentPath }),
    });
    folderDialog.close();
    await refreshTree();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("renameButton").addEventListener("click", () => {
  const items = requireSelection(true, false);
  if (!items) return;
  const selected = items[0];
  renameTargetLabel.textContent = selected.path;
  renameInput.value = selected.name;
  renameDialog.showModal();
  renameInput.focus();
  renameInput.select();
});
document.getElementById("renameCancel").addEventListener("click", () => renameDialog.close());
renameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const items = requireSelection(true, false);
  if (!items) return;
  const selected = items[0];
  const name = renameInput.value.trim();
  if (!name) return;
  try {
    setStatus(t("renaming"));
    setBusy(true, t("renaming"));
    await fetchJson("/api/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: selected.path, name }),
    });
    renameDialog.close();
    await refreshTree();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
});

fileInput.addEventListener("change", async (event) => {
  try {
    await uploadFiles([...event.target.files]);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    event.target.value = "";
  }
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});
dropZone.addEventListener("drop", async (event) => {
  try {
    await uploadFiles([...event.dataTransfer.files]);
  } catch (error) {
    setStatus(error.message, true);
  }
});

itemList.addEventListener("click", (event) => {
  if (state.busy) return;
  if (!event.target.closest(".item-row")) {
    state.selectedPaths = [];
    renderCurrentDirectory();
  }
});

document.getElementById("moveButton").addEventListener("click", () => {
  const items = requireSelection(true, false);
  if (!items) return;
  const selected = items[0];
  moveTargetLabel.textContent = selected.path;
  moveDestinationList.innerHTML = "";
  listFolderDestinations().forEach((destination) => {
    if (destination.path === selected.path) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "move-option";
    button.textContent = destination.path === "/" ? t("root") : destination.path;
    button.addEventListener("click", async () => {
      moveDialog.close();
      try {
        setStatus(t("moving"));
        setBusy(true, t("moving"));
        await fetchJson("/api/move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target: selected.path, destination: destination.path }),
        });
        await refreshTree();
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        setBusy(false);
      }
    });
    moveDestinationList.appendChild(button);
  });
  moveDialog.showModal();
});
document.getElementById("moveCancel").addEventListener("click", () => moveDialog.close());

document.getElementById("downloadButton").addEventListener("click", () => {
  const items = requireSelection(true, true);
  if (!items) return;
  window.location.href = `/api/download?target=${encodeURIComponent(items[0].path)}`;
});

document.getElementById("deleteButton").addEventListener("click", async () => {
  const items = requireSelection(false, false);
  if (!items) return;
  if (!confirm(t("deleteConfirm").replace("{count}", String(items.length)))) return;
  let recursive = false;
  if (items.some((item) => item.type === "folder" && item.children?.length)) {
    recursive = confirm(t("deleteFolderRecursive"));
    if (!recursive) return;
  }
  try {
    setStatus(t("deleting"));
    setBusy(true, t("deleting"));
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      const params = new URLSearchParams({
        target: item.path,
        recursive: String(recursive),
        restart: String(index === items.length - 1),
      });
      await fetchJson(`/api/items?${params.toString()}`, { method: "DELETE" });
    }
    await refreshTree();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
});

setStatus(t("idle"));
applyLocale();
refreshTree();
