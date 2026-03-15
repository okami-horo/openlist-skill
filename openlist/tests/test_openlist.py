import tempfile
import unittest
from pathlib import Path

from skills.openlist.scripts import openlist


class FakeClient(object):
    def __init__(self, responses):
        self.responses = {}
        for key, value in responses.items():
            if isinstance(value, list):
                self.responses[key] = list(value)
            else:
                self.responses[key] = [value]
        self.calls = []

    def request(self, method, endpoint, *, body=None, params=None):
        key = (method.upper(), endpoint)
        self.calls.append({"method": method.upper(), "endpoint": endpoint, "body": body, "params": params})
        queue = self.responses.get(key, [])
        if not queue:
            raise AssertionError("No fake response prepared for %s %s" % key)
        response = queue.pop(0)
        if callable(response):
            response = response(method=method.upper(), endpoint=endpoint, body=body, params=params)
        return dict(response)


def make_remove_plan(path="/docs/report.txt", entry_type="file", *, endpoint="/api/fs/remove", risk_level="high"):
    parent_dir, entry_name = openlist.split_dir_and_name(path)
    return {
        "plan_id": "p-remove",
        "request_id": "r-remove",
        "created_at": "2026-03-14T00:00:00+08:00",
        "type": "fs_remove",
        "api": {"base_url": "https://example.com/openlist"},
        "request": {"request_id": "r-remove", "type": "fs_remove", "path": path},
        "prechecks": [{"name": "source_exists", "ok": True, "detail": "success"}],
        "conflicts": [],
        "risk": {"level": risk_level, "notes": ["Delete is irreversible."]},
        "resolved": {
            "endpoint": endpoint,
            "body": {"dir": parent_dir, "names": [entry_name]},
            "source_path": path,
            "final_path": path,
            "entry_type": entry_type,
            "noop": False,
        },
    }


