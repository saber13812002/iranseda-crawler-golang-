package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
)

func main() {
	url := "https://headend1.iranseda.ir/DLFile/?VALID=TRUE&vid=2650695_201"

	// Create a new HTTP request
	response, err := http.Get(url)
	if err != nil {
		fmt.Println("Error while downloading:", err)
		return
	}
	defer response.Body.Close()

	// Check if the request was successful
	fmt.Println("Response Status:", response.Status)
	if response.StatusCode != http.StatusOK {
		fmt.Println("Error: failed to download file, status code:", response.StatusCode)
		return
	}

	// Determine the filename
	filename := "default_filename.mp3"

	// Check if Content-Disposition header is present
	if disposition := response.Header.Get("Content-Disposition"); disposition != "" {
		if strings.Contains(disposition, "filename=") {
			start := strings.Index(disposition, "filename=") + len("filename=")
			end := strings.Index(disposition[start:], ";")
			if end == -1 {
				end = len(disposition)
			} else {
				end += start
			}
			// Replace invalid characters in the filename
			filename = strings.ReplaceAll(strings.ReplaceAll(strings.Trim(strings.TrimSpace(disposition[start:end]), "\""), "/", "-"), ":", "-")
		}
	}

	// Create a file to save the downloaded content
	outFile, err := os.Create(filename)
	if err != nil {
		fmt.Println("Error while creating file:", err)
		return
	}
	defer outFile.Close()

	// Copy the response body to the file
	_, err = io.Copy(outFile, response.Body) // Directly copy from response.Body to outFile
	if err != nil {
		fmt.Println("Error while saving file:", err)
		return
	}

	fmt.Printf("File downloaded successfully as %s!\n", filename)
}
