<!--
PUBLISH VIA DJANGO ADMIN → Blog → Posts → Add post
  Title:  Closing Ports by Opening a Tunnel: A Homelab Hardening Story
  Tags:   homelab, kubernetes, k3s, gitops, flux, networking, security, vpn, self-hosting
  Status: Published
Paste everything below this comment into the Body field. (HTML comments don't render,
so it's harmless to leave this in, but cleaner to delete it.)
-->

I spent a weekend hardening my homelab's network and ended up deleting a firewall rule I'd been quietly uneasy about for years. The interesting part wasn't the rule — it was realizing that the most secure version of a port forward is no port forward at all, and that I could get there without losing anything I actually used.

This is less a how-to than a reflection on what that migration taught me. If you run a K3s-and-Flux homelab, the shape of it will be familiar.

## The itch

It started innocently. I turned on UniFi's CyberSecure features, drew up a set of zone-based firewall policies, and put my cluster, IoT, and guest networks into their own default-deny zones. Somewhere in the middle of that, I did the thing you're supposed to do periodically and never do: I read my own port-forward list out loud.

Most of it was defensible. One entry was not. My torrent client had a port forwarded straight from the WAN to a pod in the cluster. Every peer in every swarm could see my home IP, and the path led to a piece of software whose threat model is "talk to thousands of strangers on the internet." It was the least-hardened service on the network sitting behind the most-exposed rule.

The instinct is to *manage* that exposure — lock it to the right VLAN, watch it, hope. The better instinct, the one this whole exercise pushed me toward, is to *eliminate* it. A port forward is a permanent hole in the perimeter. The most defensible hole is the one that isn't there.

## The idea: don't forward a port, borrow one

Torrent clients want an inbound port so peers can reach you. That's the whole reason the forward existed. But there's no law that says the reachable address has to be *mine*.

A commercial VPN with port forwarding (I use PIA) gives you exactly this: your traffic egresses through the provider, and the provider hands you a forwarded port on *their* IP that peers can connect to. Pair that with a kill-switch — no VPN, no traffic, full stop — and the calculus flips entirely:

- The home WAN IP disappears from the swarm.
- Inbound peer traffic arrives through the provider, not through a hole in my router.
- If the tunnel ever drops, the client goes dark instead of leaking.
- And I get to delete the router forward for real.

Defense in depth usually means adding layers. This was the rarer, more satisfying kind: removing a layer of attack surface and getting *more* containment for it.

## The shape of it

Because everything I run is Kubernetes, the implementation is a sidecar. [gluetun](https://github.com/qdm12/gluetun) runs in the same pod as the torrent client, sharing its network namespace, so the client has no network of its own — every packet it sends or receives goes through gluetun's tunnel and its kill-switch firewall. The provider's forwarded port gets synced into the client whenever it changes, so inbound peers keep working across reconnects.

It's all GitOps. Credentials are a sealed secret; the whole change is a Flux-reconciled pull request; the rollback is `git revert`. The core of it is unremarkable once it works:

```yaml
gluetun:
  image: { repository: ghcr.io/qdm12/gluetun, tag: v3.41.1 }
  env:
    VPN_SERVICE_PROVIDER: private internet access
    VPN_PORT_FORWARDING: "on"
    PORT_FORWARD_ONLY: "on"          # refuse servers that can't forward
    FIREWALL_OUTBOUND_SUBNETS: "10.42.0.0/16,10.43.0.0/16,192.168.70.0/24"
  securityContext:
    capabilities: { add: [NET_ADMIN] }
```

"Once it works" is carrying a lot of weight in that sentence. Getting there is where the lessons were.

## What I expected versus what actually happened

### Assumptions are the expensive part

I reached for WireGuard out of habit — it's faster, lighter, the modern default. gluetun crash-looped immediately:

```text
ERROR VPN settings: provider settings: VPN provider name is not valid for Wireguard
INFO Shutdown successful
```

PIA, it turns out, is OpenVPN-only in gluetun; WireGuard "is a slow work in progress." Ten minutes of confusion for a thing the docs state plainly. The lesson isn't "read the docs" — it's that the assumption I didn't know I was making (every provider supports every protocol) was the one that cost me. OpenVPN is heavier on CPU, so I lifted the sidecar's limit to a full core and moved on. Inbound port forwarding still works fine for peer-to-peer over OpenVPN, which is all I needed.

### Conveniences have sharp edges

The provider hands you the forwarded port through a `{{PORT}}` placeholder in a command. My Helm chart helpfully runs every environment value through its templating engine — so Helm tried to evaluate `{{PORT}}` itself and failed: `function "PORT" not defined`. The fix is to escape it so the templating layer emits the literal token for the *next* layer to consume:

```yaml
# {{ "{{PORT}}" }} survives Helm's tpl and reaches gluetun as a literal {{PORT}}
```

Every convenient abstraction is a layer that will, eventually, interpret something you meant for someone else. Worth remembering the next time a templating engine is being "helpful."

### "Green" is not "healthy"

This was the one that actually stung. I merged the change, watched Flux report the release as Ready and CI go green, and told myself it was done. Then the web UI returned "no available server."

The HelmRelease had `disableWait: true`. Flux marks a release Ready the moment Helm *applies* it — it does not wait for the pod to roll out. So my dashboards were cheerfully green while the pod crash-looped underneath them. The deploy gate I'd been trusting proved that the manifest applied, nothing more.

It's a good reminder to know what your signals actually assert. "The pipeline is green" answers a narrower question than "the thing works," and the gap between those two questions is exactly where outages live.

### The firewall you add is a firewall you debug

gluetun's kill-switch does its job thoroughly: it drops everything that isn't the tunnel. Including, at first, the readiness probe and the web UI. Containment cuts both ways — the same firewall that stops leaks also stops your cluster from reaching the service until you explicitly allow the pod, service, and LAN subnets back in. The fix was three CIDRs; the lesson was that "lock everything down" and "and now nothing can talk to it" are the same sentence said twice.

There was a smaller one too: gluetun's bundled DNS server kept trying to download blocklists through the tunnel, timing out, and restarting on a loop. I don't need DNS-level blocking on a torrent box — the network already does content filtering a layer up — so I turned it off. Trimming the noise you don't need is part of the job; a log full of benign warnings is a log you stop reading.

## Did it actually work?

Yes — and the proof was satisfyingly mundane. I deleted the router's port forward, pulled down a Linux ISO, and watched inbound peers connect through the provider's forwarded port at full speed. No home IP in the swarm, no hole in the router, and the dynamic port re-syncing across reconnects without restarting the client. The thing I'd been uneasy about for years was simply gone, and nothing I cared about went with it.

## The port I kept, and why hardening isn't zealotry

I did not close every port. My media server still has one forward open, and I left it open on purpose.

The honest comparison: that forward exposes an authenticated, TLS-terminated, actively maintained application that's designed to face the internet. The one I closed exposed a torrent client. Those are not the same risk, and treating them as equally urgent would be security theater. There are cleaner options for the media server too — a mesh VPN for my own devices, the vendor's relay, a reverse proxy — but none of them are *free*, and the exposure they'd remove is small.

That's the part I keep relearning. Hardening isn't a score you maximize; it's a set of trades you make with your eyes open. The torrent port was a bad trade, so I eliminated it. The media port is a reasonable one, so it stays. Knowing the difference is most of the skill.

## Takeaways

- **Eliminating surface beats guarding it.** The strongest control I added this weekend was a rule I deleted.
- **Name your assumptions before they cost you.** "This provider supports this protocol," "this value won't be re-interpreted," "green means healthy" — each one was wrong, and each was invisible until it broke.
- **Trust behavior, not checkmarks.** A passing gate proves what it measures, which is usually less than you hope.
- **GitOps makes all of this reviewable.** Every misstep above was a diff, a log line, and a revert away from safe. That's the real luxury of running this stuff as code — not that you don't make mistakes, but that the mistakes are small, visible, and cheap to undo.

The router's port-forward list is one line shorter now, and the line that's gone is the one that mattered.
