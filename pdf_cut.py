import argparse
from pypdf import PdfReader, PdfWriter

def uniform_crop(input_file, output_file, crop_top_pt, crop_bottom_pt,
                 modify_media=False, min_height=50):
    reader = PdfReader(input_file)
    writer = PdfWriter()
    total = len(reader.pages)

    for i, page in enumerate(reader.pages, start=1):
        media = page.mediabox
        x0, y0 = float(media.left), float(media.bottom)
        x1, y1 = float(media.right), float(media.top)

        new_bottom = y0 + crop_bottom_pt
        new_top = y1 - crop_top_pt

        if new_top - new_bottom < min_height:
            print(f"[WARN] 第{i}页裁剪后高度 < {min_height}pt，跳过。")
        else:
            page.cropbox.lower_left = (x0, new_bottom)
            page.cropbox.upper_right = (x1, new_top)
            if modify_media:
                page.mediabox.lower_left = (x0, new_bottom)
                page.mediabox.upper_right = (x1, new_top)

        writer.add_page(page)

    with open(output_file, "wb") as f:
        writer.write(f)
    print(f"[OK] 处理完成: {output_file} (共{total}页)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="对扫描PDF统一裁剪上下空白（均匀页距）。")
    parser.add_argument("input", help="输入 PDF 文件")
    parser.add_argument("output", help="输出 PDF 文件")
    parser.add_argument("--top", type=float, required=True, help="裁掉顶部空白 pt 数")
    parser.add_argument("--bottom", type=float, required=True, help="裁掉底部空白 pt 数")
    parser.add_argument("--modify-media", action="store_true",
                        help="同时修改 MediaBox（真正缩短页面高度）")
    parser.add_argument("--min-height", type=float, default=50,
                        help="裁剪后最小允许页高（pt）防止过度裁剪")
    args = parser.parse_args()

    uniform_crop(args.input, args.output,
                 crop_top_pt=args.top,
                 crop_bottom_pt=args.bottom,
                 modify_media=args.modify_media,
                 min_height=args.min_height)


##python pdf_uniform_crop.py in.pdf out.pdf --top 60 --bottom 80