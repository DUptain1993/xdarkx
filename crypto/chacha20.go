package crypto

import "golang.org/x/crypto/chacha20poly1305"

// ChaCha20Poly1305Decrypt decrypts ciphertext (with appended 16-byte tag) using ChaCha20-Poly1305.
// Used for Chrome 130+ App Bound Encryption key decryption (flag=2).
func ChaCha20Poly1305Decrypt(key, nonce, ciphertext []byte) ([]byte, error) {
	aead, err := chacha20poly1305.New(key)
	if err != nil {
		return nil, err
	}
	return aead.Open(nil, nonce, ciphertext, nil)
}
