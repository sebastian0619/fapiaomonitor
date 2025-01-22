import fitz
import os
import uuid
import logging
import re
from config_manager import config

def convert_to_image(file_path, output_dir, pages=None):
    """将PDF文件转换为图片"""
    try:
        logging.debug(f"正在转换PDF为图片: {file_path}")
        doc = fitz.open(file_path)
        image_paths = []
        # 如果未指定pages，则处理所有页面
        pages_to_process = pages if pages is not None else range(len(doc))
        for page_num in pages_to_process:
            logging.debug(f"处理页面: {page_num}")
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300)
            output = os.path.join(output_dir, f"{uuid.uuid4()}.png")
            pix.save(output)
            image_paths.append(output)
            logging.debug(f"已保存图片: {output}")
            if pages is not None:
                # 如果指定了页面，假设我们只关心这些特定页面
                break
        doc.close()
        return image_paths
    except Exception as e:
        logging.error(f"转换PDF为图片时出错: {e}")
        return []

def create_new_filename(invoice_number, amount=None, original_path=None):
    """根据配置创建新文件名"""
    ext = os.path.splitext(original_path)[1] if original_path else '.pdf'
    
    # 检查是否需要包含金额
    if config.get('rename_with_amount', True) and amount:
        return f"[¥{amount}]{invoice_number}{ext}"
    return f"{invoice_number}{ext}"

def process_special_pdf(file_path):
    """处理特殊PDF文件（无法从二维码获取信息时）"""
    try:
        logging.debug(f"处理特殊PDF文件: {file_path}")
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        
        # 提取发票号码
        invoice_number_match = re.findall(r"(?<!-\d)\b\d{20}\b|(?<!-\d)\b\d{8}\b", text)
        if not invoice_number_match:
            logging.debug("未找到发票号码")
            return None
        invoice_number = invoice_number_match[0]
        logging.debug(f"找到发票号码: {invoice_number}")
        
        # 提取金额
        amount_str = None
        amount_match = re.findall(r"¥\s*(\d+\.\d+)", text)
        if amount_match:
            amounts = list(map(float, amount_match))
            max_amount = max(amounts)
            amount_str = "{:.2f}".format(max_amount)
            logging.debug(f"找到最大金额: {amount_str}")
        
        # 创建新文件名（即使没有找到金额也继续处理）
        new_file_name = create_new_filename(invoice_number, amount_str, file_path)
        new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
        
        # 处理文件名冲突
        counter = 1
        while os.path.exists(new_file_path):
            base_name = os.path.splitext(new_file_name)[0]
            ext = os.path.splitext(new_file_name)[1]
            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{counter}{ext}")
            counter += 1
        
        os.rename(file_path, new_file_path)
        logging.info(f"文件重命名为: {new_file_path}")
        return new_file_path
    except Exception as e:
        logging.error(f"处理PDF文件时出错: {e}")
        return None