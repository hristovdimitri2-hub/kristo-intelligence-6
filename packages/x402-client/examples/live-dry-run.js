/**
 * Live smoke test against the production Kristo Intelligence API.
 * Uses dry-run mode: displays the real 402 payment challenge WITHOUT paying.
 *
 *   node examples/live-dry-run.js
 */
import { KristoX402Client } from "../src/index.js";

const client = new KristoX402Client({ autoPay: false });

const result = await client.get("/api/stats");

if (result.paymentRequired) {
  console.log("✅ Live x402 handshake parsed from production:\n");
  console.log(JSON.stringify(result.paymentRequired, null, 2));
  console.log(
    "\nThis is exactly what an AI agent sees and pays." +
    "\nWire a `pay` callback (see README) to complete the flow automatically."
  );
} else if (result.ok) {
  console.log("ℹ️  Free tier call succeeded (no payment required):");
  console.log(Object.keys(result.data ?? {}).join(", "));
} else {
  console.error("❌ Unexpected response:", result.status, result.data);
  process.exit(1);
}
