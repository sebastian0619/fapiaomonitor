from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
from typing import List
import shutil
from datetime import datetime
import zipfile
from pathlib import Path
import re
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import hashlib
import json

app = FastAPI(title="发票处理系统")

# 配置日志
logging.basicConfig(level=logging.INFO)

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic()

# 简化的配置管理
class Config:
    def __init__(self):
        self.config = {
            "webui_rename_with_amount": True,
            "admin_password_hash": hashlib.sha256("admin".encode()).hexdigest()
        }
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
    
    def get_all(self):
        return self.config.copy()

config = Config()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """验证管理员密码"""
    stored_password_hash = config.get("admin_password_hash")
    provided_password_hash = hashlib.sha256(credentials.password.encode()).hexdigest()
    
    is_correct_username = secrets.compare_digest(credentials.username, "admin")
    is_correct_password = secrets.compare_digest(provided_password_hash, stored_password_hash)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页"""
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
    zip_path = f"/tmp/{zip_filename}"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for info in files_info:
            if info["success"] and info.get("new_path"):
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
        for file in files:
            try:
                # 保存上传的文件到临时目录
                file_path = f"/tmp/{file.filename}"
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                # 处理文件（这里需要实现具体的处理逻辑）
                # TODO: 实现文件处理逻辑
                
                file_info = {
                    "filename": file.filename,
                    "success": True,  # 这里需要根据实际处理结果设置
                    "new_name": file.filename,  # 这里需要根据实际处理结果设置
                    "new_path": file_path,
                    "amount": "0.00"  # 这里需要根据实际处理结果设置
                }
                
                results.append(file_info)
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

@app.get("/download/{filename}")
async def download_file(filename: str):
    """下载处理后的ZIP文件"""
    file_path = f"/tmp/{filename}"
    if not os.path.exists(file_path):
        return JSONResponse(
            status_code=404,
            content={"error": "文件不存在"}
        )
    
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=filename
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
    admin_password: str = Form(None)
):
    """更新系统配置（需要密码验证）"""
    try:
        if admin_password:
            new_password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
            config.set("admin_password_hash", new_password_hash)
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
        config.set("webui_rename_with_amount", rename_with_amount)
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        ) 