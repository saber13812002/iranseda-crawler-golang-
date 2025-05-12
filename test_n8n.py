from datetime import datetime
import os

# ساخت زمان فعلی به فرمت دلخواه
now = datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")

# مسیر فایل لاگ
log_dir = os.path.join(os.getcwd(), "logs")
filename = f"log-{timestamp}.txt"
filepath = os.path.join(log_dir, filename)

# نوشتن فایل
with open(filepath, "w") as f:
    f.write(f"n8n test run at {now.strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"✅ File created: {filepath}")
