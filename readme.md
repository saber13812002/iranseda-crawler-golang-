# iranseda-crawler-golang-



برای ایجاد جداول و فیلدهای مربوط به برنامه‌های رادیویی و جلسات در دیتابیس MySQL، می‌توانید از دستورات SQL زیر استفاده کنید:

### 1. جدول `radio_programs`
این جدول اطلاعات مربوط به برنامه‌های رادیویی را ذخیره می‌کند.

```sql
CREATE TABLE radio_programs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    time VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
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