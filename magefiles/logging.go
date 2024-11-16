//go:build mage
// +build mage

package main

import (
	"log/slog"
	"os"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/log"
	"github.com/go-logr/logr"
	"k8s.io/klog/v2"
)

func init() {
	// initialize log/slog with charmbracelet/log as a handler
	h := log.NewWithOptions(os.Stderr, log.Options{
		ReportTimestamp: true,
	})

	styles := log.DefaultStyles()
	for k, v := range styles.Levels {
		styles.Levels[k] = v.MaxWidth(5)
	}
	styles.Levels[log.Level(-8)] = lipgloss.NewStyle().
		SetString("TRACE").
		Bold(true).
		// dark grey color
		Foreground(lipgloss.Color("#666666")).
		MaxWidth(5)
	h.SetStyles(styles)
	log.SetDefault(h)

	l := slog.New(h)
	slog.SetDefault(l)

	lgr := logr.FromSlogHandler(h)
	klog.SetLogger(lgr)
}
