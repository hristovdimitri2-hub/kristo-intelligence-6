from pathlib import Path

from integrations.crm_store import CRMStore, LeadRecord


def test_sqlite_crm_backend_tracks_paid_pipeline(tmp_path):
    db_path = tmp_path / "sales.db"
    store = CRMStore(db_path)

    lead = LeadRecord(email="buyer@example.com", source="meta_ads", campaign="launch", plan="Pro")
    store.add_lead(lead)
    updated = store.mark_paid("buyer@example.com", 79.0, "Pro")

    assert updated is not None
    assert updated["payment_status"] == "paid"
    assert updated["status"] == "qualified"
    assert store.get_sales_pipeline()["paid"] >= 1
