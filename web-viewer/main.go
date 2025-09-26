package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

type Program struct {
	ID          uint       `json:"id" gorm:"primaryKey"`
	Title       string     `json:"title"`
	Description string     `json:"description"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
	Subtitles   []Subtitle `json:"subtitles" gorm:"foreignKey:ProgramID"`
}

type Subtitle struct {
	ID        uint      `json:"id" gorm:"primaryKey"`
	ProgramID uint      `json:"program_id"`
	Content   string    `json:"content"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

var db *gorm.DB

func initDB() {
	err := godotenv.Load()
	if err != nil {
		log.Fatal("Error loading .env file")
	}

	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=True&loc=Local",
		os.Getenv("DB_USER"),
		os.Getenv("DB_PASSWORD"),
		os.Getenv("DB_HOST"),
		os.Getenv("DB_PORT"),
		os.Getenv("DB_NAME"),
	)

	db, err = gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		log.Fatal("Failed to connect to database:", err)
	}

	db.AutoMigrate(&Program{}, &Subtitle{})
}

func backupToJSON() error {
	var programs []Program
	if err := db.Preload("Subtitles").Find(&programs).Error; err != nil {
		return err
	}

	backupDir := "backups"
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		return err
	}

	filename := fmt.Sprintf("%s/backup_%s.json", backupDir, time.Now().Format("2006-01-02_15-04-05"))
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(programs)
}

func main() {
	initDB()

	r := gin.Default()
	r.LoadHTMLGlob("templates/*")
	r.Static("/static", "./static")

	// API Routes
	api := r.Group("/api")
	{
		api.GET("/programs", func(c *gin.Context) {
			var programs []Program
			db.Preload("Subtitles").Find(&programs)
			c.JSON(200, programs)
		})

		api.GET("/programs/:id", func(c *gin.Context) {
			var program Program
			if err := db.Preload("Subtitles").First(&program, c.Param("id")).Error; err != nil {
				c.JSON(404, gin.H{"error": "Program not found"})
				return
			}
			c.JSON(200, program)
		})

		api.POST("/backup", func(c *gin.Context) {
			if err := backupToJSON(); err != nil {
				c.JSON(500, gin.H{"error": err.Error()})
				return
			}
			c.JSON(200, gin.H{"message": "Backup created successfully"})
		})
	}

	// Web Routes
	r.GET("/", func(c *gin.Context) {
		var programs []Program
		db.Preload("Subtitles").Find(&programs)
		c.HTML(200, "index.html", gin.H{
			"programs": programs,
		})
	})

	r.GET("/program/:id", func(c *gin.Context) {
		var program Program
		if err := db.Preload("Subtitles").First(&program, c.Param("id")).Error; err != nil {
			c.HTML(404, "error.html", gin.H{"error": "Program not found"})
			return
		}
		c.HTML(200, "program.html", gin.H{
			"program": program,
		})
	})

	r.Run(":8080")
}
