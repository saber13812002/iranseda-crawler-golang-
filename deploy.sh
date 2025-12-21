#!/bin/bash
# اسکریپت خودکار برای commit، push و generate سایت
# Usage: ./deploy.sh [commit_message]

# در صورت خطا متوقف نشود، فقط خطا را گزارش کند
set +e

# پیام commit (پیش‌فرض یا از آرگومان)
COMMIT_MSG=${1:-"new srt files"}

echo "🚀 شروع فرآیند deploy..."
echo ""

# بررسی وجود تغییرات
if [ -z "$(git status --porcelain)" ]; then
    echo "⚠️  هیچ تغییری برای commit وجود ندارد"
    echo "⏭️  ادامه با generate سایت..."
else
    echo "📝 اضافه کردن تغییرات به git..."
    git add .
    GIT_ADD_EXIT=$?
    
    if [ $GIT_ADD_EXIT -ne 0 ]; then
        echo "❌ خطا در git add"
    else
        echo "💾 ایجاد commit با پیام: '$COMMIT_MSG'"
        git commit -m "$COMMIT_MSG"
        GIT_COMMIT_EXIT=$?
        
        if [ $GIT_COMMIT_EXIT -ne 0 ]; then
            echo "❌ خطا در git commit"
        else
            echo "📤 ارسال تغییرات به GitHub..."
            git push
            GIT_PUSH_EXIT=$?
            
            if [ $GIT_PUSH_EXIT -ne 0 ]; then
                echo "❌ خطا در git push"
            else
                echo "✅ تغییرات با موفقیت push شدند"
            fi
        fi
    fi
    echo ""
fi

# تنظیم متغیرهای محیطی برای server
echo "🔧 تنظیم متغیرهای محیطی..."
export ENVIRONMENT=server
export DB_HOST=192.168.2.160
export DB_PORT=3306
export DB_USER=n8nuser
export DB_PASS='StrongPassword123!'
export DB_NAME=radio
export GITHUB_USER=saber13812002
export GITHUB_REPO=iranseda-crawler-golang-
export GITHUB_BRANCH=download-db

# اجرای generate_site.py
echo "🌐 تولید صفحات وب..."
python3 generate_site.py

echo ""
echo "✅ فرآیند deploy با موفقیت انجام شد!"

