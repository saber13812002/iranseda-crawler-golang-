#!/bin/bash
# setup_auto_deploy.sh - راه‌اندازی خودکار deploy
# این اسکریپت بهترین روش را انتخاب می‌کند

SCRIPT_DIR="/mnt/data/saberprojects/iranseda-crawler-golang-"
cd "$SCRIPT_DIR" || exit 1

echo "🔍 بررسی روش‌های موجود برای اجرای خودکار..."
echo ""

# بررسی systemd
if command -v systemctl &> /dev/null && systemctl is-system-running &> /dev/null; then
    echo "✅ Systemd پیدا شد"
    echo ""
    echo "📋 راه‌اندازی با Systemd Timer..."
    
    # کپی فایل‌های service و timer
    sudo cp iranseda-deploy.service /etc/systemd/system/
    sudo cp iranseda-deploy.timer /etc/systemd/system/
    
    # reload و enable
    sudo systemctl daemon-reload
    sudo systemctl enable iranseda-deploy.timer
    sudo systemctl start iranseda-deploy.timer
    
    echo ""
    echo "✅ Systemd Timer راه‌اندازی شد!"
    echo ""
    echo "📊 وضعیت:"
    sudo systemctl status iranseda-deploy.timer --no-pager -l
    
    echo ""
    echo "📝 دستورات مفید:"
    echo "   مشاهده وضعیت: sudo systemctl status iranseda-deploy.timer"
    echo "   مشاهده لاگ: sudo journalctl -u iranseda-deploy.service -f"
    echo "   توقف: sudo systemctl stop iranseda-deploy.timer"
    echo "   شروع: sudo systemctl start iranseda-deploy.timer"
    
elif command -v crontab &> /dev/null; then
    echo "✅ Crontab پیدا شد"
    echo ""
    echo "📋 راه‌اندازی با Cron..."
    
    # بررسی وجود cron job
    if crontab -l 2>/dev/null | grep -q "deploy.sh"; then
        echo "⚠️  یک cron job برای deploy.sh قبلاً وجود دارد"
        read -p "آیا می‌خواهید آن را جایگزین کنید؟ (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ لغو شد"
            exit 1
        fi
    fi
    
    # اضافه کردن cron job
    (crontab -l 2>/dev/null | grep -v "deploy.sh"; echo "0 */3 * * * cd $SCRIPT_DIR && /bin/bash deploy.sh >> $SCRIPT_DIR/logs/deploy.log 2>&1") | crontab -
    
    echo "✅ Cron job اضافه شد!"
    echo ""
    echo "📋 Cron jobs فعلی:"
    crontab -l
    
else
    echo "⚠️  Systemd و Crontab پیدا نشد"
    echo ""
    echo "📋 استفاده از روش While Loop..."
    echo ""
    echo "برای اجرا در background:"
    echo "  nohup ./deploy_loop.sh > /dev/null 2>&1 &"
    echo ""
    echo "یا با screen:"
    echo "  screen -S deploy"
    echo "  ./deploy_loop.sh"
    echo "  # سپس Ctrl+A سپس D برای detach"
    echo ""
    echo "برای توقف:"
    echo "  kill \$(cat /tmp/deploy_loop.pid)"
    echo ""
    read -p "آیا می‌خواهید الان deploy_loop.sh را اجرا کنید؟ (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        chmod +x deploy_loop.sh
        nohup ./deploy_loop.sh > /dev/null 2>&1 &
        echo "✅ deploy_loop.sh در background اجرا شد (PID: $!)"
        echo "📝 لاگ‌ها در: $SCRIPT_DIR/logs/deploy-loop.log"
    fi
fi

echo ""
echo "✅ راه‌اندازی کامل شد!"

