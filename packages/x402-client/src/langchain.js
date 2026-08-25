/**
 * LangChain integration for kristo-x402-client.
 *
 * Zero hard dependencies: the factory returns the exact shape LangChain's
 * `DynamicStructuredTool` constructor accepts, so users wire it in one line:
 *
 *   import { DynamicStructuredTool } from "@langchain/core/tools";
 *   import { createKristoTool } from "kristo-x402-client/langchain";
 *
 *   const tool = new DynamicStructuredTool(
 *     createKristoTool({ client, path: "/api/stats", name: "kristo_market_stats" })
 *   );
 */

/** Tool factory: binds one paid endpoint to an agent-callable tool. */
export function createKristoTool({
  client,
  path,
  name = "kristo_intelligence",
  description,
}) {
  if (!client) throw new TypeError("createKristoTool: `client` is required.");
  if (!path) throw new TypeError("createKristoTool: `path` is required.");

  return {
    name,
    description:
      description ??
      `Fetch DeFi market intelligence from the Kristo Intelligence API (${path}). ` +
      `Payments for metered access are settled automatically in USDC on Base ` +
      `via the x402 protocol.`,
    // Plain JSON schema — DynamicStructuredTool accepts this directly.
    schema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
    func: async () => {
      const result = await client.get(path);
      if (result.ok) return JSON.stringify(result.data);
      if (result.paymentRequired) {
        return JSON.stringify({
          error: "payment_required",
          detail: result.paymentRequired,
        });
      }
      return JSON.stringify({ error: "request_failed", status: result.status });
    },
  };
}
