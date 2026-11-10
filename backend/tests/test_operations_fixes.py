"""Regression tests for the operations fixes: incidents, alerts, geofence
removal, weather and search (staging test 2026-11-08, Area 6)."""

import httpx

BRIEFING_URL = "/api/weather/briefing"

# A public airport near the test point; the second entry is a non-METAR site.
STATION_KPNS = {"icaoId": "KPNS", "site": "Pensacola Intl", "lat": 30.4734, "lon": -87.1866,
                "siteType": ["METAR", "TAF"]}

CALM_LOCAL = {
    "current": {"temperature_2m": 60, "relative_humidity_2m": 50, "wind_speed_10m": 3,
                "wind_direction_10m": 180, "wind_gusts_10m": 5, "precipitation": 0,
                "cloud_cover": 10, "visibility": 20000, "weather_code": 0},
    "hourly": {"time": ["2026-11-08T22:00"], "temperature_2m": [58],
               "precipitation_probability": [0], "wind_speed_10m": [3],
               "wind_gusts_10m": [5], "visibility": [20000], "cloud_cover": [10]},
}


def _metar(**overrides):
    m = {"rawOb": "KPNS 090353Z 00000KT 10SM CLR 16/10 A3012", "temp": 16, "dewp": 10,
         "wdir": 0, "wspd": 0, "wgst": None, "visib": "10+", "fltCat": "VFR",
         "altim": 1020, "reportTime": "2026-11-09T04:00:00Z", "clouds": []}
    m.update(overrides)
    return m


def _weather_handler(stations=None, metar=None, local=None, seen=None):
    """Route the four upstream weather calls to canned responses.

    A None value for a source makes that upstream answer 500."""
    def handler(request):
        url = str(request.url)
        if seen is not None:
            seen.append(request)
        if "stationinfo" in url:
            return httpx.Response(200, json=stations) if stations is not None else httpx.Response(500)
        if "/metar" in url:
            return httpx.Response(200, json=[metar]) if metar is not None else httpx.Response(500)
        if "/taf" in url:
            return httpx.Response(200, json=[])
        if "open-meteo" in url:
            return httpx.Response(200, json=local) if local is not None else httpx.Response(500)
        raise AssertionError(f"unexpected request {url}")
    return handler


def _briefing(client, headers, lat=30.44, lon=-87.23):
    r = client.get(BRIEFING_URL, headers=headers, params={"lat": lat, "lon": lon})
    assert r.status_code == 200, r.text
    return r.json()


# --- D-12: flight category, ceiling and the no-data advisory ---


def test_briefing_reads_flight_category_and_ceiling(client, admin_headers, mock_httpx):
    clouds = [{"cover": "FEW", "base": 300}, {"cover": "BKN", "base": 1200},
              {"cover": "OVC", "base": 800}]
    mock_httpx(_weather_handler([STATION_KPNS], _metar(fltCat="MVFR", clouds=clouds), CALM_LOCAL))
    body = _briefing(client, admin_headers)
    assert body["metar"]["flight_category"] == "MVFR"
    assert body["metar"]["ceiling_ft"] == 800
    assert body["advisory"]["status"] == "caution"
    assert "Flight category: MVFR" in body["advisory"]["reasons"]


def test_briefing_ceiling_ignores_few_and_scattered_layers(client, admin_headers, mock_httpx):
    clouds = [{"cover": "FEW", "base": 200}, {"cover": "SCT", "base": 300}]
    mock_httpx(_weather_handler([STATION_KPNS], _metar(clouds=clouds), CALM_LOCAL))
    body = _briefing(client, admin_headers)
    assert body["metar"]["ceiling_ft"] is None
    assert body["advisory"]["status"] == "go"


def test_briefing_vertical_visibility_counts_as_ceiling(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler([STATION_KPNS], _metar(clouds=[{"cover": "OVX", "base": None}], vertVis=100),
                                CALM_LOCAL))
    body = _briefing(client, admin_headers)
    assert body["metar"]["ceiling_ft"] == 100


def test_ifr_gives_no_go(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler([STATION_KPNS],
                                _metar(fltCat="IFR", clouds=[{"cover": "OVC", "base": 700}]), CALM_LOCAL))
    advisory = _briefing(client, admin_headers)["advisory"]
    assert advisory["status"] == "no_go"
    assert "Flight category: IFR" in advisory["reasons"]


