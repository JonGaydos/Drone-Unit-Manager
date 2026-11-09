"""PATCH /api/photos/{id}: an empty form value clears the field.

The edit form is multipart. FastAPI reads an empty form value as missing, so
"" used to mean "keep" and nothing could be cleared. A field left out of the
form is still kept; a field sent empty is cleared (pilot_ids "" untags all).
"""

from datetime import datetime

from app.models.photo import Photo, PhotoPilot
from app.models.pilot import Pilot


def _seed(db):
    pilots = [Pilot(first_name="Alpha", last_name="One"), Pilot(first_name="Bravo", last_name="Two")]
    db.add_all(pilots)
    photo = Photo(filename="p.png", original_filename="p.png", mime_type="image/png",
                  title="Scene", description="Night shot", date_taken=datetime(2026, 5, 1))
    db.add(photo)
    db.commit()
    db.add_all([PhotoPilot(photo_id=photo.id, pilot_id=p.id) for p in pilots])
    db.commit()
    return photo.id, [p.id for p in pilots]


def _patch(client, headers, photo_id, data):
    return client.patch(f"/api/photos/{photo_id}", headers=headers, files={k: (None, v) for k, v in data.items()})


def _pilot_ids(db, photo_id):
    return sorted(link.pilot_id for link in db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id))


def test_empty_values_clear_title_description_date_and_pilots(client, db, admin_headers):
    photo_id, _ = _seed(db)

    resp = _patch(client, admin_headers, photo_id,
                  {"title": "", "description": "", "date_taken": "", "pilot_ids": ""})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    photo = db.get(Photo, photo_id)
    assert photo.title is None
    assert photo.description is None
    assert photo.date_taken is None
    assert _pilot_ids(db, photo_id) == []


def test_fields_left_out_are_kept(client, db, admin_headers):
    photo_id, pilot_ids = _seed(db)

    resp = _patch(client, admin_headers, photo_id, {"title": "Renamed"})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    photo = db.get(Photo, photo_id)
    assert photo.title == "Renamed"
    assert photo.description == "Night shot"
    assert photo.date_taken == datetime(2026, 5, 1)
    assert _pilot_ids(db, photo_id) == sorted(pilot_ids)


def test_removing_one_of_two_pilots(client, db, admin_headers):
    photo_id, pilot_ids = _seed(db)

    resp = _patch(client, admin_headers, photo_id, {"pilot_ids": str(pilot_ids[0])})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert _pilot_ids(db, photo_id) == [pilot_ids[0]]
