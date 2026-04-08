# reMarkable Import

[English README](./README.md)

## 概述

`reMarkable Import` 用于通过 SSH 向 reMarkable 平板上传 PDF 和 EPUB 文件，也支持创建目录、创建多级子目录，以及把当前目录结构按树形方式列出来。

## 功能

- 上传 `.pdf` 和 `.epub` 文档到 reMarkable。
- 为上传文档设置自定义显示名称。
- 通过 UUID 将文档上传到指定父目录。
- 在根目录或已有目录下创建新目录。
- 一条命令创建多级子目录，例如 `Books/Math/Algebra`。
- 按父子关系树形列出目录。

## 运行要求

- Python 3.8 或更高版本
- `paramiko`
- 能通过 SSH 访问 reMarkable 平板

## 安装

```bash
pip install paramiko
```

## 配置

在项目根目录创建 `config.json`：

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

## 用法

通用语法：

```bash
python upload.py [file] [options]
```

### 上传文档

```bash
python upload.py ./sample.pdf
```

默认会使用“文件名去掉扩展名”作为显示名称。

### 使用自定义显示名称上传

```bash
python upload.py ./sample.pdf --name "Linear Algebra Notes"
```

### 上传到指定目录

```bash
python upload.py ./sample.pdf --parent 12345678-1234-1234-1234-123456789abc
```

如果你需要目录 UUID，可以先执行 `--list-folders`。

### 以树形结构列出目录

```bash
python upload.py --list-folders
```

输出示例：

```text
Folders on device:
(root)
├─ Books [11111111-1111-1111-1111-111111111111]
│  └─ Math [22222222-2222-2222-2222-222222222222]
└─ Notes [33333333-3333-3333-3333-333333333333]
```

### 创建目录

```bash
python upload.py --mkdir Books
```

### 在指定父目录下创建子目录

```bash
python upload.py --mkdir Math --parent 11111111-1111-1111-1111-111111111111
```

### 一条命令创建多级目录

```bash
python upload.py --mkdir Books/Math/Algebra
```

如果路径中的某一级目录在同一父目录下已经存在，脚本会直接复用它，只创建缺失的层级。

## 说明

- 上传文档或创建目录后，脚本会重启 `xochitl` 服务，让变更显示在设备上。
- 当前仅支持 `.pdf` 和 `.epub`。
- 目前目录选择仍然使用 UUID，不支持直接传目录路径。

## 项目文件

- `upload.py`：主脚本
- `config.json`：本地连接配置

