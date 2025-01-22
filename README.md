# 目录监控工具

这是一个简单的目录监控工具，可以监控指定目录中的文件变化。

## 功能特点

- 监控目录中的文件创建
- 监控文件修改
- 监控文件删除
- 监控文件移动/重命名
- 通过环境变量配置监控目录

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

1. 直接运行（监控当前目录）：
```bash
python monitor.py
```

2. 通过环境变量指定监控目录：
```bash
export WATCH_DIR="/path/to/your/directory"
python monitor.py
```

## 日志输出

程序会实时输出以下事件的日志：
- 文件创建
- 文件修改
- 文件删除
- 文件移动/重命名

## 停止监控

按 Ctrl+C 可以停止监控程序。 