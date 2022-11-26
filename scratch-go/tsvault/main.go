package main

import (
	"context"
	"fmt"
	"log"

	"tailscale.com/client/tailscale"
)

func main() {
	lc := tailscale.LocalClient{}
	if jwt, err := lc.IDToken(context.Background(), "kubernetes"); err != nil {
		log.Fatalf("error getting id-token:", err)
	} else {
		fmt.Println(jwt.IDToken)
	}
}
