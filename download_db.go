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

	// اگر programID مشخص نشده باشد، خروجی خطا
	if *programID == "" {
		// fmt.Println("Error: Program ID is required")
		// return
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
	fmt.Println("Before fixing link:", link)
	link = strings.Replace(link, "..", "", 1)
	originalLink := "https://radio.iranseda.ir" + link
	fmt.Println("Original Link:", originalLink)

	// تبدیل لینک به لینک دانلود صحیح
	// downloadURL := convertLinkToDownloadURL(originalLink)
	// fmt.Println("Converted Download URL:", downloadURL)

	// درخواست HTML صفحه برای استخراج لینک دانلود و نام فایل
	downloadURL, filename := extractDownloadLinkAndFilename(originalLink)
	if downloadURL == "" || filename == "" {
		fmt.Println("Error: Unable to extract download link or filename")
		return
	}

	// پوشه‌ای که فایل‌ها در آن ذخیره می‌شوند
	downloadFolder := "./downloads/" + *programID + "/"
	os.MkdirAll(downloadFolder, os.ModePerm) // ایجاد پوشه برای برنامه خاص

	// اصلاح نام فایل
	filename = sanitizeFilename(filename)
	fmt.Println("Sanitized filename:", filename)

	filepath := downloadFolder + filename
	fmt.Println("Filepath to save:", filepath)

	// بررسی اینکه آیا فایل قبلاً دانلود شده است
	if _, err := os.Stat(filepath); os.IsNotExist(err) {
		fmt.Printf("Downloading file: %s\n", filename)
		downloadFile(downloadURL, filepath)
		saveDownloadedFile(db, filename)
	} else {
		fmt.Printf("File already exists: %s\n", filename)
	}
}

// تابع استخراج لینک دانلود و نام فایل از صفحه HTML
func extractDownloadLinkAndFilename(url string) (string, string) {
	// درخواست HTML صفحه
	res, err := http.Get(url)
	if err != nil {
		fmt.Println("Error fetching the page:", err)
		return "", ""
	}
	defer res.Body.Close()

	// بارگذاری محتوای صفحه
	doc, err := goquery.NewDocumentFromReader(res.Body)
	if err != nil {
		fmt.Println("Error parsing the page:", err)
		return "", ""
	}

	// استخراج لینک دانلود از تگ <a> با کلاس col-plus page-loding
	downloadURL := ""
	doc.Find("a.col-plus.page-loding").Each(func(i int, s *goquery.Selection) {
		downloadURL, _ = s.Attr("href")
	})

	// استخراج نام فایل از متن تگ <span> که شامل دانلود از سرور است
	var filename string
	doc.Find(".fa-download").Each(func(i int, s *goquery.Selection) {
		downloadText := s.Parent().Find("span").Text()
		if strings.Contains(downloadText, ".mp3") {
			filename = downloadText
		}
	})

	// اگر نام فایل پیدا نشد، از یک نام پیش‌فرض استفاده می‌کنیم
	if filename == "" {
		fmt.Println("No valid file found, using default name")
		filename = "default_filename.mp3"
	}

	return downloadURL, filename
}

// تابع برای جایگزینی کاراکترهای نامناسب در نام فایل
func sanitizeFilename(filename string) string {
	// جایگزینی کاراکترهای نامناسب مثل () و ...
	filename = strings.ReplaceAll(filename, "(", "-")
	filename = strings.ReplaceAll(filename, ")", "-")
	filename = strings.ReplaceAll(filename, " ", "_")
	return filename
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
