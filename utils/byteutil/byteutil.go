package byteutil

import (
	"encoding/hex"
	"fmt"
	"strings"
)

var OnSplitUTF8Func = func(r rune) rune {
	if r == 0x00 || r == 0x01 {
		return -1
	}
	return r
}

// ParseHexKey parses a key string in \xAA\xBB... or plain hex (AABB...) format into bytes.
// The \xAA format is produced by cookie-monster BOF output.
func ParseHexKey(s string) ([]byte, error) {
	if s == "" {
		return nil, fmt.Errorf("empty key")
	}
	// Handle \xAA\xBB style format
	if strings.Contains(s, `\x`) {
		parts := strings.Split(s, `\x`)
		var result []byte
		for _, p := range parts {
			p = strings.TrimSpace(p)
			if p == "" {
				continue
			}
			// Each part may be exactly 2 hex chars (one byte)
			if len(p) > 2 {
				// In case multiple bytes are concatenated without separator
				b, err := hex.DecodeString(p)
				if err != nil {
					return nil, fmt.Errorf("invalid hex segment %q: %w", p, err)
				}
				result = append(result, b...)
			} else {
				b, err := hex.DecodeString(p)
				if err != nil {
					return nil, fmt.Errorf("invalid hex byte %q: %w", p, err)
				}
				result = append(result, b...)
			}
		}
		return result, nil
	}
	// Plain hex string (e.g. "AABBCC" or "aa:bb:cc")
	cleaned := strings.ReplaceAll(s, ":", "")
	cleaned = strings.ReplaceAll(cleaned, " ", "")
	b, err := hex.DecodeString(cleaned)
	if err != nil {
		return nil, fmt.Errorf("invalid hex key: %w", err)
	}
	return b, nil
}

