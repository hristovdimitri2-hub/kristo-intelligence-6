"""A2A surface: the Agent Card and the JSON-RPC endpoint behind it.

The failure this file exists to prevent is a card that DESCRIBES things which
are not there — a `url` that 404s, a `skills` entry for a route that does not
exist, a capability advertised as supported whose method answers -32601. A
directory fetches the card, then fetches what the card points at, and it is
right to: a card is a promise, and these tests hold it to the promise.
"""

import os

import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main

    return main.app.test_client()


def _card(client):
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200, response.status_code
    return response.get_json()


def _send(client, text, req_id=1):
    return client.post("/a2a", json={
        "jsonrpc": "2.0", "id": req_id, "method": "message/send",
        "params": {"message": {"role": "user", "messageId": "m-%s" % req_id,
                               "parts": [{"kind": "text", "text": text}]}},
    })


# ── 1. the card is where the spec says it is, and is complete ───────────────
def test_the_card_is_served_at_the_standard_path_with_every_required_field(client):
    card = _card(client)

    for field in ("protocolVersion", "name", "description", "url", "version",
                  "capabilities", "defaultInputModes", "defaultOutputModes",
                  "skills"):
        assert field in card, "the A2A card is missing required field %r" % field
    assert card["protocolVersion"] == "0.3.0"
    assert isinstance(card["skills"], list) and card["skills"], "no skills"
    for skill in card["skills"]:
        for field in ("id", "name", "description", "tags"):
            assert field in skill, "skill %r is missing %r" % (skill.get("id"), field)


# ── 2. THE guard: nothing the card points at may be broken ─────────────────
def _path_of(url: str) -> str:
    """The request path of an absolute URL the card published."""
    without_scheme = url.split("://", 1)[-1]
    slash = without_scheme.find("/")
    return without_scheme[slash:] if slash >= 0 else "/"


def test_everything_the_card_points_at_answers(client):
    """A card is a promise. Follow every link it makes and check each one.

    This is the test that fails if someone publishes a card naming a route we do
    not serve, moves an endpoint without moving the card, or lets a product's
    free sample rot — which is how a card quietly becomes a dead end.
    """
    from main import REAL_X402_ROUTES

    card = _card(client)

    published = [
        ("card.url", card["url"]),
        ("card.documentationUrl", card["documentationUrl"]),
        ("card.iconUrl", card["iconUrl"]),
    ]
    for key, link in (card.get("x402", {}).get("discovery") or {}).items():
        published.append(("x402.discovery.%s" % key, link))

    # Every product the card advertises must have a WORKING free sample: the
    # card's whole offer is "ask me and I will show you the shape and the price".
    for route in REAL_X402_ROUTES:
        published.append(("sample for %s" % route["endpoint"],
                          "%s/sample" % route["endpoint"]))

    for name, link in published:
        path = _path_of(link) if "://" in link else link
        response = client.get(path)
        assert response.status_code == 200, (
            "the card points at %s (%s) and it answers %s"
            % (path, name, response.status_code))

    # And every skill the card lists is one of those products, by id.
    real_ids = {route["id"] for route in REAL_X402_ROUTES}
    assert {skill["id"] for skill in card["skills"]} == real_ids, (
        "the card's skills and our real products have drifted apart")


def test_each_skill_names_a_route_that_exists_at_the_price_the_paywall_charges(client):
    """A skill is a product claim. Check the route is real and the price is ours.

    The price must come from the paywall's own map: an alias or a rounded
    headline can advertise a number no caller is ever charged.
    """
    from main import X402_PRICE_MAP, REAL_X402_ROUTES

    card = _card(client)
    real = {route["endpoint"]: route for route in REAL_X402_ROUTES}
    routes = {route["endpoint"] for route in REAL_X402_ROUTES}

    for skill in card["skills"]:
        assert skill["id"] in {r["id"] for r in REAL_X402_ROUTES}, (
            "skill %r is not one of our products" % skill["id"])
        # The skill's description must quote this route's real price.
        endpoint = next(e for e, r in real.items() if r["id"] == skill["id"])
        expected = float(X402_PRICE_MAP.get(endpoint, 0.0))
        assert ("%.3f" % expected) in skill["description"], (
            "skill %r does not quote its real price %.3f"
            % (skill["id"], expected))
        assert endpoint in skill["description"], (
            "skill %r does not name its route" % skill["id"])

    assert len(card["skills"]) == len(routes), (
        "the card lists %d products and we sell %d"
        % (len(card["skills"]), len(routes)))


