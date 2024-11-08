package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
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
	if response.StatusCode != http.StatusOK {
		fmt.Println("Error: failed to download file, status code:", response.StatusCode)
		return
	}

	// Create a file to save the downloaded content
	outFile, err := os.Create("iran_seda_maaref_2650695_201.mp3") // Change the filename as necessary
	if err != nil {
		fmt.Println("Error while creating file:", err)
		return
	}
	defer outFile.Close()

	// Copy the response body to the file
	_, err = io.Copy(outFile, response.Body)
	if err != nil {
		fmt.Println("Error while saving file:", err)
		return
	}

	fmt.Println("File downloaded successfully!")
}
