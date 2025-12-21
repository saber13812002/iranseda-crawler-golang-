#!/bin/bash
# test_deploy.sh - تست سریع deploy با interval کوتاه

SCRIPT_DIR="/mnt/data/saberprojects/iranseda-crawler-golang-"
cd "$SCRIPT_DIR" || exit 1

echo "🧪 تست Deploy با interval کوتاه (1 دقیقه)"
echo "========================================="
echo ""
echo "این تست deploy.sh را هر 1 دقیقه اجرا می‌کند تا مطمئن شویم کار می‌کند"
echo "برای توقف: Ctrl+C"
echo ""

# ایجاد پوشه logs
mkdir -p logs

# فایل تست
TEST_LOG="logs/test-deploy.log"

echo "📝 لاگ تست در: $TEST_LOG"
echo ""

# شمارنده
COUNT=0
MAX_TESTS=3  # تعداد تست‌ها

while [ $COUNT -lt $MAX_TESTS ]; do
    COUNT=$((COUNT + 1))
    
    echo "=========================================" | tee -a "$TEST_LOG"
    echo "🧪 تست شماره $COUNT از $MAX_TESTS" | tee -a "$TEST_LOG"
    echo "⏰ زمان: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$TEST_LOG"
    echo "=========================================" | tee -a "$TEST_LOG"
    
    # اجرای deploy.sh
    /bin/bash deploy.sh "test deploy #$COUNT" >> "$TEST_LOG" 2>&1
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ تست $COUNT موفق بود" | tee -a "$TEST_LOG"
    else
        echo "❌ تست $COUNT ناموفق بود (کد خروج: $EXIT_CODE)" | tee -a "$TEST_LOG"
    fi
    
    echo "" | tee -a "$TEST_LOG"
    
    # اگر آخرین تست نیست، منتظر بمان
    if [ $COUNT -lt $MAX_TESTS ]; then
        echo "⏳ منتظر 1 دقیقه تا تست بعدی..." | tee -a "$TEST_LOG"
        sleep 60
    fi
done

echo ""
echo "✅ تست‌ها تمام شد!"
echo "📝 نتایج در: $TEST_LOG"
echo ""
echo "برای مشاهده لاگ:"
echo "  tail -f $TEST_LOG"

