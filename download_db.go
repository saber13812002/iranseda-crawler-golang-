package main

import (
	"database/sql"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"github.com/PuerkitoBio/goquery"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	// دریافت پارامتر از خط فرمان برای آی دی برنامه
	programID := flag.String("programID", "", "Program ID to fetch and download")
	flag.Parse()

	// اگر programID مشخص نشده باشد، مقدار آن به "1" تنظیم می‌شود
	if *programID == "" {
		*programID = "1"
	}

	// اتصال به دیتابیس
	db, err := sql.Open("mysql", "root@tcp(127.0.0.1:3306)/radio")
	if err != nil {
		fmt.Println("Error connecting to database:", err)
		return
	}
	defer db.Close()

	// دریافت لینک از دیتابیس برای تست بر اساس programID
	row := db.QueryRow("SELECT link FROM radio_program_sessions WHERE program_id = ?", *programID)

	var link string
	if err := row.Scan(&link); err != nil {
		fmt.Println("Error fetching link for program ID:", *programID, err)
		return
	}
	fmt.Println("Fetched link from DB:", link)

	// اصلاح لینک
	link = strings.Replace(link, "..", "", 1)
	originalLink := "https://radio.iranseda.ir" + link
	fmt.Println("Original Link:", originalLink)

	// درخواست HTML صفحه برای استخراج لینک دانلود
	downloadURL := extractDownloadLinkAndFilename(originalLink)
	if downloadURL == "" {
		fmt.Println("Error: Unable to extract download link")
		return
	}

	// پوشه‌ای که فایل‌ها در آن ذخیره می‌شوند
	downloadFolder := "./downloads/" + *programID + "/"
	os.MkdirAll(downloadFolder, os.ModePerm) // ایجاد پوشه برای برنامه خاص

	// دانلود و ذخیره فایل
	downloadFile(downloadURL)
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

// تابع دانلود فایل و استخراج نام فایل از هدر Content-Disposition
func downloadFile(url string) {
	// ارسال درخواست برای دریافت فایل
	response, err := http.Get(url)
	if err != nil {
		fmt.Println("Error while downloading:", err)
		return
	}
	defer response.Body.Close()

	// بررسی وضعیت پاسخ
	if response.StatusCode != http.StatusOK {
		fmt.Println("Error: failed to download file, status code:", response.StatusCode)
		return
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

	// ایجاد فایل برای ذخیره محتوا
	outFile, err := os.Create(filename)
	if err != nil {
		fmt.Println("Error while creating file:", err)
		return
	}
	defer outFile.Close()

	// کپی کردن محتوا از response.Body به فایل
	_, err = io.Copy(outFile, response.Body)
	if err != nil {
		fmt.Println("Error while saving file:", err)
		return
	}

	fmt.Printf("File downloaded successfully as %s!\n", filename)
}
