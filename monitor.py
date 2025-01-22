import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from main import process_file, sum_invoices

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class InvoiceHandler(FileSystemEventHandler):
    def __init__(self):
        self.supported_extensions = {'.pdf', '.ofd'}

    def is_supported_file(self, path):
        return os.path.splitext(path)[1].lower() in self.supported_extensions

    def on_created(self, event):
        if not event.is_directory and self.is_supported_file(event.src_path):
            logging.info(f"发现新发票文件: {event.src_path}")
            try:
                # 等待文件完全写入
                time.sleep(1)
                # 处理发票文件
                process_file(event.src_path, False)
                # 更新发票总额
                invoice_folder = os.path.dirname(event.src_path)
                sum_invoices(invoice_folder)
            except Exception as e:
                logging.error(f"处理文件时出错: {str(e)}")

def start_monitoring():
    # 从环境变量获取监控目录，如果未设置则使用当前目录
    watch_path = os.getenv('WATCH_DIR', '.')
    
    # 确保目录存在
    if not os.path.exists(watch_path):
        logging.error(f"监控目录不存在: {watch_path}")
        sys.exit(1)
    
    logging.info(f"开始监控发票目录: {watch_path}")
    logging.info("支持的文件类型: PDF, OFD")
    
    # 创建事件处理器和观察者
    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=False)
    
    # 启动观察者
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("监控已停止")
    
    observer.join()

if __name__ == "__main__":
    start_monitoring() 