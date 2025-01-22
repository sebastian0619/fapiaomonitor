import os
import uuid
import logging
from pdf_processor import convert_to_image  # 假设该函数支持OFD文件转换为多张图片
from data_extractor import scan_qrcode, extract_information
from file_processor import rename_file

def process_ofd(file_path, tmp_dir, keep_temp_files):
    try:
        logging.debug(f"Processing OFD file: {file_path}")
        image_paths = convert_to_image(file_path, tmp_dir)
    except Exception as e:
        logging.debug(f"Error in converting OFD to image: {e}")
        return
    qr_code_found = False  # 标记是否找到二维码
    for image_path in image_paths:
        try:
            logging.debug(f"Scanning image: {image_path}")
            qrcode_data = scan_qrcode(image_path)
        except Exception as e:
            logging.debug(f"Error in scanning QR code: {e}")
            continue

        if qrcode_data:
            logging.debug(f"QR code found: {qrcode_data}")
            try:
                invoice_number, amount = extract_information(qrcode_data)
            except Exception as e:
                logging.debug(f"Error in extracting information from QR code: {e}")
                continue

            if invoice_number and amount:
                new_file_name = f"[¥{amount}]{invoice_number}.ofd"
                try:
                    rename_file(file_path, new_file_name)
                except Exception as e:
                    logging.debug(f"Error in renaming file: {e}")
                    continue

                qr_code_found = True
                logging.debug(f"Renamed file to: {new_file_name}")
                break  # 找到二维码，中断循环
    if not keep_temp_files:  # 如果不保留临时文件，才删除图片
        try:
            os.remove(image_path)  # 删除处理过的图片
            logging.debug(f"Removed image: {image_path}")
        except Exception as e:
            logging.debug(f"Error in removing image: {e}")
    
    if not qr_code_found:
        # 如果所有图片都未识别到二维码，才打印错误消息
        print(f"No QR code found in any images of the OFD file: {file_path}")
        logging.debug(f"No QR code found in any images of the OFD file: {file_path}")