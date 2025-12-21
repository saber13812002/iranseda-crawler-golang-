#!/bin/bash
# test_deploy_quick.sh - تست سریع یک باره deploy

SCRIPT_DIR="/mnt/data/saberprojects/iranseda-crawler-golang-"
cd "$SCRIPT_DIR" || exit 1

echo "🧪 تست سریع Deploy (یک باره)"
echo "========================================="
echo ""

# ایجاد پوشه logs
mkdir -p logs

# اجرای deploy.sh
echo "🚀 اجرای deploy.sh..."
echo ""

/bin/bash deploy.sh "test quick deploy - $(date '+%Y-%m-%d %H:%M:%S')"

EXIT_CODE=$?

echo ""
echo "========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ تست موفق بود!"
else
    echo "❌ تست ناموفق بود (کد خروج: $EXIT_CODE)"
fi
echo ""