def test_low_ceiling_gives_caution(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler([STATION_KPNS], _metar(clouds=[{"cover": "BKN", "base": 400}]), CALM_LOCAL))
    advisory = _briefing(client, admin_headers)["advisory"]
    assert advisory["status"] == "caution"
    assert any("Ceiling 400 ft" in r for r in advisory["reasons"])


def test_no_weather_data_gives_unknown(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler())
    advisory = _briefing(client, admin_headers, lat=999, lon=999)["advisory"]
    assert advisory["status"] == "unknown"
    assert "All conditions within safe operating limits" not in advisory["reasons"]


def test_missing_metar_gives_caution_not_go(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler(stations=[], local=CALM_LOCAL))
    advisory = _briefing(client, admin_headers)["advisory"]
    assert advisory["status"] == "caution"
    assert "All conditions within safe operating limits" not in advisory["reasons"]


def test_full_data_within_limits_gives_go(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler([STATION_KPNS], _metar(), CALM_LOCAL))
    advisory = _briefing(client, admin_headers)["advisory"]
    assert advisory["status"] == "go"
    assert advisory["reasons"] == ["All conditions within safe operating limits"]


# --- D-10: the geofence feature is removed ---


def test_geofence_api_is_gone(client, admin_headers):
    assert client.get("/api/geofences", headers=admin_headers).status_code == 404
    assert client.get("/api/geofences/check", headers=admin_headers,
                      params={"lat": 30.44, "lon": -87.23}).status_code == 404


def test_geofence_table_is_not_in_the_schema():
    from app.database import Base
    import app.models  # noqa: F401
    from app.routers.backup import EXPORT_ORDER
    assert "geofences" not in Base.metadata.tables
    assert "geofences" not in [name for name, _ in EXPORT_ORDER]


def test_operations_token_scope_and_permissions_drop_geofences():
    from app.services.api_tokens import SCOPE_PREFIXES
    from app.services.permissions import _DEFAULT_GRID
    assert "/api/geofences" not in SCOPE_PREFIXES["operations"]
    assert not any("geofence" in title.lower() for title, _ in _DEFAULT_GRID)


