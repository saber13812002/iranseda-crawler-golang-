package main

import (
	"database/sql"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"

	"github.com/PuerkitoBio/goquery"
	"github.com/joho/godotenv"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	// بارگذاری فایل .env
	err := godotenv.Load()
	if err != nil {
		log.Fatal("Error loading .env file")
	}

	connStr := os.Getenv("MYSQL_CONN")
	if connStr == "" {
		log.Fatal("MYSQL_CONN not found in .env")
	}

	// اتصال به دیتابیس
	db, err := sql.Open("mysql", connStr)
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	// دریافت لیست تمام برنامه‌ها از دیتابیس
	programs, err := getPrograms(db)
	if err != nil {
		log.Fatal(err)
	}

	for _, program := range programs {
		fmt.Printf("Scanning program: %s (ID: %d)\n", program.Name, program.ID)
		
		res, err := http.Get(program.URL)
		if err != nil {
			log.Printf("Failed to fetch program %s: %v", program.Name, err)
			continue
		}
		defer res.Body.Close()

		if res.StatusCode != 200 {
			log.Printf("Failed to get page for program %s: %s", program.Name, res.Status)
			continue
		}

		doc, err := goquery.NewDocumentFromReader(res.Body)
		if err != nil {
			log.Printf("Failed to parse page for program %s: %v", program.Name, err)
			continue
		}

		// استخراج لینک‌ها
		doc.Find("a").Each(func(i int, s *goquery.Selection) {
			href, exists := s.Attr("href")
			if exists {
				matched, _ := regexp.MatchString(`epgarchivePart`, href)
				if matched {
					fmt.Printf("Found link: %s\n", href)

					// بررسی وجود لینک در دیتابیس
					if !sessionExists(db, href) {
						saveSession(db, href, program.ID) // استفاده از شناسه برنامه از دیتابیس
						fmt.Printf("Inserted: %s for program ID %d\n", href, program.ID)
					} else {
						fmt.Printf("Already exists: %s\n", href)
					}
				}
			}
		})
	}
}

// ساختار برای ذخیره اطلاعات برنامه از دیتابیس
type Program struct {
	ID   int
	Name string
	URL  string
}

// دریافت لیست برنامه‌ها از دیتابیس
func getPrograms(db *sql.DB) ([]Program, error) {
	var programs []Program

	rows, err := db.Query("SELECT id, name, url FROM radio_programs WHERE url IS NOT NULL AND url != ''")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var p Program
		err := rows.Scan(&p.ID, &p.Name, &p.URL)
		if err != nil {
			return nil, err
		}
		programs = append(programs, p)
	}

	return programs, nil
}

// توابع دیگر (programExists, saveProgram, sessionExists, saveSession) بدون تغییر می‌مانند
// ...



func sessionExists(db *sql.DB, link string) bool {
	var exists bool
	err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM radio_program_sessions WHERE link=?)", link).Scan(&exists)
	if err != nil {
		log.Fatal(err)
	}
	return exists
}

func saveSession(db *sql.DB, link string, programID int) {
	_, err := db.Exec("INSERT INTO radio_program_sessions (link, program_id, filename) VALUES (?, ?, '')", link, programID)
	if err != nil {
		log.Fatal(err)
	}
}

