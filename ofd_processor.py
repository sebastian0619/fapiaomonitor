import os
import uuid
import logging
import re
from pdf_processor import convert_to_image, create_new_filename
from data_extractor import scan_qrcode, extract_information
from config_manager import config

def process_ofd(file_path, tmp_dir, keep_temp_files=False):
    """处理 OFD 文件"""
    image_paths = []
    try:
        logging.debug(f"处理OFD文件: {file_path}")
        image_paths = convert_to_image(file_path, tmp_dir)
        if not image_paths:
            logging.error(f"转换OFD为图片失败: {file_path}")
            return None
            
        for image_path in image_paths:
            try:
                logging.debug(f"扫描图片: {image_path}")
                qrcode_data = scan_qrcode(image_path)
                
                if qrcode_data:
                    logging.debug(f"找到二维码数据: {qrcode_data}")
                    invoice_number, amount = extract_information(qrcode_data)
                    
                    if invoice_number:
                        # 创建新文件名（即使没有金额也继续处理）
                        new_file_name = create_new_filename(invoice_number, amount, file_path)
                        new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
                        
                        # 处理文件名冲突
                        counter = 1
                        while os.path.exists(new_file_path):
                            base_name = os.path.splitext(new_file_name)[0]
                            ext = os.path.splitext(new_file_name)[1]
                            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{counter}{ext}")
                            counter += 1
                        
                        # 重命名文件
                        os.rename(file_path, new_file_path)
                        logging.info(f"文件重命名为: {new_file_path}")
                        
                        # 清理临时文件并返回
                        if not keep_temp_files:
                            clean_up_images(image_paths)
                        return new_file_path
            except Exception as e:
                logging.error(f"处理图片时出错 {image_path}: {e}")
                continue
        
        # 如果没有找到有效的二维码数据
        logging.warning(f"未在OFD文件中找到有效的二维码数据: {file_path}")
        return None
        
    except Exception as e:
        logging.error(f"处理OFD文件时出错: {e}")
        return None
    finally:
        # 确保清理临时文件
        if not keep_temp_files:
            clean_up_images(image_paths)

def clean_up_images(image_paths):
    """清理临时图片文件"""
    for image_path in image_paths:
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                logging.debug(f"已删除临时图片: {image_path}")
        except Exception as e:
            logging.error(f"删除临时图片失败 {image_path}: {e}")

def extract_text_from_ofd(file_path):
    """从OFD文件中提取文本（如果需要）"""
    # TODO: 实现OFD文本提取功能
    # 这个功能可能在未来需要，用于处理无法从二维码获取信息的情况
    pass