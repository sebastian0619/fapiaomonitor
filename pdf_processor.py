import fitz
import os
import uuid
import logging
import re

def convert_to_image(file_path, output_dir, pages=None):
    try:
        logging.debug(f"Converting file to image: {file_path}")
        doc = fitz.open(file_path)
        image_paths = []
        # 如果未指定pages，则处理所有页面
        pages_to_process = pages if pages is not None else range(len(doc))
        for page_num in pages_to_process:
            logging.debug(f"Processing page number: {page_num}")
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300)
            output = os.path.join(output_dir, f"{uuid.uuid4()}.png")
            pix.save(output)
            image_paths.append(output)
            logging.debug(f"Saved image: {output}")
            if pages is not None:
                # 如果指定了页面，假设我们只关心这些特定页面
                break
        doc.close()
        return image_paths
    except Exception as e:
        logging.debug(f"Error in convert_to_image: {e}")

def process_special_pdf(file_path):
    try:
        logging.debug(f"Processing special PDF: {file_path}")
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        
        invoice_number_match = re.findall(r"(?<!-\d)\b\d{20}\b|(?<!-\d)\b\d{8}\b", text)
        if invoice_number_match:
            invoice_number = invoice_number_match[0]
            logging.debug(f"Found invoice number: {invoice_number}")
        else:
            return
        
        amount_match = re.findall(r"¥\s*(\d+\.\d+)", text)
        if amount_match:
            amounts = map(float, amount_match)
            max_amount = max(amounts)
            max_amount_str = "{:.2f}".format(max_amount)
            logging.debug(f"Found max amount: {max_amount_str}")
        else:
            return
        
        new_file_name = f"[¥{max_amount_str}]{invoice_number}"
        new_file_path = os.path.join(os.path.dirname(file_path), f"{new_file_name}{os.path.splitext(file_path)[1]}")
        os.rename(file_path, new_file_path)
        logging.debug(f"Renamed file to: {new_file_path}")
    except Exception as e:
        logging.debug(f"Error in process_special_pdf: {e}")