<!--
PUBLISH VIA DJANGO ADMIN → Blog → Posts → Add post
  Title:  Renting a Front Door: Exposing My Homelab Without Opening a Port
  Tags:   homelab, kubernetes, k3s, networking, security, wireguard, traefik, self-hosting, gitops
  Status: Published
Paste everything below this comment into the Body field. (HTML comments don't render.)
-->

The default way to put a self-hosted service on the public internet is to forward ports 80 and 443 from your home router to whatever's serving them. It works. It's also two things I didn't want: my home IP address sitting in public DNS for anyone to look up, and a permanent hole in my router pointing straight at my cluster.

So the public face of my homelab isn't my house at all. It's a $5 VPS that holds the public IP and tunnels back to me over WireGuard. My home router has **zero inbound ports open** — not 443, not 80, nothing. This is a reflection on why that shape, and what it actually costs, because the tradeoffs are more interesting than the setup.

## The shape of it

Every public hostname I serve — the apex, the `dev`/`qa` environments, the `*.review` wildcards — resolves in DNS to a small DigitalOcean droplet, not to me. The droplet does almost nothing: it accepts inbound 80/443 and passes the raw TCP straight down a WireGuard tunnel to my home gateway, which hands it to Traefik on the cluster (a MetalLB address, `192.168.70.240`). Traefik terminates TLS and routes to the app.

The tunnel itself is unremarkable — a WireGuard client on my UniFi gateway dialing the droplet on a single UDP port:

```ini
# home gateway → VPS, conceptually
[Peer]
PublicKey  = <droplet-public-key>
Endpoint   = <droplet-ip>:51820
AllowedIPs = 10.12.12.1/32
```

And the droplet's entire job is about ten lines of stream proxy — conceptually:

```text
# inbound 443 on the public IP → straight down the tunnel, untouched
443  →  10.12.12.2:443   (TCP passthrough, no TLS termination)
 80  →  10.12.12.2:80
```

That's the whole machine. It doesn't know what apps I run, it doesn't hold a single certificate, and it never decrypts anything. It moves bytes.

## Why this shape, and not a port forward

The interesting decision isn't *how* — it's *where I drew the trust boundary*. I drew it at home, on purpose, and everything good about this setup falls out of that one choice.

**TLS terminates at home, so the VPS only ever sees ciphertext.** Certificates are issued and held by cert-manager in the cluster (Let's Encrypt, HTTP-01). The droplet does L4 passthrough, which means it physically cannot read the traffic flowing through it or steal a private key it never has. If someone roots my droplet tomorrow, they get a dumb pipe — not my data, not my certs, not a foothold in my network beyond a tunnel that only routes to one place. A rented box I don't fully trust is exactly the box that should be holding nothing worth stealing.

There's a small elegance to this that I didn't appreciate until I watched it work: even ACME cert issuance flows through the tunnel. The HTTP-01 challenge comes in on port 80 over the same path as everything else, hits Traefik, and gets answered. Nothing is special-cased. The public surface is *one* path, and it's the tunnel.

**My home IP is off the internet.** Public DNS points at the droplet. A scan of my residential IP finds nothing, because there's nothing to find — no open ports, no banner, no hint that anything is hosted here at all. The thing being probed and attacked is the disposable box, not the place I live.

**WireGuard is the right spine for this.** One UDP port between two machines I control, kernel-fast, and quiet — it doesn't announce itself the way an open 443 does. (It's also, notably, *not* the same tool I used elsewhere: the tunnel that carries my torrent traffic to a commercial VPN is OpenVPN, because that provider doesn't speak WireGuard. Using the right tunnel for each job instead of forcing one everywhere is its own small lesson.)

**The front-end is deliberately dumb.** All the intelligence — ingress rules, TLS, cert-manager, routing, the app definitions — lives in the cluster, under GitOps, where I already manage it. The droplet has no opinions. That separation means I could rebuild the public front-end from scratch in minutes and lose nothing, because nothing important was ever there.

## What it costs

It would be dishonest to write this up as free. It isn't.

**Every public byte now takes a detour.** All inbound traffic flows home through one small VPS, so its bandwidth, its location, and the extra network hop are now my public ceiling. For a personal site and some dashboards that's invisible; if I were serving video to strangers it would not be.

**It's a single point of failure for *public* access.** If the droplet or the tunnel goes down, the outside world can't reach my apps — even though everything is still happily running at home and reachable on the LAN. I've traded one failure mode (exposed home) for another (dependent front-end). That's a deliberate trade, not a free win.

**The droplet is the one corner that isn't GitOps.** This is the part I'm least proud of. My entire cluster is declarative — every app, every cert, every firewall policy is a reviewable diff. The VPS's proxy and WireGuard config live *on the droplet*, hand-maintained, version-controlled by nothing but my memory. It's the seam where the otherwise-clean story leaks. Codifying it (even a small Terraform + cloud-init) is the obvious next move, and writing this is mostly me admitting I haven't done it yet.

**I'm still trusting a provider with my metadata.** They can't read my traffic, but they can see that it exists, where it comes from, and roughly how much of it there is. Encryption at home moves the boundary; it doesn't make the box disappear.

## The same instinct, twice

I closed the last open ports on my router around the same time I moved my torrent client behind a VPN, and the two are the same idea wearing different clothes: **don't guard an exposure — relocate it.** Forwarding 443 from my router guards a hole. Renting a front door removes the hole and puts the exposure somewhere disposable, off-premises, holding nothing. Being able to close 80/443 at home wasn't a separate hardening task; it was just the natural consequence of the public entry point no longer being my house.

## Takeaways

- **Decide where your trust boundary goes, then make the architecture serve it.** "TLS terminates at home" is one sentence, and it's the reason a compromised front-end is a non-event.
- **Keep the exposed thing dumb and disposable.** The less your public surface knows, the less it can leak, and the cheaper it is to lose.
- **No-open-ports has a price: a hop and a dependency.** Worth it for me; name the cost honestly before you copy the pattern.
- **Codify even the boring edge.** The one box I left out of GitOps is the one I'd most regret losing the config for. Don't be me — yet.

My router's inbound rules are empty, my home IP isn't in anyone's DNS, and the only thing facing the internet is a machine I could throw away and rebuild before lunch. For the price of a hop and five dollars a month, that feels like a good front door.
