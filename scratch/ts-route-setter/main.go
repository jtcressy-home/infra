package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/netip"

	"tailscale.com/client/tailscale"
	"tailscale.com/ipn"
)

func main() {
	lc := &tailscale.LocalClient{}
	ctx := context.Background()
	prefs, err := lc.GetPrefs(ctx)
	if err != nil {
		log.Fatalf("%v", err)
	}
	routes := map[netip.Prefix]bool{}
	for _, item := range prefs.AdvertiseRoutes {
		routes[item] = true
	}
	newRoute, err := netip.ParsePrefix("10.43.0.0/16")
	if err != nil {
		log.Fatalf("error parsing CIDR address: %v", err)
	}
	routes[newRoute] = true
	prefs.AdvertiseRoutes = []netip.Prefix{}
	for k, _ := range routes {
		prefs.AdvertiseRoutes = append(prefs.AdvertiseRoutes, k)
	}
	maskedPrefs := &ipn.MaskedPrefs{
		Prefs:              *prefs,
		AdvertiseRoutesSet: true,
	}
	prefs, err = lc.EditPrefs(ctx, maskedPrefs)
	if err != nil {
		log.Fatalf("error setting prefs: %v", err)
	}
	bts, err := json.Marshal(prefs)
	if err != nil {
		log.Fatalf("%v", err)
	}
	fmt.Println(string(bts))
}
