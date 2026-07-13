//go:build ignore
// +build ignore

package main

import (
	"os"

	"github.com/magefile/mage/mage"
)

// Support zero install
func main() { os.Exit(mage.Main()) }
