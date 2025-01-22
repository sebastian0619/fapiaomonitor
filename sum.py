import os
import re
import sys

def extract_amount(filename):
    # 使用正则表达式提取金额
    match = re.search(r'\[¥([0-9.]+)\]', filename)
    if match:
        return float(match.group(1))
    return 0.0

def main(invoice_folder):
    total_sum = 0.0

    # 检查发票文件夹是否存在
    if not os.path.isdir(invoice_folder):
        print("Invoice folder does not exist.")
        return

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
    if len(sys.argv) != 2:
        print("Usage: python sum_invoices.py <path_to_invoice_folder>")
    else:
        invoice_folder = sys.argv[1]
        main(invoice_folder)
