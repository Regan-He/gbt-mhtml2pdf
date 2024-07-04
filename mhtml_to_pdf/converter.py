#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import base64
import os
import re
import shutil
import sys
import tempfile
from email.parser import BytesParser
from email.policy import default

from bs4 import BeautifulSoup
from PIL import Image
from reportlab.pdfgen import canvas

app_name = "mhtml-to-pdf"
# 这是GB/T文档中小图片的宽度和高度，这是固定值，至少目前看过的所有GB/T文档都是这种格式
small_pic_width = 119
small_pic_height = 168


def read_mhtml_content(file_path):
    with open(file_path, "rb") as file:
        return file.read()


def extract_html_from_mhtml(mhtml_content):
    parser = BytesParser(policy=default)
    msg = parser.parsebytes(mhtml_content)

    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True)


def extract_images_from_mhtml(mhtml_content, output_dir):
    image_names = []
    parser = BytesParser(policy=default)
    msg = parser.parsebytes(mhtml_content)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for part in msg.walk():
        if part.get_content_type() == "application/octet-stream" and part["Content-Transfer-Encoding"] == "base64":
            image_name = part["Content-Location"].split("fileName=")[1]
            image_data = base64.b64decode(part.get_payload())
            image_names.append(image_name)
            image_path = os.path.join(output_dir, image_name)
            with open(image_path, "wb") as image_file:
                image_file.write(image_data)

    return image_names


def convert_to_pdf(pages, output_pdf_path):
    c = canvas.Canvas(output_pdf_path)
    for page_image in pages:
        try:
            c.setPageSize((page_image.width, page_image.height))
            c.drawInlineImage(page_image, 0, 0, width=page_image.width, height=page_image.height)
            c.showPage()
        except Exception as e:
            print(f"Error while converting page to PDF: {e}")
            sys.exit(1)
    c.save()


def extract_size(style, attribute):
    size = re.search(rf"{attribute}: (\d+)px", style)
    return int(size.group(1)) if size else 0


def extract_image_info(style):
    bg_image_part = re.search(rf"url\((.*?)\)", style)
    bg_image_url = bg_image_part.group(1) if bg_image_part else None

    position = re.search(rf"background-position: (-?\d+)px (-?\d+)px", style)
    crop_x = abs(int(position.group(1)))
    crop_y = abs(int(position.group(2)))

    return bg_image_url, crop_x, crop_y


def create_page_image(page, opened_images):
    page_width = extract_size(page["style"], "width")
    page_height = extract_size(page["style"], "height")

    page_image = Image.new("RGBA", (page_width, page_height), (255, 255, 255, 0))

    page_spans = page.find_all("span", class_=lambda x: x and x.startswith("pdfImg-"))
    for span in page_spans:
        col, row = [int(num) for num in span["class"][0].split("-")[1:]]
        x_pos = col * small_pic_width
        y_pos = row * small_pic_height

        span_style = span["style"]
        bg_image_url, crop_x, crop_y = extract_image_info(span_style)
        if not bg_image_url:
            continue

        image_name = bg_image_url.split("fileName=")[-1].strip('"').strip("'")

        if image_name in opened_images.keys():
            source_image = opened_images[image_name]
            component_image = source_image.crop(
                box=(
                    crop_x,
                    crop_y,
                    crop_x + small_pic_width,
                    crop_y + small_pic_height,
                )
            )
            page_image.paste(component_image, (x_pos, y_pos))
        else:
            print(f"Image {image_name} not found in extracted images.")

    return page_image


def parse_page_components(html_content, image_names, image_temp_directory):
    soup = BeautifulSoup(html_content, "html.parser")
    pages = soup.find_all("div", class_="page")
    opened_images = {
        image_name: Image.open(os.path.join(image_temp_directory, image_name)).convert("RGBA")
        for image_name in image_names
    }
    page_images = [create_page_image(page, opened_images) for page in pages]
    return page_images


def generate_output_filename(origin_file_name):
    origin_name = os.path.basename(origin_file_name)
    output_file_name = os.path.splitext(origin_name)[0] + ".pdf"
    return output_file_name


def convert_mhtml_to_pdf(mhtml_path, output_pdf_path, image_temp_directory):
    mhtml_content = read_mhtml_content(mhtml_path)
    html_content = extract_html_from_mhtml(mhtml_content)
    image_names = extract_images_from_mhtml(mhtml_content, image_temp_directory)
    pages = parse_page_components(html_content, image_names, image_temp_directory)
    convert_to_pdf(pages, output_pdf_path)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Convert MHTML to PDF.",
        epilog="Examples:\n"
        f"  {app_name} -y -m input.mhtml -o /path/to/output.pdf\n\toutput file: /path/to/output.pdf\n"
        f"  {app_name} -y -m input.mhtml -d /path/to/\n\toutput file: /path/to/input.pdf\n"
        f"  {app_name} -y -m input.mhtml -d /path/to/ -n output.pdf\n\toutput file: /path/to/output.pdf\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,  # 保持 epilog 文本格式
    )

    parser.add_argument("-m", "--mhtml", required=True, help="The path to the input MHTML file.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-d",
        "--output-dir",
        help="Specifies the directory where the PDF file is stored.",
    )
    parser.add_argument(
        "-n",
        "--filename",
        help="Specify the PDF file name (used with --output-dir).",
    )
    group.add_argument("-o", "--output-file", help="Specifies the PDF file name to use")
    parser.add_argument("-i", action="store_true", help="Prompt before every overwrite.")
    parser.add_argument("-y", action="store_true", help="Automatically answer yes for all questions.")

    args = parser.parse_args()

    if args.filename and args.output_file:
        parser.error("--filename (-n) and --output-file (-o) are mutually exclusive.")

    if args.filename and not args.output_dir:
        parser.error("--filename (-n) requires --output-dir (-d).")

    return args


def main():
    args = parse_arguments()
    orig_mhtml = os.path.abspath(args.mhtml)
    if not os.path.isfile(orig_mhtml):
        print(f"File {orig_mhtml} does not exist.")
        sys.exit(1)

    output_path = ""
    if args.output_file:
        output_pdf_path = os.path.abspath(args.output_file)
        output_path = os.path.dirname(output_pdf_path)
    elif args.output_dir:
        output_path = os.path.abspath(args.output_dir)
        pdf_file_name = args.filename if args.filename else generate_output_filename(orig_mhtml)
        output_pdf_path = os.path.join(output_path, pdf_file_name)

    if not os.path.exists(output_path):
        print(f"Directory {output_path} does not exist.")
        sys.exit(1)

    if os.path.exists(output_pdf_path):
        if os.path.isdir(output_pdf_path):
            print(f"{output_pdf_path} is a directory.")
            sys.exit(1)
        if args.i or not args.y:
            overwrite = input(f"File {output_pdf_path} already exists, do you want to overwrite it？(y/n): ")
            if overwrite.lower() != "y":
                print("Operation cancelled.")
                exit(0)

    if args.i or not args.y:
        continue_answer = input(f"Convert {orig_mhtml} to {output_pdf_path}? (y/n): ")
        if continue_answer.lower() != "y":
            print("Operation cancelled.")
            exit(0)

    image_temp_directory = tempfile.mkdtemp()
    try:
        convert_mhtml_to_pdf(orig_mhtml, output_pdf_path, image_temp_directory)
    finally:
        shutil.rmtree(image_temp_directory)


if __name__ == "__main__":
    main()
