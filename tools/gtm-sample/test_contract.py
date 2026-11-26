"""End-to-end contract checks against a fresh loopback-only sample service."""
import json
import threading
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import fixtures as f
from server import BASE, Handler, ThreadingHTTPServer


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class GtmContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.server.static_root = None
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}{BASE}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        self.browser = build_opener(HTTPCookieProcessor(CookieJar()))
        self.project = "/projects/" + f.PROJECT

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        with self.browser.open(request, timeout=3) as res:
            return json.load(res)

    def view(self, page, **params):
        query = urlencode({"category_code": "TV", **params}, doseq=True)
        return self.call(self.project + "/views/" + page + "?" + query)

    def test_every_page_and_tab_returns_renderable_cells(self):
        self.assertEqual("sample", self.call("/context")["mode"])
        for page in f.PAGES:
            for tab in f.TABS.get(page, [""]):
                with self.subTest(page=page, tab=tab):
                    view = self.view(page, tab=tab)
                    self.assertEqual((page, tab, f.PROJECT), (view["page"], view["tab"], view["project_id"]))
                    for table in view["tables"]:
                        fields = [c["key"] for c in table["columns"]]
                        for row in table["rows"]:
                            self.assertTrue(set(fields) <= row["cells"].keys())
                            self.assertTrue(row["evidence"])

    def test_workbench_scenario_is_scoped_and_sample_only(self):
        path = "/sample-scenarios/0916"
        scenario = self.call(self.project + path)
        self.assertEqual(("0916", "sample", f.PROJECT), (scenario["version"], scenario["mode"], scenario["project_id"]))
        self.assertTrue(scenario["records"]["dailyModels"])
        self.assertTrue(scenario["records"]["premiumVocTop5Data"])
        self.assertTrue(scenario["records"]["smartReports"])
        with self.assertRaises(HTTPError) as caught:
            self.call("/projects/another-project" + path)
        self.assertEqual(404, caught.exception.code)

    def test_weekly_population_and_missing_daily_value(self):
        dates = {"period": "custom", "date_from": "2026-06-08", "date_to": "2026-06-14"}
        self.assertEqual(392, self.view("key-model", **dates)["tables"][0]["rows"][0]["cells"]["sales_volume_units"])
        self.assertEqual(110, self.view("key-model", channel="jd", **dates)["tables"][0]["rows"][0]["cells"]["sales_volume_units"])
        self.assertIsNone(self.view("key-model")["tables"][0]["rows"][0]["cells"]["sales_volume_units"])
        self.assertEqual("unavailable", self.view("daily", category_code="AC")["status"])

    def test_linked_details_match_parent_entity_scope_and_snapshot(self):
        visited = set()
        for page in ("own-monitor","rival-monitor","launch","todo-center","reports"):
            view = self.view(page)
            row = view["tables"][0]["rows"][0]
            queue = [row["drilldown"]]
            while queue:
                ref = queue.pop()
                params = {"category_code":"TV", "snapshot_id":view["snapshot_id"], "record_id":ref["record_id"]}
                path = self.project + "/details/" + ref["kind"] + "?"
                detail = self.call(path+urlencode(params))
                self.assertEqual((ref["kind"],row["id"],view["snapshot_id"]), (detail["kind"],detail["record_id"],detail["snapshot_id"]))
                self.assertEqual(row["evidence"], detail["evidence"])
                visited.add(ref["kind"])
                queue.extend(detail["links"])
                for changes,status in [({"record_id":"missing"},404),({"category_code":"AC"},404),({"snapshot_id":"old"},409)]:
                    with self.assertRaises(HTTPError) as caught:
                        self.call(path+urlencode({**params,**changes}))
                    self.assertEqual(status,caught.exception.code)
        self.assertEqual(len(visited),8)

    def test_filters_catalog_and_pagination(self):
        options = self.call(self.project + "/catalog?category_code=TV&kind=competitor&query=TCL")
        self.assertEqual(["tcl65"], [o["id"] for o in options])
        view = self.view("competitor", tab="product", competitor_ids=["tcl65"])
        self.assertEqual(2, view["tables"][0]["total"])
        view = self.view("own-monitor", channel="pdd", period="7d", severity="严重", offset=0, limit=1)
        table = view["tables"][0]
        self.assertEqual(1, len(table["rows"]))
        self.assertEqual("严重", table["rows"][0]["cells"]["severity"])
        self.assertEqual("拼多多", table["rows"][0]["cells"]["channel"])

    def test_invalid_ranges_tabs_and_project_are_errors(self):
        for page, args in [("own-monitor", {"offset": -1}), ("premium", {"tab": "bad"}),
                           ("daily", {"period": "custom", "date_from": "bad"}), ("rival-monitor", {"competitor_ids": ["missing"]})]:
            with self.assertRaises(HTTPError) as err:
                self.view(page, **args)
            self.assertEqual(422, err.exception.code)
        with self.assertRaises(HTTPError) as err:
            self.call("/projects/other/views/daily?category_code=TV")
        self.assertEqual(404, err.exception.code)

    def test_action_retry_conflict_and_browser_isolation(self):
        view = self.view("todo-center")
        task = view["tables"][0]["rows"][0]
        body = {"scope": {"project_id": f.PROJECT, "category_code": "TV", "page": "todo-center", "tab": "", "offset": 0, "limit": 20},
                "request_id": "retry1", "snapshot_id": view["snapshot_id"], "operation": "complete-task", "row_id": task["id"], "input": "", "fields": {}}
        first = self.call(self.project + "/actions", body)
        self.assertEqual(first, self.call(self.project + "/actions", body))
        self.assertEqual("已完成", self.view("todo-center")["tables"][0]["rows"][0]["cells"]["status"])
        with self.assertRaises(HTTPError) as err:
            self.call(self.project + "/actions", {**body, "input": "different"})
        self.assertEqual(409, err.exception.code)
        self.browser = build_opener(HTTPCookieProcessor(CookieJar()))
        self.assertEqual("待处理", self.view("todo-center")["tables"][0]["rows"][0]["cells"]["status"])

    def test_message_history_idempotency_and_attachment_validation(self):
        body = {"scope": {"category_code": "TV"}, "conversation_id": None, "question": "价格异常", "origin": None, "request_id": "m1"}
        chat = self.call(self.project + "/messages", body)
        self.assertEqual(chat, self.call(self.project + "/messages", body))
        self.assertEqual(chat, self.call(self.project + "/conversations/" + chat["id"] + "?category_code=TV"))
        self.assertTrue(chat["messages"][1]["evidence"])
        path = self.project + "/conversations?category_code=TV"
        before = self.call(path)
        with self.assertRaises(HTTPError):
            self.call(self.project + "/messages", {**body, "request_id":"m2", "attachment_ids":["bad"]})
        self.assertEqual(before, self.call(path))


if __name__ == "__main__":
    unittest.main()