class OpenListHelpersTest(unittest.TestCase):
    def test_parse_env_text(self):
        content = """
        # comment
        OPENLIST_BASE_URL=http://localhost:5244
        OPENLIST_TOKEN="abc123"
        INVALID
        """
        parsed = openlist.parse_env_text(content)
        self.assertEqual(parsed["OPENLIST_BASE_URL"], "http://localhost:5244")
        self.assertEqual(parsed["OPENLIST_TOKEN"], "abc123")
        self.assertNotIn("INVALID", parsed)

    def test_normalize_path(self):
        self.assertEqual(openlist.normalize_openlist_path("/dir/file.txt/"), "/dir/file.txt")
        self.assertEqual(openlist.normalize_openlist_path("/"), "/")
        with self.assertRaises(openlist.UserFacingError):
            openlist.normalize_openlist_path("dir/file.txt")
        with self.assertRaises(openlist.UserFacingError):
            openlist.normalize_openlist_path("/dir/../file.txt")

    def test_join_base_url(self):
        url = openlist.join_base_url("https://example.com/openlist", "/api/me")
        self.assertEqual(url, "https://example.com/openlist/api/me")

    def test_generate_auto_name_is_stable(self):
        existing = {"report.pdf", "report (1).pdf"}
        self.assertEqual(openlist.generate_auto_name(existing, "report.pdf"), "report (2).pdf")

    def test_validate_new_name(self):
        self.assertEqual(openlist.validate_new_name("ok.txt"), "ok.txt")
        for invalid in ("", ".", "..", "a/b", "a\\b"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(openlist.UserFacingError):
                    openlist.validate_new_name(invalid)

    def test_split_dir_and_name(self):
        parent, name = openlist.split_dir_and_name("/dir/name.txt")
        self.assertEqual(parent, "/dir")
        self.assertEqual(name, "name.txt")

    def test_choose_offline_tool(self):
        self.assertEqual(openlist.choose_offline_tool(["aria2", "SimpleHttp"]), "SimpleHttp")
        self.assertEqual(openlist.choose_offline_tool(["aria2"]), "aria2")
        self.assertIsNone(openlist.choose_offline_tool([]))

    def test_filter_urls(self):
        urls = openlist.filter_urls(["  ", "https://a", "", " https://b "])
        self.assertEqual(urls, ["https://a", "https://b"])

    def test_task_type_mapping(self):
        self.assertEqual(openlist.TASK_TYPES["move"], "/api/task/move")
        self.assertEqual(openlist.TASK_TYPES["offline_download"], "/api/task/offline_download")

    def test_delete_plan_type_and_endpoint_allowlist(self):
        self.assertIn("fs_remove", openlist.ALLOWED_PLAN_TYPES)
        self.assertIn("/api/fs/remove", openlist.ALLOWED_ENDPOINTS)
        self.assertEqual(openlist.PLAN_ENDPOINTS["fs_remove"], "/api/fs/remove")

    def test_make_result_success(self):
        result = openlist.make_result(True, "success", openlist_code=200, data={"name": "file.txt"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["openlist_code"], 200)

    def test_sanitize_for_audit(self):
        sanitized = openlist.sanitize_for_audit(
            {
                "Authorization": "token",
                "nested": {"token_value": "abc", "path": "/demo"},
            }
        )
        self.assertEqual(sanitized["Authorization"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["token_value"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["path"], "/demo")

    def test_validate_plan_schema_blocks_overwrite(self):
        config = {"base_url": "https://example.com/openlist"}
        plan = {
            "plan_id": "p1",
            "request_id": "r1",
            "created_at": "2026-03-14T00:00:00+08:00",
            "type": "fs_rename",
            "api": {"base_url": "https://example.com/openlist"},
            "prechecks": [{"name": "ok", "ok": True, "detail": ""}],
            "conflicts": [],
            "risk": {"level": "low", "notes": []},
            "resolved": {
                "endpoint": "/api/fs/rename",
                "body": {"path": "/a", "name": "b", "overwrite": True},
            },
        }
        with self.assertRaises(openlist.UserFacingError):
            openlist.validate_plan_schema(plan, config)

    def test_validate_plan_schema_blocks_conflicts(self):
        config = {"base_url": "https://example.com/openlist"}
        plan = {
            "plan_id": "p1",
            "request_id": "r1",
            "created_at": "2026-03-14T00:00:00+08:00",
            "type": "fs_move",
            "api": {"base_url": "https://example.com/openlist"},
            "prechecks": [{"name": "ok", "ok": True, "detail": ""}],
            "conflicts": [{"kind": "name_conflict"}],
            "risk": {"level": "medium", "notes": []},
            "resolved": {
                "endpoint": "/api/fs/move",
                "body": {"src_dir": "/a", "dst_dir": "/b", "names": ["c"], "overwrite": False},
            },
        }
        with self.assertRaises(openlist.UserFacingError):
            openlist.validate_plan_schema(plan, config)

    def test_validate_plan_schema_blocks_tampered_delete_plan(self):
        config = {"base_url": "https://example.com/openlist"}
        plan = make_remove_plan()
        plan["resolved"]["body"]["names"] = ["report.txt", "other.txt"]
        with self.assertRaises(openlist.UserFacingError):
            openlist.validate_plan_schema(plan, config)

    def test_validate_plan_schema_blocks_delete_endpoint_mismatch(self):
        config = {"base_url": "https://example.com/openlist"}
        plan = make_remove_plan(endpoint="/api/fs/rename")
        with self.assertRaises(openlist.UserFacingError):
            openlist.validate_plan_schema(plan, config)

    def test_noop_apply_writes_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "base_url": "https://example.com/openlist",
                "audit_path": Path(tmp) / "audit.jsonl",
            }
            plan = {
                "plan_id": "p1",
                "request_id": "r1",
                "created_at": "2026-03-14T00:00:00+08:00",
                "type": "fs_rename",
                "api": {"base_url": "https://example.com/openlist"},
                "request": {"request_id": "r1", "type": "fs_rename", "path": "/a", "new_name": "a"},
                "prechecks": [{"name": "ok", "ok": True, "detail": ""}],
                "conflicts": [],
                "risk": {"level": "low", "notes": []},
                "resolved": {
                    "endpoint": "/api/fs/rename",
                    "body": {"path": "/a", "name": "a", "overwrite": False},
                    "noop": True,
                },
            }
            result = openlist.execute_plan(client=None, config=config, plan=plan)  # type: ignore[arg-type]
            self.assertTrue(result["ok"])
            records = openlist.load_audit_records(config)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["phase"], "apply")

    def test_build_delete_preview_for_file(self):
        client = FakeClient(
            {
                ("POST", "/api/fs/get"): [
                    {"ok": True, "message": "success", "data": {"is_dir": False}},
                ]
            }
        )
        plan = openlist.build_delete_preview(client, {"base_url": "https://example.com/openlist"}, "/docs/report.txt")
        self.assertEqual(plan["type"], "fs_remove")
        self.assertEqual(plan["risk"]["level"], "high")
        self.assertEqual(plan["resolved"]["body"], {"dir": "/docs", "names": ["report.txt"]})
        self.assertEqual(plan["resolved"]["entry_type"], "file")
        self.assertEqual(plan["resolved"]["final_path"], "/docs/report.txt")

    def test_build_delete_preview_for_directory(self):
        client = FakeClient(
            {
                ("POST", "/api/fs/get"): [
                    {"ok": True, "message": "success", "data": {"is_dir": True}},
                ]
            }
        )
        plan = openlist.build_delete_preview(client, {"base_url": "https://example.com/openlist"}, "/docs/archive")
        self.assertEqual(plan["resolved"]["body"], {"dir": "/docs", "names": ["archive"]})
        self.assertEqual(plan["resolved"]["entry_type"], "dir")

    def test_build_delete_preview_rejects_invalid_paths(self):
        client = FakeClient({})
        for invalid in ("/", "", "docs/report.txt", "/docs/../report.txt"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(openlist.UserFacingError):
                    openlist.build_delete_preview(client, {"base_url": "https://example.com/openlist"}, invalid)

    def test_execute_plan_delete_success_writes_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "base_url": "https://example.com/openlist",
                "audit_path": Path(tmp) / "audit.jsonl",
            }
            client = FakeClient(
                {
                    ("POST", "/api/fs/get"): [
                        {"ok": True, "message": "success", "data": {"is_dir": False}},
                    ],
                    ("POST", "/api/fs/remove"): [
                        {"ok": True, "message": "Removed", "openlist_code": 200, "data": {}},
                    ],
                }
            )
            result = openlist.execute_plan(client=client, config=config, plan=make_remove_plan())
            self.assertTrue(result["ok"])
            self.assertEqual(client.calls[1]["endpoint"], "/api/fs/remove")
            records = openlist.load_audit_records(config)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["phase"], "apply")

    def test_execute_plan_delete_denies_when_target_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "base_url": "https://example.com/openlist",
                "audit_path": Path(tmp) / "audit.jsonl",
            }
            client = FakeClient(
                {
                    ("POST", "/api/fs/get"): [
                        {"ok": True, "message": "success", "data": {"is_dir": True}},
                    ]
                }
            )
            result = openlist.execute_plan(client=client, config=config, plan=make_remove_plan(entry_type="file"))
            self.assertFalse(result["ok"])
            self.assertEqual(result["data"]["actual_entry_type"], "dir")
            records = openlist.load_audit_records(config)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["phase"], "apply")

    def test_execute_plan_delete_surfaces_openlist_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "base_url": "https://example.com/openlist",
                "audit_path": Path(tmp) / "audit.jsonl",
            }
            client = FakeClient(
                {
                    ("POST", "/api/fs/get"): [
                        {"ok": True, "message": "success", "data": {"is_dir": False}},
                    ],
                    ("POST", "/api/fs/remove"): [
                        {"ok": False, "message": "Permission denied", "openlist_code": 403, "data": {}},
                    ],
                }
            )
            result = openlist.execute_plan(client=client, config=config, plan=make_remove_plan())
            self.assertFalse(result["ok"])
            self.assertEqual(result["openlist_code"], 403)
            records = openlist.load_audit_records(config)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["outcome"]["message"], "Permission denied")

    def test_audit_show_filter_by_tid(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"audit_path": Path(tmp) / "audit.jsonl"}
            openlist.write_audit_record(
                config,
                phase="apply",
                operation_type="offline_create",
                inputs={"path": "/downloads"},
                outcome={"tasks": [{"task_type": "offline_download", "tid": "t-1"}]},
                request_id="r1",
                plan_id="p1",
            )
            records = openlist.filter_audit_records(openlist.load_audit_records(config), tid="t-1")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["plan_id"], "p1")


if __name__ == "__main__":
    unittest.main()
