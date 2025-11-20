# iranseda-crawler-golang-

## 🌐 Live Website / وب‌سایت زنده

**🔗 [View Live Website - مشاهده وب‌سایت زنده](https://saber13812002.github.io/iranseda-crawler-golang-/index.html)**

### What you'll find / آنچه خواهید یافت:

**English:**
- 📻 **Complete Radio Program Archive** - Browse 28+ radio programs from IranSeda
- 📊 **Interactive Statistics** - Sortable table showing program counts, subtitle availability, and date ranges
- 🎵 **Direct Audio Links** - Access original MP3 files from IranSeda website
- 📝 **Transcripts & Subtitles** - Download both raw and cleaned text transcripts
- 🔍 **Detailed Program Pages** - Each program has its own page with all episodes and metadata
- 📱 **Mobile Responsive** - Beautiful design that works on all devices

**Persian:**
- 📻 **آرشیو کامل برنامه‌های رادیویی** - مرور بیش از 28 برنامه رادیو ایران‌صدا
- 📊 **آمار تعاملی** - جدول قابل مرتب‌سازی با تعداد قسمت‌ها، زیرنویس‌ها و بازه‌های زمانی
- 🎵 **لینک‌های مستقیم صوتی** - دسترسی به فایل‌های MP3 اصلی از سایت ایران‌صدا
- 📝 **متن‌ها و زیرنویس‌ها** - دانلود متن‌های خام و پاک‌سازی شده
- 🔍 **صفحات تفصیلی برنامه‌ها** - هر برنامه صفحه مخصوص خود با تمام قسمت‌ها و اطلاعات
- 📱 **طراحی ریسپانسیو** - طراحی زیبا که روی همه دستگاه‌ها کار می‌کند

---
 
This project is a web crawler written in Golang that retrieves audio files and metadata from the IranSeda radio website. It is designed to crawl the website, scan for available content, and download the audio files and associated data.

## 🔄 Workflow Documentation / مستند فرایند

برای هماهنگی تیم روی سرور و n8n، هر مرحلهٔ اصلی خط لوله در یک فایل Markdown توضیح داده شده است. پیش از اعمال هر تغییر در اسکریپت‌ها یا ورک‌فلوها، لطفاً سند متناظر را مطالعه و پس از تغییر، به‌روزرسانی کنید:

- [Plan – Program Schedule Refresh / طرح به‌روزرسانی زمان‌بندی](docs/workflows/00_program_schedule_refresh.md)
- [Stage 1 – Scan & Ingest / اسکن لینک و ثبت برنامه](docs/workflows/01_scan_and_ingest.md)
- [Stage 2 – DB-driven Downloads / دانلود از دیتابیس](docs/workflows/02_download_pipeline.md)
- [Stage 3 – Subtitle Generation / تولید زیرنویس](docs/workflows/03_subtitle_generation.md)
- [Stage 4 – Full-Text Cleanup / متن کامل و پاک‌سازی](docs/workflows/04_full_text_cleanup.md)
- [Stage 5 – Server Git Sync / همگام‌سازی گیت](docs/workflows/05_git_sync.md)
- [Stage 6 – Site Generation / تولید صفحات وب](docs/workflows/06_site_generation.md)

> **Rule:** هر تغییری در اسکریپت‌های مربوط به مراحل بالا، باید هم‌زمان در سند مرتبط ثبت شود تا «Single Source of Truth» حفظ گردد.

### Main Function Points
- Crawl and retrieve information and audio files from the IranSeda radio website
- Store the downloaded audio files and metadata in a local directory
- Manage the database of radio programs and their associated sessions

### Technology Stack
- Golang
- Python
- MariaDB/MySQL
- Git

### License
This project is open-source and available under the MIT License.





اول لينك رو اضافه ميكنيم به كراول
بعدش اسكن ميكنيم
بعدش دانلود میکنیم





------------------------



# 📡 IranSeda Crawler Golang Project

این پروژه برای خزش (crawl) و دریافت اطلاعات و فایل‌های صوتی از وب‌سایت رادیو ایران‌صدا طراحی شده است.

## 📁 ساختار پوشه‌ها

```
.
├── crawler/                # کدهای Python
├── downloads/             # فایل‌های mp3 یا srt
├── logs/                  # لاگ‌های تست
├── *.go                   # فایل‌های Go
├── *.sql                  # اسکریپت ساخت دیتابیس
├── .env                   # متغیرهای اتصال
└── readme.md              # این فایل
```

---

## 🛠 پیش‌نیازهای سرور

- Ubuntu 20.04 یا بالاتر
- Go (نسخه 1.24+)
- Python 3.8+
- MariaDB یا MySQL
- Git
- build-essential

---

## 🚀 مراحل نصب

### 1. کلون پروژه

```bash
git clone https://github.com/saber13812002/iranseda-crawler-golang-.git
cd iranseda-crawler-golang-
```

### 2. نصب Go

```bash
wget https://go.dev/dl/go1.24.3.linux-amd64.tar.gz
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go1.24.3.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc
go version
```

### 3. نصب Python و کتابخانه‌ها

```bash
sudo apt update
sudo apt install python3-pip
pip3 install requests beautifulsoup4 pymysql python-dotenv
```

### 4. نصب MariaDB و ساخت دیتابیس

```bash
sudo apt install mariadb-server
sudo systemctl enable mysql
sudo systemctl start mysql
```

### 5. ساخت دیتابیس و یوزر

```sql
CREATE DATABASE radio CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER 'n8nuser'@'%' IDENTIFIED BY 'StrongPassword123!';
GRANT ALL PRIVILEGES ON radio.* TO 'n8nuser'@'%';
FLUSH PRIVILEGES;
```

### 6. ساخت فایل .env

```env
MYSQL_CONN=n8nuser:StrongPassword123!@tcp(192.168.2.160:3306)/radio
DB_HOST=192.168.2.160
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio
```

---

## ⚙️ اجرای برنامه‌ها

### اجرای کراولر Go

```bash
go run scan.go
```

### اجرای دانلودر Go

```bash
go run download.go
```

### اجرای اسکریپت پایتون

```bash
python3 crawler/your_script.py
```

---

## ✅ نکات مهم

- اتصال‌ها به دیتابیس از طریق فایل `.env` انجام می‌شود.
- Go نیاز به اجرای `go mod tidy` دارد.
- MySQL باید به صورت ریموت در دسترس باشد (`bind-address=0.0.0.0` در فایل کانفیگ).
- برای تست سریع می‌توان از `test_n8n.py` استفاده کرد.





















-----------

برای ایجاد جداول و فیلدهای مربوط به برنامه‌های رادیویی و جلسات در دیتابیس MySQL، می‌توانید از دستورات SQL زیر استفاده کنید:

### 1. جدول `radio_programs`
این جدول اطلاعات مربوط به برنامه‌های رادیویی را ذخیره می‌کند.

```sql
DROP TABLE IF EXISTS `radio_programs`;
CREATE TABLE `radio_programs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `url` VARCHAR(255),
  `time_description` TEXT,
  `description` TEXT,
  `created_at` TIMESTAMP NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

```


### 2. جدول `radio_program_sessions`
این جدول اطلاعات مربوط به جلسات هر برنامه را ذخیره می‌کند.

```sql
CREATE TABLE radio_program_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    program_id INT NOT NULL,
    link VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (program_id) REFERENCES radio_programs(id) ON DELETE CASCADE
);

ALTER TABLE radio_program_sessions
ADD COLUMN filename VARCHAR(255) NOT NULL;

ALTER TABLE radio_program_sessions
ADD COLUMN is_downloaded TINYINT(1) DEFAULT 0;



CREATE TABLE downloaded_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,  -- نام فایل دانلود شده
    link TEXT NOT NULL,          -- لینک مربوطه از دیتابیس اصلی
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- زمان دانلود فایل
);



```

### توضیحات فیلدها:
- **`id`**: شناسه یکتای هر رکورد (کلید اصلی).
- **`name`**: نام برنامه رادیویی.
- **`time`**: زمان پخش برنامه.
- **`program_id`**: شناسه برنامه‌ای که جلسه به آن مربوط است (کلید خارجی).
- **`link`**: لینک مربوط به جلسه.
- **`created_at`**: زمان ایجاد رکورد.

### نکات:
- می‌توانید فیلدهای بیشتری به جداول اضافه کنید، مانند توضیحات یا تصویر برنامه.
- اطمینان حاصل کنید که جداول به درستی به هم مرتبط شده‌اند تا از یکپارچگی داده‌ها اطمینان حاصل شود.

اگر سوال دیگری دارید یا نیاز به تغییرات خاصی دارید، بفرمایید!
