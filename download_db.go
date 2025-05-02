package main

import (
    "database/sql"
    "fmt"
    "io"
    "net/http"
    "os"
    "strings"

    _ "github.com/go-sql-driver/mysql"
)

func main() {
    // اتصال به دیتابیس
    db, err := sql.Open("mysql", "root@tcp(127.0.0.1:3306)/radio")
    if err != nil {
        fmt.Println("Error connecting to database:", err)
        return
    }
    defer db.Close()

    // دریافت لینک‌های ذخیره‌شده در دیتابیس
    rows, err := db.Query("SELECT link FROM radio_program_sessions")
    if err != nil {
        fmt.Println("Error fetching links:", err)
        return
    }
    defer rows.Close()

    // پوشه‌ای که فایل‌ها در آن ذخیره می‌شوند
    downloadFolder := "./downloads/"

    for rows.Next() {
        var link string
        if err := rows.Scan(&link); err != nil {
            fmt.Println("Error scanning row:", err)
            continue
        }

        // استخراج نام فایل از لینک
        filename := extractFilename(link)
        filepath := downloadFolder + filename

        // بررسی اینکه آیا فایل قبلاً دانلود شده است
        if _, err := os.Stat(filepath); os.IsNotExist(err) {
            fmt.Printf("Downloading file: %s\n", filename)
            downloadFile(link, filepath)
            saveDownloadedFile(db, filename)
        } else {
            fmt.Printf("File already exists: %s\n", filename)
        }
    }
}

// تابع استخراج نام فایل از لینک
func extractFilename(link string) string {
    parts := strings.Split(link, "=")
    if len(parts) > 1 {
        return parts[1] + ".mp3"
    }
    return "default_filename.mp3"
}

// تابع دانلود فایل
func downloadFile(url, filepath string) {
    response, err := http.Get(url)
    if err != nil {
        fmt.Println("Error downloading:", err)
        return
    }
    defer response.Body.Close()

    outFile, err := os.Create(filepath)
    if err != nil {
        fmt.Println("Error creating file:", err)
        return
    }
    defer outFile.Close()

    _, err = io.Copy(outFile, response.Body)
    if err != nil {
        fmt.Println("Error saving file:", err)
    }
}

// ذخیره نام فایل در بانک اطلاعاتی
func saveDownloadedFile(db *sql.DB, filename string) {
    _, err := db.Exec("INSERT INTO downloaded_files (name) VALUES (?)", filename)
    if err != nil {
        fmt.Println("Error saving filename to database:", err)
    }
}
