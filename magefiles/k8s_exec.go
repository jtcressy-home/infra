//go:build mage
// +build mage

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"tailscale.com/client/tailscale"
)

// ExecCredential is the Kubernetes ExecCredential API object
// Example:
//
//	{
//		"apiVersion": "client.authentication.k8s.io/v1",
//		"kind": "ExecCredential",
//		"status": {
//			"token": "my-bearer-token"
//		}
//	}
type ExecCredential struct {
	APIVersion string               `json:"apiVersion"`
	Kind       string               `json:"ExecCredential"`
	Status     ExecCredentialStatus `json:"status"`
}

type ExecCredentialStatus struct {
	Token string `json:"token"`
}

func NewExecCredential(token string) ExecCredential {
	ec := ExecCredential{
		APIVersion: "client.authentication.k8s.io/v1",
		Kind:       "ExecCredential",
		Status: ExecCredentialStatus{
			Token: token,
		},
	}
	return ec
}

func (ec ExecCredential) String() string {
	b, err := json.MarshalIndent(&ec, "", "  ")
	if err != nil {
		fmt.Printf("could not marshal ExecCredentials: %s", err)
		os.Exit(1)
	}
	return string(b)
}

func k8s_exec() error {
	lc := tailscale.LocalClient{}
	if jwt, err := lc.IDToken(context.Background(), "kubernetes"); err != nil {
		return fmt.Errorf("error getting id-token:", err)
	} else {
		ec := NewExecCredential(jwt.IDToken)
		fmt.Println(ec.String())
	}
	return nil
}
