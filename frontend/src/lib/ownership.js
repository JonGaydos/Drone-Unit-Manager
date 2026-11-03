/**
 * Whether the signed-in user owns a record, for canRecord(key, owned). These
 * mirror the backend's rules, which decide; see "Meaning of Own" in the design.
 */

/** True when the record's owner field names this user. A record with no
 *  recorded owner belongs to nobody. */
export function ownsRecord(user, ownerId) {
  return ownerId != null && ownerId === user?.id
}

/** True when the pilot is the user's linked pilot. */
export function ownsPilot(user, pilotId) {
  return pilotId != null && pilotId === user?.pilot_id
}

/** A flight is the user's when it is their linked pilot's or they logged it. */
export function ownsFlight(user, flight) {
  return ownsPilot(user, flight.pilot_id) || ownsRecord(user, flight.created_by_id)
}

/** A mission or training log is the user's when they created it or their linked
 *  pilot is on its roster. */
export function ownsLog(user, log) {
  return ownsRecord(user, log.created_by_id) || (log.pilots || []).some(p => ownsPilot(user, p.pilot_id))
}

/** A document is the user's when they uploaded it or it is attached to their
 *  pilot record or certification. */
export function ownsDocument(user, doc) {
  return ownsRecord(user, doc.uploaded_by_id)
    || ownsPilot(user, doc.pilot_id)
    || ownsPilot(user, doc.certification_pilot_id)
}
