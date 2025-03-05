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
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        if file_path.lower().endswith(('.pdf', '.ofd')):
            try:
                relative_path = os.path.relpath(file_path, config.get("watch_dir", "./watch"))
                logging.info(f"检测到新文件: {relative_path}")
                
                ext = os.path.splitext(file_path)[1].lower()
                
                # 使用Watch目录的配置
                config.set("rename_with_amount", config.get("watch_rename_with_amount", False))
                
                if ext == '.pdf':
                    process_special_pdf(file_path)
                elif ext == '.ofd':
                    process_ofd(file_path, "tmp", False)
                    
            except Exception as e:
                logging.error(f"处理文件失败 {file_path}: {e}")
            finally:
                # 恢复原始配置
                config.set("rename_with_amount", config.get("webui_rename_with_amount", False))

def start_file_monitor():
    """启动文件监控"""
    watch_dir = config.get("watch_dir", "./watch")
    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir, exist_ok=True)
        
    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=True)
    observer.start()
    
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
                
                # 记录文件上传时间（用于自动清理）
                file_upload_times[file_path] = datetime.now()
                
                # 处理文件
                ext = os.path.splitext(file.filename)[1].lower()
                result = None
                amount = None
                if ext == '.pdf':
                    result = process_special_pdf(file_path)
                    if result:
                        try:
                            amount_match = re.search(r'\[¥(\d+\.\d{2})\]', os.path.basename(result))
                            if amount_match:
                                amount = amount_match.group(1)
                        except Exception as e:
                            logging.warning(f"提取金额失败: {e}")
                elif ext == '.ofd':
                    result = process_ofd(file_path, "tmp", False)
                    if result:
                        try:
                            amount_match = re.search(r'\[¥(\d+\.\d{2})\]', os.path.basename(result))
                            if amount_match:
                                amount = amount_match.group(1)
                        except Exception as e:
                            logging.warning(f"提取金额失败: {e}")
                
                # 准备结果
                success = result is not None
                new_name = os.path.basename(result) if success else None
                results.append({
                    "filename": file.filename,
                    "success": success,
                    "amount": amount,
                    "new_name": new_name,
                    "new_path": result if success else None
                })
                
                if success:
                    processed_files.append(result)
                
            except Exception as e:
                logging.error(f"处理文件失败: {e}")
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": str(e)
                })
                continue
        
        # 创建ZIP文件（如果有成功处理的文件）
        if processed_files:
            zip_path = create_zip_file([r for r in results if r["success"]])
            return {"success": True, "results": results, "download": zip_path}
        
        return {"success": True, "results": results}
    
    except Exception as e:
        logging.error(f"处理上传文件时出错: {e}")
        return {"success": False, "error": str(e)}
    finally:
        # 恢复原始配置
        config.set("rename_with_amount", config.get("webui_rename_with_amount", False))

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