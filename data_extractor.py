from PIL import Image
import re
import fitz  # PyMuPDF, 用于读取PDF文件
from pyzbar.pyzbar import decode
import logging

def scan_qrcode(image_path):
    """
    使用 pyzbar 扫描二维码
    """
    try:
        image = Image.open(image_path)
        decoded_objects = decode(image)
        if decoded_objects:
            qr_data = decoded_objects[0].data.decode('utf-8')
            logging.debug(f"成功识别二维码: {qr_data}")
            return qr_data
        return None
    except Exception as e:
        logging.debug(f"扫描二维码失败: {e}")
        return None

def extract_information(data_str):
    """
    从二维码数据中提取发票号码和金额
    """
    invoice_number = None
    amount = None
    
    try:
        # 提取发票号码（支持20位和8位格式）
        invoice_match = re.search(r"\b\d{20}\b|\b\d{8}\b", data_str)
        if invoice_match:
            invoice_number = invoice_match.group(0)
            logging.debug(f"提取到发票号码: {invoice_number}")
        
        # 提取金额（支持多种格式）
        amount_patterns = [
            r"(\d+\.\d+)(?=,)",  # 标准格式：数字.数字,
            r"金额[:：]\s*(\d+\.\d+)",  # 带"金额"标识
            r"¥\s*(\d+\.\d+)",  # 带货币符号
            r"[^\d](\d+\.\d+)[^\d]"  # 通用数字格式
        ]
        
        for pattern in amount_patterns:
            amount_match = re.search(pattern, data_str)
            if amount_match:
                amount = round(float(amount_match.group(1)), 2)
                amount = "{:.2f}".format(amount)
                logging.debug(f"提取到金额: {amount}")
                break
    except Exception as e:
        logging.debug(f"提取信息时出错: {e}")
    
    return invoice_number, amount

def extract_information_from_pdf(data_str, file_path):
    """
    从PDF文件中提取发票信息，包括二维码数据和文本内容
    """
    # 首先从二维码数据中提取信息
    invoice_number, amount = extract_information(data_str)

    # 如果发票号码存在但金额未找到，或发票号码是8位格式，则尝试从PDF文本中提取
    if invoice_number and (not amount or len(invoice_number) == 8):
        text = ""
        try:
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text()
            doc.close()
            
            # 从文本中提取所有金额
            amount_matches = re.findall(r"¥\s*(\d+\.\d+)", text)
            if amount_matches:
                amounts = [float(x) for x in amount_matches]
                max_amount = max(amounts)  # 使用最大金额
                amount = "{:.2f}".format(max_amount)
                logging.debug(f"从PDF提取到最大金额: {amount}")
        except Exception as e:
            logging.debug(f"从PDF提取信息时出错: {e}")
    
    return invoice_number, amount