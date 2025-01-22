from fastapi import FastAPI, UploadFile, File, Form, Request, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
import logging
from typing import List
import shutil
from datetime import datetime, timedelta
import zipfile
import asyncio
from pathlib import Path
from config_manager import config
from pdf_processor import process_special_pdf
from ofd_processor import process_ofd
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import hashlib
import json

app = FastAPI(title="发票处理系统")

# 创建必要的目录
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("downloads", exist_ok=True)

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic()

class ProcessedFilesManager:
    def __init__(self):
        self.processed_files_path = "processed_files.json"
        self.processed_files = self._load_processed_files()
        
    def _load_processed_files(self):
        """加载已处理文件记录"""
        if os.path.exists(self.processed_files_path):
            try:
                with open(self.processed_files_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"加载处理记录失败: {e}")
                return {}
        return {}
    
    def _save_processed_files(self):
        """保存已处理文件记录"""
        try:
            with open(self.processed_files_path, 'w', encoding='utf-8') as f:
                json.dump(self.processed_files, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存处理记录失败: {e}")
    
    def get_file_hash(self, file_path):
        """计算文件的SHA256哈希值"""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logging.error(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    def is_file_processed(self, file_path):
        """检查文件是否已处理"""
        file_hash = self.get_file_hash(file_path)
        if not file_hash:
            return False
        return file_hash in self.processed_files
    
    def add_processed_file(self, file_path, new_name):
        """添加处理记录"""
        file_hash = self.get_file_hash(file_path)
        if file_hash:
            self.processed_files[file_hash] = {
                "original_path": file_path,
                "new_name": new_name,
                "processed_time": datetime.now().isoformat()
            }
            self._save_processed_files()

# 创建处理记录管理器实例
processed_files_manager = ProcessedFilesManager()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """验证管理员密码"""
    # 从配置文件获取管理员密码的哈希值，如果不存在则使用默认密码 "admin"
    stored_password_hash = config.get("admin_password_hash", 
                                    hashlib.sha256("admin".encode()).hexdigest())
    
    # 计算提供的密码的哈希值
    provided_password_hash = hashlib.sha256(credentials.password.encode()).hexdigest()
    
    # 验证用户名和密码
    is_correct_username = secrets.compare_digest(credentials.username, "admin")
    is_correct_password = secrets.compare_digest(provided_password_hash, stored_password_hash)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

class InvoiceHandler(FileSystemEventHandler):
    def __init__(self):
        self.update_timer = None
        super().__init__()
    
    def update_directory_amount(self, directory):
        """更新目录名以显示总金额"""
        try:
            total_amount = 0
            # 扫描目录下所有PDF和OFD文件
            for file in os.listdir(directory):
                if file.lower().endswith(('.pdf', '.ofd')):
                    file_path = os.path.join(directory, file)
                    try:
                        # 从文件名中提取金额
                        amount_match = re.search(r'_(\d+\.\d{2})\.(pdf|ofd)$', file)
                        if amount_match:
                            total_amount += float(amount_match.group(1))
                    except Exception as e:
                        logging.warning(f"提取文件金额失败 {file}: {e}")
            
            # 获取目录的基本名称（不包含金额部分）
            dir_name = os.path.basename(directory)
            # 使用 -￥ 作为分隔符来分割目录名
            base_dir_name = re.sub(r'-￥\d+\.\d{2}$', '', dir_name)
            
            # 构造新的目录名，使用 -￥ 作为分隔符
            new_dir_name = f"{base_dir_name}-￥{total_amount:.2f}"
            
            # 如果目录名不同，则重命名
            if dir_name != new_dir_name:
                new_path = os.path.join(os.path.dirname(directory), new_dir_name)
                os.rename(directory, new_path)
                logging.info(f"更新目录金额: {new_dir_name}")
                
                # 更新配置中的watch_dir
                if directory == config.get("watch_dir"):
                    config.set("watch_dir", new_path)
                
        except Exception as e:
            logging.error(f"更新目录金额失败: {e}")
    
    def schedule_update(self, directory):
        """调度目录更新（带防抖动）"""
        if self.update_timer:
            self.update_timer.cancel()
        
        # 创建新的定时器，1秒后执行更新（减少延迟时间）
        self.update_timer = threading.Timer(1.0, self.update_directory_amount, args=[directory])
        self.update_timer.start()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        if file_path.lower().endswith(('.pdf', '.ofd')):
            try:
                relative_path = os.path.relpath(file_path, config.get("watch_dir", "./watch"))
                
                # 检查文件是否已处理
                if processed_files_manager.is_file_processed(file_path):
                    logging.info(f"文件已处理过，跳过: {relative_path}")
                    return
                
                logging.info(f"检测到新文件: {relative_path}")
                ext = os.path.splitext(file_path)[1].lower()
                result = None
                
                # 使用Watch目录的配置
                config.set("rename_with_amount", config.get("watch_rename_with_amount", False))
                
                if ext == '.pdf':
                    result = process_special_pdf(file_path)
                elif ext == '.ofd':
                    result = process_ofd(file_path, "tmp", False)
                
                if result:
                    processed_files_manager.add_processed_file(file_path, os.path.basename(result))
                    # 调度目录金额更新
                    self.schedule_update(os.path.dirname(file_path))
                    
            except Exception as e:
                logging.error(f"处理文件失败 {file_path}: {e}")
            finally:
                # 恢复原始配置
                config.set("rename_with_amount", config.get("webui_rename_with_amount", False))
    
    def on_deleted(self, event):
        """文件删除时更新目录金额"""
        if not event.is_directory and event.src_path.lower().endswith(('.pdf', '.ofd')):
            self.schedule_update(os.path.dirname(event.src_path))
    
    def on_moved(self, event):
        """文件移动时更新源目录和目标目录的金额"""
        if not event.is_directory and event.src_path.lower().endswith(('.pdf', '.ofd')):
            self.schedule_update(os.path.dirname(event.src_path))
            if os.path.dirname(event.src_path) != os.path.dirname(event.dest_path):
                self.schedule_update(os.path.dirname(event.dest_path))

def start_file_monitor():
    """启动文件监控"""
    watch_dir = config.get("watch_dir", "./watch")
    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir, exist_ok=True)
        
    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=True)
    observer.start()
    
    # 启动时计算初始金额
    event_handler.update_directory_amount(watch_dir)
    
    logging.info(f"开始监控目录: {watch_dir} (包含子目录)")
    return observer

