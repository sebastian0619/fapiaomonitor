import sys
import os
from pdf_processor import convert_to_image, process_special_pdf
from image_processor import crop_image
from data_extractor import scan_qrcode, extract_information, extract_information_from_pdf
from file_processor import ensure_dir, rename_file, clean_up
import logging
from ofd_processor import process_ofd  # 确保你已经创建了这个模块

def toggle_debug_mode(debug_mode):
    if debug_mode:
        logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler(sys.stdout)])
        print("Debug mode enabled.")
    else:
        logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
        print("Debug mode disabled.")

toggle_debug_mode(True)

def process_pdf(file_path, tmp_dir, keep_temp_files):  # 添加 keep_temp_files 参数
    image_paths = convert_to_image(file_path, tmp_dir, pages=[0])  # 假设这个函数接受一个页码列表作为参数
    if image_paths:
        cropped_image_path = crop_image(image_paths[0], tmp_dir)
        qrcode_data = scan_qrcode(cropped_image_path)
        
        if not keep_temp_files:  # 检查 keep_temp_files 参数
            clean_up(*image_paths, cropped_image_path)  # 清理生成的图像文件

        if qrcode_data:
            invoice_number, amount = extract_information_from_pdf(qrcode_data, file_path)
            if invoice_number and amount:
                new_file_name = f"[¥{amount}]{invoice_number}.pdf"
                new_file_path = rename_file(file_path, new_file_name)
                print(f"Processed file: {new_file_path}")
        else:
            process_special_pdf(file_path)

def process_file(file_path, keep_temp_files):  # 添加 keep_temp_files 参数
    tmp_dir = "tmp"
    ensure_dir(tmp_dir)
    
    if file_path.lower().endswith('.ofd'):
        process_ofd(file_path, tmp_dir, keep_temp_files)  # 添加 keep_temp_files 参数
    elif file_path.lower().endswith('.pdf'):
        process_pdf(file_path, tmp_dir, keep_temp_files)  # 添加 keep_temp_files 参数
    else:
        print(f"Unsupported file format: {file_path}")

    if not keep_temp_files:
        # 删除临时目录
        for file_name in os.listdir(tmp_dir):
            file_path = os.path.join(tmp_dir, file_name)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(e)

def extract_amount(filename):
    import re
    # 使用正则表达式提取金额
    match = re.search(r'\[¥([0-9.]+)\]', filename)
    if match:
        return float(match.group(1))
    return 0.0

def sum_invoices(invoice_folder):
    total_sum = 0.0

    # 遍历发票文件夹中的所有文件
    for filename in os.listdir(invoice_folder):
        filepath = os.path.join(invoice_folder, filename)
        if os.path.isfile(filepath):
            # 提取文件名中的金额部分并累加
            amount = extract_amount(filename)
            total_sum += amount

    # 格式化总金额，确保只有两位小数
    formatted_total = f"{total_sum:.2f}"

    # 查找文件夹中的 .txt 文件
    txt_file_found = False
    for filename in os.listdir(invoice_folder):
        if filename.endswith(".txt"):
            old_filepath = os.path.join(invoice_folder, filename)
            new_filepath = os.path.join(invoice_folder, f"{formatted_total}.txt")
            os.rename(old_filepath, new_filepath)
            txt_file_found = True
            break  # Assuming there is only one .txt file to rename

    # 如果没有找到 .txt 文件，则创建一个新的
    if not txt_file_found:
        new_filepath = os.path.join(invoice_folder, f"{formatted_total}.txt")
        with open(new_filepath, 'w') as f:
            f.write(f"Total amount: ¥{formatted_total}\n")

    print(f"Total amount: ¥{formatted_total}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for file_path in sys.argv[1:]:
            process_file(file_path, True)  # 添加 True 作为 keep_temp_files 参数的默认值
        
        invoice_folder = os.path.dirname(sys.argv[1])
        sum_invoices(invoice_folder)
    else:
        print("请提供文件和发票文件夹的路径作为参数。")
