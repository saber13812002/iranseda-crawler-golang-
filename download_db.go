package main

import (
	"database/sql"
	// "flag"
	"fmt"
	"io"
	"net/http"
	"os"
	// "strconv"
	"strings"

	"github.com/PuerkitoBio/goquery"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	// دریافت پارامتر از خط فرمان برای آی دی برنامه
	// programID := flag.String("programID", "", "Program ID to fetch and download")
	// flag.Parse()

	// // اگر programID مشخص نشده باشد، مقدار آن به "1" تنظیم می‌شود
	// if *programID == "" {
	// 	*programID = "1"
	// }

	// اتصال به دیتابیس
	db, err := sql.Open("mysql", "root@tcp(127.0.0.1:3306)/radio")
	if err != nil {
		fmt.Println("Error connecting to database:", err)
		return
	}
	defer db.Close()

	// دریافت لینک‌ها و وضعیت دانلود از دیتابیس
	rows, err := db.Query("SELECT id, link, is_downloaded FROM radio_program_sessions")
	if err != nil {
		fmt.Println("Error fetching data from database:", err)
		return
	}
	defer rows.Close()

	// خواندن لینک‌ها و دانلود فایل‌های جدید
	for rows.Next() {
		var id int
		var link string
		var isDownloaded int
		if err := rows.Scan(&id, &link, &isDownloaded); err != nil {
			fmt.Println("Error scanning row:", err)
			continue
		}

		if isDownloaded == 0 { // فقط فایل‌هایی که دانلود نشده‌اند
			// اصلاح لینک
			link = strings.Replace(link, "..", "", 1)
			originalLink := "https://radio.iranseda.ir" + link
			fmt.Println("Original Link:", originalLink)

			// استخراج لینک دانلود
			downloadURL := extractDownloadLinkAndFilename(originalLink)
			if downloadURL == "" {
				fmt.Println("Error: Unable to extract download link")
				continue
			}

			// دانلود فایل
			filename := downloadFile(downloadURL)

			// ذخیره نام فایل در بانک اطلاعاتی

			if err != nil {
				fmt.Println("Error converting programID to int:", err)
				continue
			}
			saveDownloadedFile(db, id, filename)

			// بروزرسانی وضعیت دانلود در دیتابیس
			_, err = db.Exec("UPDATE radio_program_sessions SET is_downloaded = 1 WHERE link = ?", link)
			if err != nil {
				fmt.Println("Error updating download status in database:", err)
			} else {
				fmt.Println("File marked as downloaded in database.")
			}
		} else {
			fmt.Println("File already downloaded:", link)
		}
	}

	if err := rows.Err(); err != nil {
		fmt.Println("Error iterating rows:", err)
	}
}

// تابع استخراج لینک دانلود از صفحه HTML
func extractDownloadLinkAndFilename(url string) string {
	// درخواست HTML صفحه
	res, err := http.Get(url)
	if err != nil {
		fmt.Println("Error fetching the page:", err)
		return ""
	}
	defer res.Body.Close()

	// بارگذاری محتوای صفحه
	doc, err := goquery.NewDocumentFromReader(res.Body)
	if err != nil {
		fmt.Println("Error parsing the page:", err)
		return ""
	}

	// استخراج لینک دانلود از تگ <a> با کلاس col-plus page-loding
	downloadURL := ""
	doc.Find("a.col-plus.page-loding").Each(func(i int, s *goquery.Selection) {
		downloadURL, _ = s.Attr("href")
	})

	return downloadURL
}

// تابع دانلود فایل
func downloadFile(url string) string {
	// ارسال درخواست برای دریافت فایل
	response, err := http.Get(url)
	if err != nil {
		fmt.Println("Error while downloading:", err)
		return ""
	}
	defer response.Body.Close()

	// بررسی وضعیت پاسخ
	if response.StatusCode != http.StatusOK {
		fmt.Println("Error: failed to download file, status code:", response.StatusCode)
		return ""
	}

	// استخراج نام فایل از هدر Content-Disposition
	filename := "default_filename.mp3"
	if disposition := response.Header.Get("Content-Disposition"); disposition != "" {
		if strings.Contains(disposition, "filename=") {
			start := strings.Index(disposition, "filename=") + len("filename=")
			end := strings.Index(disposition[start:], ";")
			if end == -1 {
				end = len(disposition)
			} else {
				end += start
			}
			// جایگزینی کاراکترهای نامناسب
			filename = strings.ReplaceAll(strings.ReplaceAll(strings.Trim(strings.TrimSpace(disposition[start:end]), "\""), "/", "-"), ":", "-")
		}
	}

	// ایجاد پوشه "downloads" در صورتی که وجود نداشته باشد
	downloadFolder := "./downloads/"
	os.MkdirAll(downloadFolder, os.ModePerm)

	// ذخیره فایل در پوشه "downloads"
	filepath := downloadFolder + filename
	outFile, err := os.Create(filepath)
	if err != nil {
		fmt.Println("Error while creating file:", err)
		return ""
	}
	defer outFile.Close()

	// کپی کردن محتوا از response.Body به فایل
	_, err = io.Copy(outFile, response.Body)
	if err != nil {
		fmt.Println("Error while saving file:", err)
		return ""
	}

	fmt.Printf("File downloaded successfully as %s!\n", filename)
	return filename
}

// ذخیره نام فایل در بانک اطلاعاتی
func saveDownloadedFile(db *sql.DB, id int, filename string) {
	_, err := db.Exec("UPDATE radio_program_sessions SET filename = ?, is_downloaded = 1 WHERE id = ?", filename, id)
	if err != nil {
		fmt.Println("Error saving filename to database:", err)
	}
}
