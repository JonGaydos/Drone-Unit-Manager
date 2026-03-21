from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_flights: int = 0
    total_flight_hours: float = 0.0
    active_pilots: int = 0
    fleet_size: int = 0
    flights_needing_review: int = 0
    upcoming_cert_expirations: int = 0


class FlightsByPurpose(BaseModel):
    purpose: str
    count: int


class FlightsByYear(BaseModel):
    year: int
    count: int


class FlightsByYearPurpose(BaseModel):
    year: int
    purpose: str
    count: int


class FlightsByPilot(BaseModel):
    pilot_name: str
    count: int
    percentage: float


class AvgDurationByYear(BaseModel):
    year: int
    avg_seconds: float


class MonthlyFlights(BaseModel):
    year: int
    month: int
    count: int


class VehicleHours(BaseModel):
    vehicle_name: str
    hours: float


class PilotHours(BaseModel):
    pilot_name: str
    hours: float
    flight_count: int
