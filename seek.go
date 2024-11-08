package main

import (
	"fmt"
	"log"
	"net/http"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

func main() {
	// URL صفحه‌ای که می‌خواهیم کراول کنیم
	url := "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=152507390"

	// درخواست به URL
	res, err := http.Get(url)
	if err != nil {
		log.Fatal(err)
	}
	defer res.Body.Close()

	// بررسی وضعیت پاسخ
	if res.StatusCode != 200 {
		log.Fatalf("خطا در درخواست: %d\n", res.StatusCode)
	}

	// پارس کردن HTML با goquery
	doc, err := goquery.NewDocumentFromReader(res.Body)
	if err != nil {
		log.Fatal(err)
	}

	// پیدا کردن لینک‌های دانلود
	var mp3Link string

	// جستجوی لینک‌ها
	doc.Find(".modal-body a").Each(func(index int, item *goquery.Selection) {
		// استخراج href
		link, exist := item.Attr("href")
		// fmt.Println(link) // این خط را برای دیباگ حفظ کنید

		if exist && index == 2 && containsMp3(item) { // تنها لینک سوم را بررسی می‌کنیم
			mp3Link = link // اگر لینک .mp3 پیدا شد، ذخیره می‌کنیم
		}
	})

	// بررسی و نمایش لینک mp3 پیدا شده
	if mp3Link != "" {
		fmt.Println(mp3Link)
	} else {
		fmt.Println("لینک mp3 پیدا نشد.")
	}
}

// تابعی برای بررسی وجود ".mp3" در متن
func containsMp3(item *goquery.Selection) bool {
	span := item.Find("span") // پیدا کردن عنصر span
	text := span.Text()       // استخراج متن

	// بررسی وجود ".mp3" در متن
	return strings.Contains(text, "(.mp3)")
}
