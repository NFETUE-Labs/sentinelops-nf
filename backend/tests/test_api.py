import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sentinelops.db")
os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-at-least-32-chars")
os.environ.setdefault("CLICKHOUSE_USER", "test")
os.environ.setdefault("CLICKHOUSE_PASSWORD", "test")

import main as backend_main
from fastapi.testclient import TestClient


class FakeClickHouseClient:
    def execute(self, query, params=None):
        if "FROM sentinelops.anomalies" in query:
            return [
                ("2026-01-01 00:00:00", "svc", "latency_spike", "GET /slow", 100.0, 250.0, "warning")
            ]
        if "FROM system.columns" in query:
            return [(1,)]
        return []


class BackendApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend_main.Base.metadata.create_all(bind=backend_main.engine)
        cls.client = TestClient(backend_main.app)

    def setUp(self):
        db = backend_main.SessionLocal()
        try:
            db.query(backend_main.User).delete()
            db.commit()
        finally:
            db.close()

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/auth/register",
            json={"email": "weak@example.com", "password": "weak"},
        )
        self.assertEqual(response.status_code, 400)

    def test_register_login_and_me(self):
        register = self.client.post(
            "/auth/register",
            json={"email": "ok@example.com", "password": "StrongPass123"},
        )
        self.assertEqual(register.status_code, 200)

        login = self.client.post(
            "/auth/login",
            data={"username": "ok@example.com", "password": "StrongPass123"},
        )
        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]

        me = self.client.get("/me", headers={"Authorization": " ".join(["Bearer", token])})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "ok@example.com")

    def test_anomalies_returns_empty_if_api_key_column_missing(self):
        self.client.post(
            "/auth/register",
            json={"email": "tenant@example.com", "password": "StrongPass123"},
        )
        login = self.client.post(
            "/auth/login",
            data={"username": "tenant@example.com", "password": "StrongPass123"},
        )
        token = login.json()["access_token"]

        original = backend_main.anomalies_has_api_key
        backend_main.anomalies_has_api_key = lambda: False
        try:
            response = self.client.get("/anomalies", headers={"Authorization": " ".join(["Bearer", token])})
        finally:
            backend_main.anomalies_has_api_key = original

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_anomalies_are_tenant_scoped_query(self):
        self.client.post(
            "/auth/register",
            json={"email": "tenant2@example.com", "password": "StrongPass123"},
        )
        login = self.client.post(
            "/auth/login",
            data={"username": "tenant2@example.com", "password": "StrongPass123"},
        )
        token = login.json()["access_token"]
        current_user = self.client.get("/me", headers={"Authorization": " ".join(["Bearer", token])}).json()

        captured = {}

        def fake_execute(query, params=None):
            captured["params"] = params
            return [
                ("2026-01-01 00:00:00", "svc", "latency_spike", "GET /slow", 100.0, 250.0, "warning")
            ]

        class CH:
            def execute(self, query, params=None):
                return fake_execute(query, params)

        original_has = backend_main.anomalies_has_api_key
        original_ch = backend_main.get_ch_client
        backend_main.anomalies_has_api_key = lambda: True
        backend_main.get_ch_client = lambda: CH()
        try:
            response = self.client.get("/anomalies", headers={"Authorization": " ".join(["Bearer", token])})
        finally:
            backend_main.anomalies_has_api_key = original_has
            backend_main.get_ch_client = original_ch

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["params"]["api_key"], current_user["api_key"])


if __name__ == "__main__":
    unittest.main()