def test_migration_drops_geofences_and_downgrade_restores_it(tmp_path, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    import app.config

    url = f"sqlite:///{tmp_path / 'existing.db'}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0014_autoincrement_ids")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        assert "geofences" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
    command.downgrade(cfg, "0014_autoincrement_ids")
    engine = create_engine(url)
    try:
        assert "geofences" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_restore_of_an_old_backup_with_geofences_succeeds(client, db, telemetry_db, tmp_path, monkeypatch):
    import io
    import json
    import zipfile
    from sqlalchemy import text
    from app.config import settings as app_settings
    from app.models.pilot import Pilot
    from app.routers.backup import DATABASE_FILE, EXPORT_ORDER, _install_token_path, build_backup_archive

    monkeypatch.setattr(app_settings, "UPLOAD_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    db.add(Pilot(first_name="Test", last_name="Restore", status="active"))
    db.commit()
    spooled, _ = build_backup_archive(db, include_telemetry=False)

    # Re-pack the archive with the geofences table an older version exported.
    src = zipfile.ZipFile(io.BytesIO(spooled.read()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == DATABASE_FILE:
                tables = json.loads(data)
                tables["geofences"] = [{"id": 1, "name": "Old zone", "zone_type": "caution",
                                        "geometry_type": "circle", "center_lat": 30.0,
                                        "center_lon": -87.0, "radius_m": 100.0, "is_active": True,
                                        "created_at": "2026-01-01T00:00:00"}]
                data = json.dumps(tables)
            dst.writestr(name, data)

    db.execute(text("PRAGMA foreign_keys=OFF"))
    for _name, model in EXPORT_ORDER:
        db.execute(model.__table__.delete())
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))
    token = "geofence-restore-token"
    with open(_install_token_path(), "w") as f:
        f.write(token)

    r = client.post("/api/backup/import", headers={"X-Install-Token": token},
                    files={"file": ("backup.zip", out.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Pilot).filter_by(last_name="Restore").count() == 1


# --- Incidents ---

INCIDENTS_URL = "/api/incidents"


def _incident_body(**overrides):
    body = {"date": "2026-11-07", "title": "Hard landing", "severity": "minor",
            "category": "other", "description": "Landed hard on the pad"}
    body.update(overrides)
    return body


def _make_incident(db, **kwargs):
    from datetime import date
    from app.models.incident import Incident
    values = {"date": date(2026, 11, 1), "title": "Old", "severity": "minor",
              "category": "other", "description": "d"}
    values.update(kwargs)
    inc = Incident(**values)
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


# D-1: category must be one of the page's lists


def test_create_refuses_unknown_category(client, admin_headers):
    r = client.post(INCIDENTS_URL, headers=admin_headers, json=_incident_body(category="banana"))
    assert r.status_code == 422
    assert "category must be one of" in r.text


def test_create_accepts_incident_and_success_categories(client, admin_headers):
    assert client.post(INCIDENTS_URL, headers=admin_headers,
                       json=_incident_body(category="near_miss")).status_code == 200
    assert client.post(INCIDENTS_URL, headers=admin_headers,
                       json=_incident_body(category="suspect_located", report_type="success")).status_code == 200


def test_patch_refuses_unknown_category_but_keeps_a_stored_one(client, db, admin_headers):
    inc = _make_incident(db, category="legacy_value")
    r = client.patch(f"{INCIDENTS_URL}/{inc.id}", headers=admin_headers, json={"category": "zzz"})
    assert r.status_code == 422
    r = client.patch(f"{INCIDENTS_URL}/{inc.id}", headers=admin_headers,
                     json={"category": "legacy_value", "title": "Renamed"})
    assert r.status_code == 200, r.text


# D-2: title and description are required, after trimming


def test_create_refuses_blank_title_and_description(client, admin_headers):
    for field in ("title", "description"):
        for blank in ("", "   "):
            r = client.post(INCIDENTS_URL, headers=admin_headers, json=_incident_body(**{field: blank}))
            assert r.status_code == 422, (field, blank, r.text)
            assert field in r.text


def test_create_trims_title(client, admin_headers):
    r = client.post(INCIDENTS_URL, headers=admin_headers, json=_incident_body(title="  Prop strike  "))
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Prop strike"


def test_patch_refuses_blank_or_null_title_and_description(client, db, admin_headers):
    inc = _make_incident(db)
    for body in ({"title": "  "}, {"description": ""}, {"title": None}, {"description": None}):
        r = client.patch(f"{INCIDENTS_URL}/{inc.id}", headers=admin_headers, json=body)
        assert r.status_code == 422, (body, r.text)


# --- D-13: the nearest station that reports METAR ---


def test_briefing_skips_stations_without_an_icao_id_or_metar(client, admin_headers, mock_httpx):
    seen = []
    no_icao = {"icaoId": None, "id": "PCLF1", "site": "Buoy", "lat": 30.44, "lon": -87.23,
               "siteType": []}
    taf_only = {"icaoId": "KXXA", "site": "No obs", "lat": 30.441, "lon": -87.231, "siteType": ["TAF"]}
    mock_httpx(_weather_handler([no_icao, taf_only, STATION_KPNS], _metar(), CALM_LOCAL, seen))
    body = _briefing(client, admin_headers)
    assert body["station"]["id"] == "KPNS"
    metar_requests = [r for r in seen if "/metar" in str(r.url)]
    assert metar_requests[0].url.params["ids"] == "KPNS"
    assert body["metar"]["station"] == "KPNS"


# --- D-14: station name from the upstream "site" key ---


def test_briefing_station_name_comes_from_site(client, admin_headers, mock_httpx):
    mock_httpx(_weather_handler([STATION_KPNS], _metar(), CALM_LOCAL))
    assert _briefing(client, admin_headers)["station"]["name"] == "Pensacola Intl"


# --- D-15: forecast hours in the location's own time zone ---


def test_open_meteo_is_asked_for_local_time(client, admin_headers, mock_httpx):
    seen = []
    mock_httpx(_weather_handler([STATION_KPNS], _metar(), CALM_LOCAL, seen))
    body = _briefing(client, admin_headers)
    meteo = next(r for r in seen if "open-meteo" in str(r.url))
    assert meteo.url.params["timezone"] == "auto"
    assert body["forecast"][0]["time"] == "2026-11-08T22:00"