# 存储文件上传时间的字典
file_upload_times = {}

async def cleanup_old_files():
    """定期清理超过30分钟的上传文件"""
    while True:
        try:
            current_time = datetime.now()
            # 检查并删除过期文件
            expired_files = []
            for file_path, upload_time in file_upload_times.items():
                if current_time - upload_time > timedelta(minutes=30):
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            logging.info(f"已删除过期文件: {file_path}")
                        except Exception as e:
                            logging.error(f"删除文件失败 {file_path}: {e}")
                    expired_files.append(file_path)
            
            # 从记录中移除已删除的文件
            for file_path in expired_files:
                file_upload_times.pop(file_path, None)
                
        except Exception as e:
            logging.error(f"清理文件时发生错误: {e}")
        
        # 每分钟检查一次
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    """启动时开始运行清理任务"""
    asyncio.create_task(cleanup_old_files())

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页"""
    # 确保使用Web UI的配置
    config_data = config.get_all()
    config_data["rename_with_amount"] = config_data.get("webui_rename_with_amount", False)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": config_data
        }
    )

def create_zip_file(files_info):
    """创建包含处理后文件的ZIP包"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"processed_invoices_{timestamp}.zip"
    zip_path = os.path.join("downloads", zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for info in files_info:
            if info["success"] and info.get("new_path"):
                # 将文件添加到ZIP中，使用新文件名作为ZIP中的名称
                zipf.write(
                    info["new_path"],
                    os.path.basename(info["new_path"])
                )
    
    return zip_path

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """处理上传的文件并返回ZIP包下载链接"""
    results = []
    processed_files = []
    
    try:
        # 使用Web UI的配置
        config.set("rename_with_amount", config.get("webui_rename_with_amount", False))
        
        for file in files:
            try:
                # 保存上传的文件
                file_path = os.path.join("uploads", file.filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                # 记录文件上传时间
                file_upload_times[file_path] = datetime.now()
                
                # 处理文件
                ext = os.path.splitext(file.filename)[1].lower()
                result = None
                amount = None
                if ext == '.pdf':
                    result = process_special_pdf(file_path)
                    # 从文件名中提取金额（假设文件名中包含金额信息）
                    if result:
                        try:
                            amount_match = re.search(r'_(\d+\.\d{2})\.pdf$', result)
                            if amount_match:
                                amount = amount_match.group(1)
                        except Exception as e:
                            logging.warning(f"提取金额失败: {e}")
                elif ext == '.ofd':
                    result = process_ofd(file_path, "tmp", False)
                    # 从文件名中提取金额（假设文件名中包含金额信息）
                    if result:
                        try:
                            amount_match = re.search(r'_(\d+\.\d{2})\.(pdf|ofd)$', result)
                            if amount_match:
                                amount = amount_match.group(1)
                        except Exception as e:
                            logging.warning(f"提取金额失败: {e}")
                
                file_info = {
                    "filename": file.filename,
                    "success": result is not None,
                    "new_name": os.path.basename(result) if result else None,
                    "new_path": result if result else None,
                    "amount": amount
                }
                
                results.append(file_info)
                if result:
                    processed_files.append(file_info)
                
            except Exception as e:
                logging.error(f"处理文件失败 {file.filename}: {e}")
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": str(e)
                })
        
        # 如果有成功处理的文件，创建ZIP包
        zip_path = None
        if processed_files:
            zip_path = create_zip_file(processed_files)
            # 清理已处理的原始文件
            for file_info in processed_files:
                if file_info.get("new_path") and os.path.exists(file_info["new_path"]):
                    try:
                        os.remove(file_info["new_path"])
                    except Exception as e:
                        logging.error(f"清理文件失败 {file_info['new_path']}: {e}")
        
        return JSONResponse(content={
            "results": results,
            "download_url": f"/download/{os.path.basename(zip_path)}" if zip_path else None
        })
        
    except Exception as e:
        logging.error(f"批量处理文件失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
    finally:
        # 恢复Watch目录的配置
        config.set("rename_with_amount", config.get("watch_rename_with_amount", False))

@app.get("/download/{filename}")
async def download_file(filename: str):
    """下载处理后的ZIP文件"""
    file_path = os.path.join("downloads", filename)
    if not os.path.exists(file_path):
        return JSONResponse(
            status_code=404,
            content={"error": "文件不存在"}
        )
    
    response = FileResponse(
        file_path,
        media_type="application/zip",
        filename=filename
    )
    
    # 设置回调以在发送完成后删除文件
    async def delete_file():
        try:
            os.remove(file_path)
        except Exception as e:
            logging.error(f"删除ZIP文件失败 {file_path}: {e}")
    
    response.background = delete_file
    return response

@app.get("/config")
async def get_config():
    """获取当前配置"""
    return config.get_all()

@app.post("/config")
async def update_config(
    rename_with_amount: bool = Form(...),
    watch_dir: str = Form(...),
    ui_port: int = Form(...)
):
    """更新配置"""
    try:
        config.set("rename_with_amount", rename_with_amount)
        config.set("watch_dir", watch_dir)
        config.set("ui_port", ui_port)
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request, credentials: HTTPBasicCredentials = Depends(verify_admin)):
    """管理页面（需要密码验证）"""
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "config": config.get_all()
        }
    )

