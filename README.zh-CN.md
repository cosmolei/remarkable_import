# reMarkable Import

[English README](./README.md)

## 概述

`reMarkable Import` 用于通过 SSH 管理 reMarkable 平板上的文档和目录。项目现在对外暴露的是“解析后的逻辑文件树”，而不是底层 `.metadata` 文件，因此也更适合作为后续 Web 界面的基础。
理论上适配 reMarkable 全系产品，但目前只在 reMarkable Paper Pro Move 上测试过。

## 功能

- 列出目录和文档组成的逻辑树。
- 创建目录或多级目录路径。
- 上传 `.pdf` 和 `.epub` 文档。
- 下载文档。
- 删除文档。
- 删除目录，支持递归删除非空目录。
- 将文档或目录移动到另一个目录。
- 支持用 UUID 或逻辑路径定位目标。

## 运行要求

- Python 3.8 或更高版本
- `paramiko`
- 能通过 SSH 访问 reMarkable 平板

## 安装

```bash
pip install -r requirements.txt
```

## 配置

先将 `config.example.json` 复制为 `config.json`，再填写你自己的连接信息：

```json
{
  "host": "10.11.99.1",
  "username": "root",
  "password": "your-password",
  "xochitl_path": "/home/root/.local/share/remarkable/xochitl"
}
```

字段说明：

- `host`：reMarkable 的 IP 地址或主机名
- `username`：SSH 用户名
- `password`：SSH 密码
- `xochitl_path`：reMarkable 上 `xochitl` 存储目录的路径

`config.json` 已加入 Git 忽略，不会被提交。

## 用法

通用语法：

```bash
python upload.py <command> [options]
```

### 列出逻辑目录树

```bash
python upload.py list
```

只显示目录：

```bash
python upload.py list --folders-only
```

同时显示 UUID：

```bash
python upload.py list --show-uuid
```

输出示例：

```text
(root)
├─ Books/
│  ├─ Math/
│  │  └─ Linear Algebra (pdf)
│  └─ Physics (epub)
└─ Notes/
```

### 创建目录

在根目录创建一个目录：

```bash
python upload.py mkdir Books
```

一条命令创建多级目录：

```bash
python upload.py mkdir Books/Math/Algebra
```

通过 UUID 或逻辑路径指定父目录：

```bash
python upload.py mkdir Algebra --parent Books/Math
```

### 上传文档

上传到根目录：

```bash
python upload.py upload ./sample.pdf
```

上传时指定显示名称：

```bash
python upload.py upload ./sample.pdf --name "Linear Algebra Notes"
```

按逻辑路径上传到指定目录：

```bash
python upload.py upload ./sample.pdf --parent Books/Math
```

按 UUID 上传到指定目录：

```bash
python upload.py upload ./sample.pdf --parent 12345678-1234-1234-1234-123456789abc
```

### 下载文档

按逻辑路径下载：

```bash
python upload.py download Books/Math/"Linear Algebra Notes"
```

下载到指定本地文件：

```bash
python upload.py download Books/Physics ./downloads/physics.epub
```

### 删除文档或目录

删除文档：

```bash
python upload.py delete Books/Math/"Linear Algebra Notes"
```

删除空目录：

```bash
python upload.py delete Books/Math/Algebra
```

递归删除非空目录：

```bash
python upload.py delete Books --recursive
```

### 移动文档或目录

把文档移动到另一个目录：

```bash
python upload.py move Books/Physics Notes
```

把目录移动到另一个目录：

```bash
python upload.py move Books/Math Archive
```

## Web 界面

启动本地 Web 界面：

```bash
python webapp.py
```

然后打开 `http://127.0.0.1:8000`。

当前 Web 界面支持：

- 从根目录开始的单目录浏览
- 点击目录进入下一级，并可返回上级
- 通过拖拽或文件选择器批量上传到当前目录
- 在当前目录内创建子目录
- 重命名目录或文档
- 通过列表复选框进行批量删除
- 基于当前选中项进行下载、移动和重命名
- 上传进度展示
- 英文/中文界面切换

也可以自定义监听地址和端口：

```bash
python webapp.py --host 127.0.0.1 --port 8765
```

## 说明

- CLI 基于元数据解析出的逻辑树工作，而不是直接展示底层 `.metadata` 文件名。
- `list` 默认不显示 UUID，输出会更接近真实目录视图。
- 写操作完成后，脚本会重启 `xochitl` 服务，让变更显示在设备上。
- 在重启 `xochitl` 前，客户端会先清理该 systemd 单元的 failed 状态，减少高频操作时触发启动限流的概率。
- 当前仅支持上传 `.pdf` 和 `.epub`。
- 如果逻辑路径存在歧义，脚本会直接报错，不会自行猜测。

## 项目结构

- `upload.py`：CLI 入口
- `remarkable/client.py`：逻辑树解析、上传、下载、移动、删除、建目录等核心能力
- `webapp.py`：FastAPI Web 服务
- `templates/` 和 `static/`：Web 模板与静态资源
- `requirements.txt`：Python 依赖清单
- `config.example.json`：配置模板
- `config.json`：本地配置，已被 Git 忽略
