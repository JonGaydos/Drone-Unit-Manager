"""Fleet model list: normalization, merging of spellings and the route."""

from app.models.vehicle import Vehicle
from app.services.fleet_models import fleet_models, normalize_model

MODELS_URL = "/api/currency/models"


def _add(db, serial, model, status="active"):
    db.add(Vehicle(serial_number=serial, manufacturer="Acme", model=model, status=status))
    db.commit()


def test_normalize_model():
    assert normalize_model(" X10 ") == normalize_model("x10") == normalize_model("X10")
    assert normalize_model("LEMUR  2") == normalize_model("lemur 2")
    assert normalize_model(None) == ""
    assert normalize_model("  ") == ""


def test_fleet_models_merges_spellings(db):
    _add(db, "S1", "X10")
    _add(db, "S2", "x10 ")
    _add(db, "S3", "X10")
    assert fleet_models(db) == [{"name": "X10", "aircraft": 3, "retired": 0}]


def test_fleet_models_names_model_by_most_common_spelling(db):
    _add(db, "S1", "X10")
    _add(db, "S2", "x10")
    _add(db, "S3", "x10")
    assert fleet_models(db)[0]["name"] == "x10"


def test_fleet_models_breaks_spelling_tie_alphabetically(db):
    _add(db, "S1", "x2e")
    _add(db, "S2", "X2E")
    assert fleet_models(db)[0]["name"] == "X2E"


def test_fleet_models_counts_retired_apart(db):
    _add(db, "S1", "X2E")
    _add(db, "S2", "X2E", "maintenance")
    _add(db, "S3", "X2E", "retired")
    _add(db, "S4", "Old", "retired")
    assert fleet_models(db) == [
        {"name": "Old", "aircraft": 0, "retired": 1},
        {"name": "X2E", "aircraft": 2, "retired": 1},
    ]


def test_fleet_models_skips_blank_model(db):
    _add(db, "S1", "  ")
    _add(db, "S2", "X10")
    assert [m["name"] for m in fleet_models(db)] == ["X10"]


def test_models_route_permissions(client, admin_headers, supervisor_headers, pilot_headers, viewer_headers):
    assert client.get(MODELS_URL, headers=admin_headers).status_code == 200
    assert client.get(MODELS_URL, headers=supervisor_headers).status_code == 200
    assert client.get(MODELS_URL, headers=pilot_headers).status_code == 403
    assert client.get(MODELS_URL, headers=viewer_headers).status_code == 403
