"""Fleet and maintenance fixes from the 2026-11-08 staging test (Area 3)."""


# ── A-F26: component dates ──────────────────────────────────────────────────

def _component(client, headers, **extra):
    resp = client.post("/api/components", headers=headers, json={
        "name": "Motor 1", "component_type": "motor", **extra,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_component_create_rejects_invalid_dates(client, admin_headers):
    for field in ("install_date", "warranty_expiry"):
        resp = client.post("/api/components", headers=admin_headers, json={
            "name": "x", "component_type": "motor", field: "2026-13-01",
        })
        assert resp.status_code == 422, f"{field}: {resp.text}"


def test_component_patch_rejects_invalid_date(client, admin_headers):
    cid = _component(client, admin_headers)["id"]
    resp = client.patch(f"/api/components/{cid}", headers=admin_headers,
                        json={"warranty_expiry": "not-a-date"})
    assert resp.status_code == 422, resp.text


def test_component_patch_empty_date_clears_it(client, admin_headers):
    cid = _component(client, admin_headers, install_date="2026-01-05")["id"]
    resp = client.patch(f"/api/components/{cid}", headers=admin_headers,
                        json={"install_date": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["install_date"] is None


def test_component_valid_dates_round_trip(client, admin_headers):
    body = _component(client, admin_headers, install_date="2026-01-05",
                      warranty_expiry="2027-01-05")
    assert body["install_date"] == "2026-01-05"
    assert body["warranty_expiry"] == "2027-01-05"
