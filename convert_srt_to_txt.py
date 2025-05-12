import os
import re

downloads_path = "./downloads"

def convert_srt_to_txt(srt_path, txt_path):
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # جدا کردن بلاک‌ها
    blocks = content.strip().split("\n\n")

    lines = []
    for block in blocks:
        lines_in_block = block.strip().split("\n")

        # اگر بلاک ساختار درست دارد (حداقل 3 خط: عدد - زمان - متن)
        if len(lines_in_block) >= 3:
            # حذف خطوط اول (شماره) و دوم (تایم‌کد)
            text_lines = lines_in_block[2:]
            text = " ".join(text_lines)
            lines.append(text)

    full_text = " ".join(lines)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(full_text)

    print(f"✅ {os.path.basename(txt_path)} created.")

def process_all_srt_files():
    for file in os.listdir(downloads_path):
        if file.endswith(".srt"):
            base_name = os.path.splitext(file)[0]
            txt_file = os.path.join(downloads_path, f"{base_name}.txt")

            if os.path.exists(txt_file):
                print(f"⏭ Already exists: {txt_file}")
                continue

            srt_file = os.path.join(downloads_path, file)
            try:
                convert_srt_to_txt(srt_file, txt_file)
            except Exception as e:
                print(f"❌ Error processing {file}: {e}")

if __name__ == "__main__":
    process_all_srt_files()