# ── 3. the card must not advertise what is not implemented ─────────────────
def test_the_card_advertises_no_capability_it_cannot_serve(client):
    """Over-claiming is the same defect as a dead link, one level up.

    `streaming` is declared false. If someone flips it to true, this test sends
    the method it would imply and requires it to work — so the claim cannot be
    made without the feature.
    """
    card = _card(client)
    caps = card["capabilities"]

    if not caps.get("streaming"):
        response = client.post("/a2a", json={
            "jsonrpc": "2.0", "id": 9, "method": "message/stream",
            "params": {"message": {"role": "user", "parts": []}}})
        assert response.get_json()["error"]["code"] == -32601, (
            "streaming is declared unsupported, so message/stream must say so")
    if not caps.get("pushNotifications"):
        for method in ("tasks/pushNotificationConfig/set",
                       "tasks/pushNotificationConfig/get"):
            response = client.post("/a2a", json={
                "jsonrpc": "2.0", "id": 10, "method": method, "params": {}})
            assert response.get_json()["error"]["code"] == -32601

    # And nothing advertises a credential requirement: this surface needs none.
    assert not card.get("securitySchemes"), (
        "the card advertises a security scheme for an endpoint that needs no "
        "credential")
    assert not card.get("security"), "the card requires a credential we do not ask for"


# ── 4. message/send really answers ─────────────────────────────────────────
def test_a_request_for_a_product_completes_with_a_sample_and_the_terms(client):
    response = _send(client, "I need whale flow data for Base", req_id=1)
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("jsonrpc") == "2.0"
    assert "error" not in body, body.get("error")

    task = body["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "completed", (
        "a request we can answer must not be left in a non-terminal state")
    parts = task["artifacts"][0]["parts"]
    data = next(p["data"] for p in parts if p.get("kind") == "data")
    assert data["matched"] == "whale-flow", data.get("matched")
    assert data["free_sample"], "the answer carries no free sample"
    assert data["how_to_pay"]["protocol"] == "x402"
    assert data["product"]["price_usdc"] > 0


def test_the_answer_states_the_amount_is_atomic(client):
    """The units trap, told to the agent BEFORE it pays.

    `accepts[0].amount` is atomic USDC. An agent that reads 3000 as dollars
    overpays by a factor of a million and the excess is not refunded, so the
    one place this must be spelled out is the answer that tells it how to pay.
    """
    body = _send(client, "terms for sales history", req_id=2).get_json()
    data = next(p["data"] for p in body["result"]["artifacts"][0]["parts"]
                if p.get("kind") == "data")
    flow = " ".join(data["how_to_pay"]["flow"])
    assert "ATOMIC" in flow.upper()
    assert "3000" in flow and "0.003" in flow, (
        "the atomic warning names no example, so it cannot be acted on")


def test_the_answer_never_returns_the_live_payload(client):
    """The paywall is the product. This surface must not give it away.

    It answers with the FREE SAMPLE — the same static example the /sample route
    serves — and the terms. If it ever returns the live body, the thing we sell
    is free.
    """
    body = _send(client, "give me the live trading signals right now",
                 req_id=3).get_json()
    data = next(p["data"] for p in body["result"]["artifacts"][0]["parts"]
                if p.get("kind") == "data")
    assert data["free_sample"] is not None
    assert "output_example" in data["free_sample"], (
        "the answer is not the documented static sample")
    text = " ".join(p.get("text", "") for p in
                    body["result"]["artifacts"][0]["parts"])
    assert "does NOT return the live payload" in text, (
        "the answer does not say that it is withholding, so a caller could "
        "read the sample as the product")


def test_an_unclear_request_gets_the_catalogue_and_not_a_guess(client):
    body = _send(client, "qqqq zzzz", req_id=4).get_json()
    data = next(p["data"] for p in body["result"]["artifacts"][0]["parts"]
                if p.get("kind") == "data")
    assert data["matched"] is None, (
        "an unclear request was answered with a product, which is a guess "
        "presented as a match")
    assert len(data["catalogue"]) >= 1


# ── 5. tasks/get round-trips, and a missing task is not invented ───────────
def test_a_task_we_created_can_be_fetched_back(client):
    task = _send(client, "market stats", req_id=5).get_json()["result"]
    got = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": 6, "method": "tasks/get",
        "params": {"id": task["id"]}}).get_json()
    assert "error" not in got, got.get("error")
    assert got["result"]["id"] == task["id"]
    assert got["result"]["status"]["state"] == "completed"


def test_an_unknown_task_is_an_error_not_an_empty_task(client):
    """Inventing a task for an id we never issued would be a fabricated answer."""
    got = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": 7, "method": "tasks/get",
        "params": {"id": "task-does-not-exist"}}).get_json()
    assert got["error"]["code"] == -32001, got
    assert "result" not in got


