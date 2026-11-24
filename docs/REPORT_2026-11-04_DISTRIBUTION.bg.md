# REPORT No. 2 — SOFTWARE DISTRIBUTION
### Kristo Intelligence · 04.11.2026

---

## In brief, in two minutes

The software was **ready and invisible**. It could be bought, but nobody knew it
existed. Public search found us with **one page**.

Today we are in **over 12 external directories and catalogs**, with **two open PRs** in
popular lists, with confirmed **Google Search Console**, **Bing** and **IndexNow**, and
with a **measurable** audience: **514,530 requests** come to us, not to someone else.

**But I have to say it honestly:** part of this is "**submitted and confirmed**", not
"**measured**". Google and Bing show data after **24–48 hours**. And three of the
directories that the x402 ecosystem maintainer himself recommended, we **have not used
yet**.

---

## 1. Where we are now — 12+ places

| Where | What it is | Status |
|---|---|---|
| **npm** | `kristo-x402-client@1.1.1` — the client the integrator installs | ✅ Published, speaks the fast rail |
| **x402scan** | The directory the x402 maintainer pointed to as **#1** | ✅ Registered: 6 paid + 8 free |
| **MCP Registry** (official) | The registry Claude Desktop / Cursor draw from | ✅ **6.2.0** — the newest version |
| **x402-list.com** | Independent meter | ✅ **96/100, "Strong", #2 of 210 in AI**, 100% uptime |
| **x402-trust.com** | Independent meter No. 2 | ✅ **6 endpoints with grade A**, average **81.2** against 54.2 for the ecosystem, **100% uptime** against 54.1% |
| **Socket.dev** | Security analysis of the npm package | ✅ Indexed |
| **mcpfind.org** | MCP catalog | ✅ Indexed |
| **glama.ai** | MCP catalog with a rating | ⚠️ **Outdated cache** — shows `toolCount: 3`, while the live one serves **6** |
| **agentropolis.io** | Agent directory | ✅ Indexed |
| **Sato Hub** | x402 merchants | ✅ Indexed |
| **Council of AI** | Count of x402 settlements | ✅ We have a row (with an **outdated** result — see §4) |
| **vet402.com** | x402 verifier | ✅ |
| **x402-foundation issue #3719** | Our public grant application | ✅ Closed, with a good outcome |

### 📌 Two open PRs for inclusion in popular lists

| PR | Repo | Status |
|---|---|---|
| **#13219** | `punkpeye/awesome-mcp-servers` | ⏳ Open — blocked **exactly** on the outdated number from Glama |
| **#1308** | `xpaysh/awesome-x402` | ⏳ Open, `mergeable_state: **clean**` since 24.08 |

---

## 2. What we fixed so that we can be found

This is the part that **does not depend on anyone's passwords** and is done today.

### Search engines

| What | Before | Now |
|---|---|---|
| **Google Search Console** | we had none | ✅ Confirmed (URL-prefix — Domain is impossible, `onrender.com` belongs to Render) |
| **Bing Webmaster** | we had none | ✅ Connected — it came **ready-made** from Google |
| **IndexNow** | The code existed, **nobody had ever run it** | ✅ **11 addresses** submitted to Bing, Yandex and Seznam — accepted (200/202) |
| **Sitemap** | Full of `noindex` pages, and the real `/validation` **was missing** | ✅ **11 URLs**, the three `noindex` removed |
| **robots.txt** | was fine | ✅ Still is |
| **Meta tags** | **not a single one** on the indexable pages | ✅ og + twitter + canonical + **valid JSON-LD** on all |
| **Social preview** | bare address | ✅ Image **1200×630** and description |
| **`/pricing` and `/terms`** | **404** — and x402-list checks exactly them | ✅ Both created, generated from the live price map |

### The AI agents — our most important audience

**52.2%** of all requests come from AI agents. That is why the documents that **they**
read were the most expensive defect:

| File | What it taught | Now |
|---|---|---|
| **`llms.txt`** | Only the **old** payment protocol, and "~2 seconds" for a path that waits **24** | Both paths, **the standard one first**, with the codes 200/401/402/425 |
| **`/api/v1/quickstart`** | All three examples taught the **slow** path | The fast one is the first step |
| **`agents.json`** | **5 of 6** routes | **6 of 6**, and it is now **generated** from the single source |
| **`mcp.json`** | **3 of 6** | **6 of 6** |
| **`ai-plugin.json`** | **not a single** route + "one free call" (false) | All 6, honestly |
| **`/.well-known/kristo-agent.json`** | Taught only the slow path, without units | Fixed |
| **The MCP server** | Sold **3 of 6** products — **the flagship could not be bought** | **6 of 6** |

### The two beginnings that everyone sees first

| What | Before | Now |
|---|---|---|
| **The home page** | All of its buttons served **machine files**. A person who wants to buy **had no clickable path** to payment. `/launch` was not linked | **12 links** (there were 7). Every human page now has the home page as an inbound one |
| **The README on GitHub** | Showed a red "**F**" (license unrecognized), while the connector badge glows "A" | **Fixed** — `pyproject.toml` with PEP 639 + `SPDX-License-Identifier: MIT` |

