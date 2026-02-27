# MoviesDownload

> Windows 端资源搜索与下载助手 — 基于豆瓣（Douban）数据源

## 功能

- 🔍 **关键字搜索**：输入电影、图书或音乐名称，即时获取豆瓣匹配结果
- 📋 **详细信息**：显示评分、年份、简介、豆瓣链接
- 🔗 **下载链接**：自动聚合来自百度网盘、阿里云盘、夸克网盘、BT磁力等来源的下载链接
- � **智能缓存**：下载链接自动缓存，切换不同结果时无需重新获取
- 📜 **搜索历史**：自动保存搜索记录，支持快速重新搜索和历史管理
- �🖥️ **图形界面**：基于 tkinter 的桌面 GUI，支持打包为 Windows 可执行文件（.exe）

## 快速开始

### 运行源码（需要 Python 3.9+）

```bash
# 克隆项目
git clone https://github.com/ChanceyLi/MoviesDownload.git
cd MoviesDownload

# 直接运行（tkinter 为 Python 标准库，无需额外安装）
python main.py
```

### 打包为 Windows 可执行文件

```bash
# 安装 PyInstaller
pip install pyinstaller

# 构建单文件 exe（输出在 dist/ 目录）
pyinstaller build.spec
```

## 使用说明

1. 选择资源类型（**电影** / **图书** / **音乐**）
2. 在搜索框输入关键字（如"肖申克的救赎"、"三体"）
3. 按回车键或点击"搜索"按钮
4. 在左侧列表中点击某一条结果，右侧将显示详情及下载链接
5. 点击蓝色链接可在浏览器中打开；点击绿色磁力链接可唤起 BT 客户端
6. 点击"📜 历史"按钮可查看和管理搜索历史

### 新增功能

- **智能缓存**：点击不同搜索结果时，已获取的下载链接会自动缓存。当你再次点击同一结果时，链接会立即显示，无需重新获取
- **搜索历史**：
  - 每次搜索会自动保存到历史记录
  - 点击"历史"按钮查看所有搜索记录
  - 双击历史记录或点击"再次搜索"快速重新搜索
  - 支持清空历史记录功能

## 文件结构

```
MoviesDownload/
├── main.py          # 主程序入口（GUI）
├── searcher.py      # 豆瓣搜索模块
├── downloader.py    # 下载链接聚合模块
├── build.spec       # PyInstaller 打包配置
├── requirements.txt # 依赖列表
└── tests.py         # 单元测试
```

## 运行测试

```bash
pip install pytest
python -m pytest tests.py -v
```

## 注意事项

- 本工具使用豆瓣公开的建议搜索接口，请勿频繁请求以避免 IP 限制
- 下载链接来源为用户在豆瓣评论中分享的资源，具体有效性请自行验证
- 仅供学习研究使用，请遵守相关法律法规
