# Who actually pays us — measured 2026-11-19

The only measurement in this project taken from the buyer's side. Everything
else measures our own supply.

## How it was measured

Base mainnet, read directly over a public RPC (`eth_getCode`,
`eth_getTransactionCount`, `eth_call` for the USDC balance). One call per field,
one row per address. No payment, nothing written.

The nine addresses are the ones the dashboard classifies as `external` — real
customers, as opposed to our own demo key, our canaries and the market sampler.

## The nine

    address                                       kind      nonce   USDC held
    0xee523a5145cfaea8ccec34fb364a2a92fad62a3a    CONTRACT      3     17.4947
    0x6a0b784cf4e3f79e0bca889e35a1b3aa1dc24518    EOA           0     11.1338
    0x171d8021b98c53dcbb3c9c30cbbbeb1b01850fca    EOA          14     15.3161
    0x902dcf34e53695bdea2ffb354b1a2e58bd598256    CONTRACT     67     47.7288
    0x9a1066feec0822996875a28a3d4e058175af6c92    EOA           0      1.0113
    0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a    EOA          53      0.2104
    0x0bbd2fec713482d888b6d7d7ea7ec8c632297aa8    EOA           0     15.0050
    0xce4fbd6ea0d2e73a8d8959b4c8e28ec39bd3c236    CONTRACT      2     18.7870
    0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7    EOA           0      4.4362

One of these is not a customer: `0xee523a…2a3a` is Ernest, the auditor we paid
$15.0001. He holds $17.4947, which is our payment plus his earlier balance — a
useful sanity check that the reading is correct.

So: **eight real external buyers**, ten payments, $0.041 total.

## What the shape says

**Three of nine are contracts.** A contract is a smart wallet or an agent
runtime. No human sits behind one directly.

**Four of nine have `nonce 0`.** They have never sent a transaction of their own.
They exist to hold USDC and sign EIP-3009 authorizations, which the facilitator
submits and pays gas for. That is a programmatic wallet, not a person clicking
send in a wallet app.

**All of them are funded.** Between them they hold $131.13.

## The number that matters

    held across the eight buyers    $131.13
    spent with us, all time           $0.054

The wallets have money. They are not unable to pay. They paid once and did not
come back. One of the eight ever returned (three payments in October); the other
seven paid once.

## What this does not prove

It does not prove they are agents rather than humans — a person using an x402
client would also pay through the facilitator and also leave a `nonce 0`. It
proves the wallets are programmatic in shape and funded in fact.

It also does not say why they left. The likely answer is next door: the signal
route, which is the one product with a public record, measures 1 hit in 84
(`docs/SIGNAL_EDGE_FINDING.md`). An agent that pays once, gets a signal that does
not work, and does not return is behaving rationally.

## What follows

The bottleneck is not discovery, not price and not the 402 challenge — all three
were checked and are sound. It is that the product did not survive a second
purchase. Whatever is led with next has to be something a buyer can verify for
themselves, because the buyers who arrived had the money and chose not to spend
it twice.
