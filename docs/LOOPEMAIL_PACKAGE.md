# LOOPEMAIL PACKAGE — the email to the seller of "loopA" (status: waiting for a channel)

## What loopA is (summary)
- Settlement address: starts with `0xcf92…` (the full address is in RECON_FINDINGS.md)
- Real third-party x402 API: **14 payers, 117 tx/week, $0.002/call** —
  the most successful third-party listing measured so far
- In a loop with our buyer `0x5f64` (the only confirmed agent-trader on the
  market): every day it buys house data + loopA data → swap through the router

## Identification result (04.09): NOT a PayAPI listing
Checked ALL PayAPI candidates at the price $0.002/call (402-probe of each,
reading the payTo from the challenge):
- DNS & Domain Intelligence → house cashier (0xFFc4…) ❌
- Screenshot & PDF Capture → house cashier ❌
- Web Scraper & Content Extractor → house cashier ❌
- Skim – Clean Reader → another cashier (0x63AE…) ❌
- SameDayDesk → another cashier (0x8904…) ❌
- Lemon Toolshed → another cashier (0x0adc…) ❌

→ loopA is an x402 API listed **outside PayAPI** (probably x402scan, since the
crawler pays for it). Identifying the seller requires a channel we do not have
yet.

## Available channels (in order of effort)
1. **x402scan** → look for the settlement address in the resource list; if the
   listing is there, the seller is visible (name/site). *Optional task for the
   next session: scan of the 6777 receivers against the x402scan catalog.*
2. **A direct question to Chet** (ONLY once, as a "data" line appended to an
   existing email, not a new thread): "does your seller inventory include a $0.002 API
   whose settlement starts 0xcf92? Happy to cross-link with their seller."
   *Risk: low, but wait for the first band so that it is not the only line in the email.*
3. **Waiting:** the crawler visits loopA weekly → if it ever pays us,
   the seller will probably see our listing in the same source.

## READY TEXT (address-agnostic — comes into effect the moment a channel is found)

> **Subject:** we share a customer — x402 API seller to x402 API seller
>
> Hi — I run an x402-native DeFi signals API on Base (settlement-verified,
> $0.003/call). On-chain I noticed a wallet that pays both your endpoint and
> mine in a steady daily loop — someone is actively using both of our data
> in one pipeline, which I find genuinely encouraging for this market.
>
> I made the integration path public (a one-command reference agent), and
> I'm happy to cross-link related APIs with you — buyers who need clean
> reading and scraping probably also need signals, and third-party sellers
> are thin enough on the ground that findability compounds.
>
> Repo with the demo agent: https://github.com/hristovdimitri2-hub/kristo-intelligence-6
>
> — Dimitri

**Rules observed in the text:** zero wallet addresses; zero "I am watching you"
tone ("on-chain I noticed" is a public fact presented as encouragement); zero requests.

## Decision (by the "two sessions or dead" rule)
The move is NOT declared dead — its goal (access to the only live buyer)
is too valuable. But it is **demoted to passive**: ready text + 3 channels in this
file. It activates only on the triggers: the loopA seller appears in a directory,
Chet replies with an identification, or the crawler data reveal the domain.

## Identification 2 (04.09 night): loopA is a MetaMask retail developer
- The bytecode of `0xcf92…` starts with `0xef0100` → **EIP-7702 delegation** (EOA,
  delegated to a contract). The implementation is **"MetaMask: EIP-7702 Delegator"**
  (Basescan title: 0x63c0…32b)
- The wallet holds 43 dust meme tokens, $5.42 USDC, 0.0013 ETH → a classic
  **personal MetaMask account of a retail developer**, testing his API with
  his own wallet — not a company participation
- Consequence for the email: the seller is an individual with MetaMask; a public
  contact does NOT exist (no ENS, no name). The text remains ready —
  "address-agnostic". The channels (x402scan listing search / one line to Chet)
  remain the path to him
