from datetime import datetime

now = datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")
filename = f"/home/n8n/logs/log-{timestamp}.txt"

with open(filename, "w") as f:
    f.write(f"n8n test run at {now.strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"✅ File created: {filename}")
