package main

import (
	"database/sql"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"

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

		// Canonical keys of the program's existing sessions — per-episode
		// dedup, so the same episode is never inserted twice even if the
		// stored link differs in URL format (absolute vs relative, VALID
		// flag, param order, trailing slash). Stored links are never
		// rewritten (matches discover_new.py's canonical matching).
		known, err := knownEpisodeKeys(db, program.ID)
		if err != nil {
			log.Printf("Failed to load existing sessions for program %d: %v", program.ID, err)
			continue
		}

		// استخراج لینک‌ها
		doc.Find("a").Each(func(i int, s *goquery.Selection) {
			href, exists := s.Attr("href")
			if exists {
				matched, _ := regexp.MatchString(`epgarchivePart`, href)
				if matched {
					key := canonEpisodeLink(href)
					if key == "" {
						return // not a well-formed epgarchivePart episode link
					}
					fmt.Printf("Found link: %s\n", href)

					// بررسی وجود لینک در دیتابیس (مقایسه با کلید کانونیکال)
					if known[key] {
						fmt.Printf("Already exists: %s\n", href)
						return
					}
					saveSession(db, href, program.ID) // استفاده از شناسه برنامه از دیتابیس
					known[key] = true
					fmt.Printf("Inserted: %s for program ID %d\n", href, program.ID)
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

	rows, err := db.Query("SELECT id, name, url FROM radio_programs WHERE url IS NOT NULL AND url != '' AND is_legacy = 0")
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



// canonEpisodeLink — canonical identity key for an archive-episode URL.
//
// Must stay in lock-step with iranseda_site.canon_episode_link (Python) so
// every dedup path recognizes the same episode. The episode is identified by
// (ch, e) only; everything else (host, scheme, "../", VALID flag, param
// order, trailing slash) is stripped. Returns "" for non-episode links.
func canonEpisodeLink(link string) string {
	s := strings.TrimSpace(link)
	// strip scheme + host
	if i := strings.Index(s, "://"); i >= 0 {
		rest := s[i+3:]
		if j := strings.Index(rest, "/"); j >= 0 {
			s = rest[j:]
		} else {
			s = ""
		}
	}
	s = strings.TrimPrefix(s, "/")
	// A trailing slash (after the query or the path) carries no meaning.
	s = strings.TrimRight(s, "/")
	for strings.HasPrefix(s, "../") {
		s = s[3:]
	}
	i := strings.Index(s, "epgarchivePart")
	if i < 0 {
		return ""
	}
	s = s[i:]
	parts := strings.SplitN(s, "?", 2)
	path := strings.TrimRight(parts[0], "/")
	if path != "epgarchivePart" {
		return ""
	}
	ch, e := "", ""
	if len(parts) > 1 {
		for _, kv := range strings.Split(parts[1], "&") {
			if kv == "" {
				continue
			}
			pe := strings.SplitN(kv, "=", 2)
			if len(pe) != 2 {
				continue
			}
			switch strings.ToLower(pe[0]) {
			case "ch":
				ch = strings.TrimSpace(pe[1])
			case "e":
				e = strings.TrimSpace(pe[1])
			}
		}
	}
	if ch == "" || e == "" {
		return ""
	}
	return "epgarchivePart?ch=" + ch + "&e=" + e
}

// knownEpisodeKeys loads the canonical keys of all sessions already stored
// for a program, for per-episode dedup (no duplicate rows, any URL format).
func knownEpisodeKeys(db *sql.DB, programID int) (map[string]bool, error) {
	rows, err := db.Query("SELECT link FROM radio_program_sessions WHERE program_id=?", programID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	known := make(map[string]bool)
	for rows.Next() {
		var link string
		if err := rows.Scan(&link); err != nil {
			return nil, err
		}
		if k := canonEpisodeLink(link); k != "" {
			known[k] = true
		}
	}
	return known, rows.Err()
}

// saveSession inserts one session. INSERT IGNORE: the UNIQUE(program_id,
// link) key makes concurrent runs (scan.go + discover_new.py + dashboard
// seed) safe — a duplicate is a no-op, not a failure.
func saveSession(db *sql.DB, link string, programID int) {
	res, err := db.Exec("INSERT IGNORE INTO radio_program_sessions (link, program_id, filename, status) VALUES (?, ?, '', 'pending_download')", link, programID)
	if err != nil {
		log.Fatal(err)
	}
	if n, e := res.RowsAffected(); e == nil && n == 0 {
		fmt.Printf("Already exists (unique key): %s\n", link)
	}
}

