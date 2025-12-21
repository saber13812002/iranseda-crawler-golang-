#!/bin/bash
# check_deploy_status.sh - بررسی وضعیت deploy خودکار

SCRIPT_DIR="/mnt/data/saberprojects/iranseda-crawler-golang-"
cd "$SCRIPT_DIR" || exit 1

echo "🔍 بررسی وضعیت Deploy خودکار..."
echo "========================================="
echo ""

# بررسی Systemd Timer
echo "📋 بررسی Systemd Timer:"
if systemctl list-timers 2>/dev/null | grep -q "iranseda-deploy.timer"; then
    echo "✅ Systemd Timer فعال است"
    echo ""
    systemctl status iranseda-deploy.timer --no-pager -l | head -20
    echo ""
    echo "📊 زمان اجرای بعدی:"
    systemctl list-timers iranseda-deploy.timer --no-pager
    echo ""
    echo "📝 آخرین لاگ‌ها:"
    journalctl -u iranseda-deploy.service --no-pager -n 10 2>/dev/null || echo "   لاگی پیدا نشد"
else
    echo "❌ Systemd Timer فعال نیست"
fi
echo ""

# بررسی Cron
echo "📋 بررسی Cron Jobs:"
if command -v crontab &> /dev/null; then
    CRON_JOBS=$(crontab -l 2>/dev/null | grep -i "deploy.sh" || echo "")
    if [ -n "$CRON_JOBS" ]; then
        echo "✅ Cron Job پیدا شد:"
        echo "$CRON_JOBS"
    else
        echo "❌ Cron Job برای deploy.sh پیدا نشد"
    fi
else
    echo "⚠️  Crontab نصب نیست"
fi
echo ""

# بررسی While Loop
echo "📋 بررسی While Loop (deploy_loop.sh):"
if [ -f "/tmp/deploy_loop.pid" ]; then
    PID=$(cat /tmp/deploy_loop.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ deploy_loop.sh در حال اجرا است (PID: $PID)"
        echo ""
        ps aux | grep -E "deploy_loop|$PID" | grep -v grep
    else
        echo "⚠️  PID file وجود دارد اما پروسه در حال اجرا نیست"
        rm -f /tmp/deploy_loop.pid
    fi
else
    echo "❌ deploy_loop.sh در حال اجرا نیست"
fi
echo ""

# بررسی لاگ‌ها
echo "📋 بررسی لاگ‌ها:"
if [ -f "logs/deploy.log" ]; then
    echo "✅ logs/deploy.log موجود است"
    echo "   آخرین خطوط:"
    tail -5 logs/deploy.log 2>/dev/null | sed 's/^/   /'
else
    echo "⚠️  logs/deploy.log پیدا نشد"
fi

if [ -f "logs/deploy-loop.log" ]; then
    echo ""
    echo "✅ logs/deploy-loop.log موجود است"
    echo "   آخرین خطوط:"
    tail -5 logs/deploy-loop.log 2>/dev/null | sed 's/^/   /'
else
    echo "⚠️  logs/deploy-loop.log پیدا نشد"
fi
echo ""

# خلاصه
echo "========================================="
echo "📊 خلاصه وضعیت:"
echo ""

if systemctl list-timers 2>/dev/null | grep -q "iranseda-deploy.timer"; then
    echo "✅ روش فعال: Systemd Timer"
    echo "   دستورات:"
    echo "   - مشاهده وضعیت: sudo systemctl status iranseda-deploy.timer"
    echo "   - مشاهده لاگ: sudo journalctl -u iranseda-deploy.service -f"
elif [ -f "/tmp/deploy_loop.pid" ] && ps -p "$(cat /tmp/deploy_loop.pid)" > /dev/null 2>&1; then
    echo "✅ روش فعال: While Loop"
    echo "   PID: $(cat /tmp/deploy_loop.pid)"
    echo "   لاگ: logs/deploy-loop.log"
elif crontab -l 2>/dev/null | grep -q "deploy.sh"; then
    echo "✅ روش فعال: Cron"
    echo "   مشاهده: crontab -l"
else
    echo "❌ هیچ روشی فعال نیست!"
    echo ""
    echo "💡 برای راه‌اندازی:"
    echo "   sudo ./setup_auto_deploy.sh"
fi