def test_the_internal_bookkeeping_key_never_leaks(client):
    task = _send(client, "arbitrage", req_id=8).get_json()["result"]
    assert not any(k.startswith("_") for k in task), task.keys()


# ── 6. protocol hygiene ────────────────────────────────────────────────────
def test_an_unsupported_method_is_refused_with_the_supported_list(client):
    got = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": 11, "method": "tasks/cancel",
        "params": {}}).get_json()
    assert got["error"]["code"] == -32601
    assert "message/send" in got["error"]["data"]["supported"]


def test_bad_requests_are_json_rpc_errors_not_tracebacks(client):
    for payload in ({"method": "message/send"},          # no jsonrpc / no id
                    {"jsonrpc": "2.0", "id": 1},          # no method
                    {"jsonrpc": "2.0", "id": 1, "method": "message/send",
                     "params": {}},                       # no message
                    {"jsonrpc": "2.0", "id": 1, "method": "tasks/get",
                     "params": {"id": ""}}):              # empty id
        response = client.post("/a2a", json=payload)
        assert response.status_code == 200, (
            "a JSON-RPC protocol error must travel as a 200 with an error "
            "object, not as a transport failure")
        body = response.get_json()
        assert body.get("jsonrpc") == "2.0"
        assert isinstance(body.get("error", {}).get("code"), int), body


def test_a_non_object_body_is_a_parse_error(client):
    response = client.post("/a2a", data="not json at all",
                           content_type="application/json")
    assert response.status_code == 200
    assert response.get_json()["error"]["code"] == -32700


def test_get_a2a_describes_itself_instead_of_405(client):
    """A directory checking the card's url sends GET. A 405 would read as dead."""
    response = client.get("/a2a")
    assert response.status_code == 200
    body = response.get_json()
    assert body["protocolVersion"] == "0.3.0"
    assert "message/send" in body["methods"]
    assert body["card"].endswith("/.well-known/agent-card.json")


# ── 7. discovery must stay free, or nobody can find us ─────────────────────
def test_the_a2a_surface_is_free_and_not_paywalled(client):
    """A 402 on discovery is a discovery surface nobody can discover."""
    from main import X402_FREE_ENDPOINTS

    assert "/.well-known/agent-card.json" in X402_FREE_ENDPOINTS
    assert "/a2a" in X402_FREE_ENDPOINTS

    for path in ("/.well-known/agent-card.json", "/a2a"):
        response = client.get(path)
        assert response.status_code != 402, (
            "%s is behind the paywall, so an agent must pay to learn that it "
            "must pay" % path)


def test_the_card_is_reachable_without_a_trailing_extension_guess(client):
    """The path is agent-card.json, with the hyphen, exactly as the spec has it.

    A near-miss path is the most common way a card is published and never
    found, so the wrong spellings must be the ones that 404.
    """
    assert client.get("/.well-known/agent-card.json").status_code == 200
    for wrong in ("/.well-known/agentcard.json", "/.well-known/agent.json",
                  "/.well-known/agent_card.json"):
        assert client.get(wrong).status_code == 404, (
            "%s answered; an agent fetching the wrong path must not be handed "
            "something that looks right" % wrong)


# ── 8. published where agents read, not only at its conventional path ──────
def test_the_card_is_published_in_the_two_surfaces_agents_actually_read(client):
    """A card at its conventional path is correct and easy to miss.

    `/agents.json` and `/llms.txt` are the manifests an agent reads to learn what
    a service sells. Both listed our six HTTP routes and said nothing about A2A,
    so an agent could read either one in full and still not know we speak it.
    This checks the pointer is in both AND that what it names answers — a
    manifest advertising a dead URL is worse than a silent one.
    """
    agents = client.get("/agents.json").get_json()
    docs = agents["docs"]
    assert docs["a2a_agent_card"].endswith("/.well-known/agent-card.json")
    assert docs["a2a_endpoint"].endswith("/a2a")

    llms = client.get("/llms.txt").get_data(as_text=True)
    assert "/.well-known/agent-card.json" in llms
    assert "/a2a" in llms

    # The honesty claim is part of the publication, not decoration: without it
    # an agent asks the A2A surface for the paid payload, is correctly refused,
    # and reads that refusal as a broken agent rather than a boundary.
    assert "does not return the live payload" in llms

    # Not taken on faith — fetch what the manifest names.
    for url in (docs["a2a_agent_card"], docs["a2a_endpoint"]):
        path = _path_of(url)
        assert path in ("/.well-known/agent-card.json", "/a2a"), path
        assert client.get(path).status_code == 200
