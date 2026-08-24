from pathlib import Path


def test_x402_client_example_documents_complete_payment_retry_flow():
    example = Path("docs/x402-client-example.js").read_text(encoding="utf-8")

    for required_fragment in (
        "response.status === 402",
        "payment.token_contract",
        "payment.receiver_address",
        "writeContract",
        "waitForTransactionReceipt",
        "chain_id: BASE_CHAIN_ID",
        "X-Payment-Proof",
        "fetch(url",
        "settlement_status=discovery_only",
    ):
        assert required_fragment in example