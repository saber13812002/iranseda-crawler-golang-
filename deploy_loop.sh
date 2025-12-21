#!/bin/bash
# deploy_loop.sh - اجرای خودکار با while loop
# Usage: ./deploy_loop.sh
# برای اجرا در background: nohup ./deploy_loop.sh > /dev/null 2>&1 &

SCRIPT_DIR="/mnt/data/saberprojects/iranseda-crawler-golang-"
LOG_FILE="$SCRIPT_DIR/logs/deploy-loop.log"
INTERVAL_HOURS=3
INTERVAL_SECONDS=$((INTERVAL_HOURS * 3600))

# تغییر به دایرکتوری پروژه
cd "$SCRIPT_DIR" || {
    echo "❌ خطا: نمی‌توانم به دایرکتوری $SCRIPT_DIR بروم"
    exit 1
}

# ایجاد پوشه logs
mkdir -p "$SCRIPT_DIR/logs"

# فعال‌سازی virtualenv اگر وجود دارد
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "🚀 شروع حلقه deploy (هر $INTERVAL_HOURS ساعت)" | tee -a "$LOG_FILE"
echo "📝 لاگ‌ها در: $LOG_FILE" | tee -a "$LOG_FILE"
echo "⏹️  برای توقف: kill \$(cat /tmp/deploy_loop.pid)" | tee -a "$LOG_FILE"
echo ""

# ذخیره PID
echo $$ > /tmp/deploy_loop.pid

# تابع cleanup
cleanup() {
    echo "" | tee -a "$LOG_FILE"
    echo "🛑 دریافت سیگنال توقف. خروج..." | tee -a "$LOG_FILE"
    rm -f /tmp/deploy_loop.pid
    exit 0
}

# ثبت signal handlers
trap cleanup SIGINT SIGTERM

# حلقه اصلی
while true; do
    echo "=========================================" | tee -a "$LOG_FILE"
    echo "⏰ اجرا در: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"
    
    # اجرای deploy.sh
    /bin/bash "$SCRIPT_DIR/deploy.sh" >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ اجرا با موفقیت تمام شد" | tee -a "$LOG_FILE"
    else
        echo "❌ خطا در اجرا (کد خروج: $EXIT_CODE)" | tee -a "$LOG_FILE"
    fi
    
    echo "" | tee -a "$LOG_FILE"
    echo "⏳ منتظر $INTERVAL_HOURS ساعت تا اجرای بعدی..." | tee -a "$LOG_FILE"
    echo "   اجرای بعدی: $(date -d "+$INTERVAL_HOURS hours" '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # انتظار
    sleep "$INTERVAL_SECONDS"
done