---

## 3. Who actually reads us — measured, not assumed

Today's live numbers from the dashboard:

| Who | Requests | Share |
|---|---|---|
| **AI agent** (Claude Code, two versions) | 268 455 | **52.2%** |
| **Search engine or bot** (Agent402 crawler) | 86 387 | 16.8% |
| **Programmatic client** (`node`, `python-requests`) | 82 892 | 16.1% |
| **External monitor** (third-party liveness checks) | 76 796 | 14.9% |
| **Browser (human)** | **0** | **0%** |

**Total: 514 530 requests.**

### What these numbers say

1. **Our audience is machines, not people.** Zero browsers. That is why `llms.txt`, MCP
   and the specifications are **more important than any human page** — and that is why
   the errors in them were the most expensive.
2. **Claude Code is our biggest user** with 268 455 requests. One agent asks many
   times — that is normal, but it means that **precisely its document**
   (`llms.txt`) had to be correct.
3. **~77 000 requests are third-party liveness checks** — they are not clients. It is
   good to know that, so the traffic is not read wrongly.
4. **The revenue comes from elsewhere.** Traffic is not sales: **50 sales,
   $0.164, 10 payers over 63 days**. The external (real) ones are **$0.09 from 10 payers**.

---

## 4. What remains

### 🔴 Three directories that the x402 maintainer **himself** recommended to us — and we are not in them yet

I found them in the **closing comment of our own grant application** (13.10). Nobody
had read them:

| Directory | Checked | Why it matters |
|---|---|---|
| **Agentic.Market** | `q=kristo` → **0**. But `q=onrender` → **10 colleagues** from `.onrender.com`, which **are** listed | So the path works, we are simply not on it |
| **Pay.sh** | 76 providers, 77 provider pages — **we are not there** | — |
| **app.ampersend.ai/discover** | Exists, but is an entirely browser-based application | — |

**Something important that I checked so as not to tell you a convenient story:** the four
directories are **independent**. I checked it twice — **0 of 10** colleagues that
Agentic.Market lists are in x402scan, and Pay.sh gives `aggregator_count: 0`. That is,
**one action does not unlock the others**.

### 🟠 One public row that harms us — and awaits an email

**Council of AI** measures "what is declared against what is received" and writes for
`/api/v1/signal`: **DELIVERED** on 2026-09-06 · *"host reported a settlement but
its PAYMENT-RESPONSE did not parse into a tx reference"*.

**This is exactly the thing that makes an agent not integrate.** And it is outdated by
**16 days** — it was fixed on 22.09, and the audit has **n=1** and was never measured
again.

Their page says explicitly: *"send the URL with «re-check» in the subject and the next
run will replace the row with what it sees."*

**Only one email is needed.** The draft is ready. I cannot send it — their form is
JavaScript-only, and I have no access to your mail. **Ask me and I will give you the
exact address, the ready text to copy and where to click.**

### 🟡 Hangs on others

| What | Who |
|---|---|
| Glama still shows `toolCount: 3`, while the live server gives **6** | Glama — it is not fixed with code, but with a re-crawl |
| PR #13219 | punkpeye — blocked **exactly** on that number |
| PR #1308 | xpaysh — it is clean, it just needs a nudge |
| mcp.so verification | mcp.so (comment #3441) |
| PulseMCP | Takes from the registry — fixes itself |
| Smithery | **Dead** — proxy stopped 31.10. The channel is being written off |

### ⏸️ Awaiting your decision

| # | Question | Price |
|---|---|---|
| 1 | **Paid channels** — mcpmarket ($69) and CDP Bazaar ($0.25) | So far **$0** spent |
| 2 | **Shall we quote the x402-trust badge** (grade **A**) on `/validation`? | Free — we have already earned it |
| 3 | **The three missed directories** — shall we submit them one by one? | Free |
| 4 | **The email to Council of AI** for a new measurement | Free — only you can |

---

## 5. The honest reckoning

### ✅ What is **proven**

- We are in **12+ external places**, with **two independent A grades**
- **x402-list: #2 of 210** in AI, 96/100
- **Google, Bing and IndexNow**: confirmed and submitted
- **514 530 requests** come to us — measured
- **npm 1.1.1 + MCP Registry 6.2.0** — both the newest

### ⚠️ What is **submitted, but not yet measured**

- The data in Google Search Console and Bing appears after **24–48 hours**.
  We will have to look at it in **Search Console → "Performance"**.
- The **11 URLs** are in the sitemap, but are not indexed yet — that takes days.
- The three new directories have not been submitted yet.

### ❌ What is **not** done

- The three directories from §4
- The email to Council of AI
- Glama (it is not our job, but it is holding up our PR)
- Paid channels ($0 spent)

---

## 6. One sentence for the end

Distribution is no longer "we hope they will find us". They have found us —
**514 530 times**, and **more than half** are AI agents that read exactly the files
we fixed today. All that remains is to finish the three free channels and one email.