@app.post("/admin/config")
async def update_system_config(
    credentials: HTTPBasicCredentials = Depends(verify_admin),
    watch_dir: str = Form(...),
    ui_port: int = Form(...),
    admin_password: str = Form(None)  # 可选参数，用于更新管理员密码
):
    """更新系统配置（需要密码验证）"""
    try:
        config.set("watch_dir", watch_dir)
        config.set("ui_port", ui_port)
        
        # 如果提供了新密码，则更新密码哈希
        if admin_password:
            new_password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
            config.set("admin_password_hash", new_password_hash)
            
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@app.post("/admin/watch_config")
async def update_watch_config(
    credentials: HTTPBasicCredentials = Depends(verify_admin),
    watch_rename_with_amount: bool = Form(...)
):
    """更新Watch目录配置"""
    try:
        config.set("watch_rename_with_amount", watch_rename_with_amount)
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@app.post("/user/config")
async def update_user_config(
    rename_with_amount: bool = Form(...)
):
    """更新Web UI用户配置"""
    try:
        # 将Web UI的重命名配置保存为单独的键
        config.set("webui_rename_with_amount", rename_with_amount)
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

def start_web_server():
    """启动 Web 服务器"""
    port = config.get("ui_port", 8080)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 启动文件监控
    observer = start_file_monitor()
    
    try:
        # 启动Web服务器
        start_web_server()
    except KeyboardInterrupt:
        observer.stop()
    observer.join() 