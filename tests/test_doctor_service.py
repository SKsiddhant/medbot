from services.doctor_service import DoctorService


def test_find_nearby_does_not_mutate_shared_directory():
    svc = DoctorService()
    near = svc.find_nearby("Cardiology", user_lat=23.25, user_lng=77.43)
    assert near and "distance_km" in near[0]
    # A later call without coordinates must not see a stale distance from the first call.
    later = svc.find_nearby("Cardiology")
    assert all("distance_km" not in d for d in later)
    assert all("distance_km" not in d for d in svc._doctors)
