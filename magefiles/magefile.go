//go:build mage
// +build mage

package main

import (
	"fmt"
	"os/exec"
	// mg contains helpful utility functions, like Deps
)

// Default target to run when none is specified
// If not set, running mage will list available targets
// var Default = Build

// A build step that requires additional params, or platform specific steps for example
func Build() error {
	fmt.Println("Building...")
	cmd := exec.Command("go", "build", "-o", "MyApp", ".")
	return cmd.Run()
}

// For use by kubectl via kubeconfig to generate an auth token from tailscaled
func KExecCredential() error {
	return k8s_exec()
}
