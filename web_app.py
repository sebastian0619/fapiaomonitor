from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
import logging
from typing import List
import shutil
from datetime import datetime
from config_manager import config
from pdf_processor import process_special_pdf
from ofd_processor import process_ofd

app = FastAPI(title="发票处理系统")

# 创建必要的目录
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": config.get_all()
        }
    )

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """处理上传的文件"""
    results = []
    for file in files:
        try:
            # 保存上传的文件
            file_path = os.path.join("uploads", file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 处理文件
            ext = os.path.splitext(file.filename)[1].lower()
            if ext == '.pdf':
                result = process_special_pdf(file_path)
            elif ext == '.ofd':
                result = process_ofd(file_path, "tmp", False)
            else:
                result = None
                
            results.append({
                "filename": file.filename,
                "success": result is not None,
                "new_name": os.path.basename(result) if result else None
            })
            
        except Exception as e:
            logging.error(f"处理文件失败 {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return JSONResponse(content={"results": results})

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

def start_web_server():
    """启动 Web 服务器"""
    port = config.get("ui_port", 8080)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start_web_server() 