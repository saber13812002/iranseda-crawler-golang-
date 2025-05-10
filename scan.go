package main

import (
	"database/sql"
	"fmt"
	"log"
	"net/http"
	"regexp"

	"github.com/PuerkitoBio/goquery"
	_ "github.com/go-sql-driver/mysql"
)

func main() {
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116"
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=046104"
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045101"
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044323"
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=047545"
	// tarikh
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045102"
	// quran
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045103"
	// mahdavi
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=046111"
	// پیام ولایت
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044125"
	// امیر مؤمنان
	//url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=047506"
	// امیر بیان
	//  url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045504"
	//اخبار معارفی
	url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=048113"


	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044323"
	// url := "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044323"
	db, err := sql.Open("mysql", "root@tcp(127.0.0.1:3306)/radio")
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	res, err := http.Get(url)
	if err != nil {
		log.Fatal(err)
	}
	defer res.Body.Close()

	if res.StatusCode != 200 {
		log.Fatalf("failed to get page: %s", res.Status)
	}

	doc, err := goquery.NewDocumentFromReader(res.Body)
	if err != nil {
		log.Fatal(err)
	}
	var programID int

	var programName, programTime string
	var newSession bool

	// استخراج نام برنامه و زمان آن
	doc.Find("h1").Each(func(i int, s *goquery.Selection) {
		programName = s.Text()
	})

	doc.Find("h2").Each(func(i int, s *goquery.Selection) {
		programTime = s.Text()
	})

	// استخراج لینک‌ها
	// استخراج لینک‌ها
	doc.Find("a").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if exists {
			matched, _ := regexp.MatchString(`epgarchivePart`, href)
			if matched {
				fmt.Printf("Found link: %s\n", href) // چاپ لینک پیدا شده

				// بررسی وجود لینک در دیتابیس
				if !sessionExists(db, href) {
					saveSession(db, href, programID) // استفاده از شناسه برنامه
					fmt.Printf("Inserted: %s\n", href)
				} else {
					fmt.Printf("Already exists: %s\n", href)
				}
			}
		}
	})

	if programName != "" && programTime != "" {
		if !programExists(db, programName) {
			programID = saveProgram(db, programName, programTime) // ذخیره شناسه
		} else {
			// دریافت شناسه برنامه موجود
			err := db.QueryRow("SELECT id FROM radio_programs WHERE name=?", programName).Scan(&programID)
			if err != nil {
				log.Fatal(err)
			}
		}
	}

	if newSession {
		fmt.Println("New session added.")
	} else {
		fmt.Println("No new sessions.")
	}
}

func programExists(db *sql.DB, name string) bool {
	var exists bool
	err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM radio_programs WHERE name=?)", name).Scan(&exists)
	if err != nil {
		log.Fatal(err)
	}
	return exists
}

// در تابع saveProgram:
func saveProgram(db *sql.DB, name, time string) int {
	result, err := db.Exec("INSERT INTO radio_programs (name, time) VALUES (?, ?)", name, time)
	if err != nil {
		log.Fatal(err)
	}
	id, err := result.LastInsertId() // دریافت شناسه برنامه جدید
	if err != nil {
		log.Fatal(err)
	}
	return int(id) // بازگشت شناسه
}

func sessionExists(db *sql.DB, link string) bool {
	var exists bool
	err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM radio_program_sessions WHERE link=?)", link).Scan(&exists)
	if err != nil {
		log.Fatal(err)
	}
	return exists
}

func saveSession(db *sql.DB, link string, programID int) {
	_, err := db.Exec("INSERT INTO radio_program_sessions (link, program_id) VALUES (?, ?)", link, programID)
	if err != nil {
		log.Fatal(err)
	}
}
