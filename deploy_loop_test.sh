#!/bin/bash
# deploy_loop_test.sh - تست while loop با interval کوتاه (1 دقیقه)

SCRIPT_DIR="/mnt/data/saberprojects/iranseda-crawler-golang-"
LOG_FILE="$SCRIPT_DIR/logs/deploy-loop-test.log"
INTERVAL_SECONDS=60  # 1 دقیقه برای تست

cd "$SCRIPT_DIR" || exit 1

mkdir -p logs

echo "🧪 تست While Loop با interval 1 دقیقه"
echo "========================================="
echo "📝 لاگ در: $LOG_FILE"
echo "⏹️  برای توقف: Ctrl+C"
echo ""

# ذخیره PID
echo $$ > /tmp/deploy_loop_test.pid

# تابع cleanup
cleanup() {
    echo "" | tee -a "$LOG_FILE"
    echo "🛑 توقف تست..." | tee -a "$LOG_FILE"
    rm -f /tmp/deploy_loop_test.pid
    exit 0
}

trap cleanup SIGINT SIGTERM

# حلقه تست (5 بار)
COUNT=0
MAX_TESTS=5

while [ $COUNT -lt $MAX_TESTS ]; do
    COUNT=$((COUNT + 1))
    
    echo "=========================================" | tee -a "$LOG_FILE"
    echo "🧪 تست شماره $COUNT از $MAX_TESTS" | tee -a "$LOG_FILE"
    echo "⏰ زمان: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"
    
    # اجرای deploy.sh
    /bin/bash "$SCRIPT_DIR/deploy.sh" "test loop #$COUNT" >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ تست $COUNT موفق بود" | tee -a "$LOG_FILE"
    else
        echo "❌ تست $COUNT ناموفق (کد: $EXIT_CODE)" | tee -a "$LOG_FILE"
    fi
    
    echo "" | tee -a "$LOG_FILE"
    
    if [ $COUNT -lt $MAX_TESTS ]; then
        echo "⏳ منتظر 1 دقیقه..." | tee -a "$LOG_FILE"
        sleep "$INTERVAL_SECONDS"
    fi
done

echo "✅ تست‌ها تمام شد!" | tee -a "$LOG_FILE"
rm -f /tmp/deploy_loop_test.pid

