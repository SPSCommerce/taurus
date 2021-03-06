import logging
import math
import os
import time
import urwid
import yaml

from bzt.engine import ScenarioExecutor
from bzt.modules.aggregator import ConsolidatingAggregator, DataPoint, KPISet, AggregatorListener
from bzt.modules.pbench import PBenchExecutor, Scheduler
from bzt.six import StringIO, parse
from bzt.utils import BetterDict
from tests import BZTestCase, __dir__
from tests.mocks import EngineEmul


class TestPBench(BZTestCase):
    def test_simple(self):
        obj = PBenchExecutor()
        obj.engine = EngineEmul()
        obj.engine.aggregator = ConsolidatingAggregator()
        obj.engine.aggregator.add_listener(DataPointLogger())
        obj.engine.config.merge({"provisioning": "test"})

        if os.path.exists("/home/undera/Sources/phantom"):  # FIXME: not good, get rid of it
            obj.settings.merge({
                "path": "/home/undera/Sources/phantom/bin/phantom",
                "modules-path": "/home/undera/Sources/phantom/lib/phantom",
            })
        else:
            obj.settings.merge({
                "path": os.path.join(os.path.dirname(__file__), '..', "phantom.sh"),
            })

        obj.execution.merge({
            "log-responses": "proto_error",
            # "iterations": 5000000,
            "concurrency": 10,
            "throughput": 1000,
            "ramp-up": "1m",
            # "steps": 5,
            "hold-for": "15",
            "scenario": {
                "timeout": 1,
                "default-address": "http://localhost:33",
                "headers": {
                    "Connection": "close"
                },
                "requests": [
                    # "/",
                    {
                        "url": "/api",
                        "method": "POST",
                        "headers": {
                            "Content-Length": 0
                        },
                        "body": {
                            "param": "value"
                        }
                    }

                ]
            }
        })
        obj.engine.aggregator.prepare()
        obj.prepare()

        obj.engine.aggregator.startup()
        obj.startup()

        while not obj.check():
            logging.debug("Running...")
            obj.engine.aggregator.check()
            time.sleep(1)

        obj.shutdown()
        obj.engine.aggregator.shutdown()

        obj.post_process()
        obj.engine.aggregator.post_process()

    def test_schedule_rps(self):
        executor = PBenchExecutor()
        executor.engine = EngineEmul()
        executor.engine.config.merge({"provisioning": "test"})
        rps = 9
        rampup = 12
        executor.execution.merge({"throughput": rps, "ramp-up": rampup, "steps": 3, "hold-for1": 0})
        obj = Scheduler(executor.get_load(), StringIO("4 test\ntest\n"), logging.getLogger(""))

        cnt = 0
        cur = 0
        currps = 0
        for item in obj.generate():
            # logging.debug("Item: %s", item)
            if int(math.ceil(item[0])) != cur:
                # self.assertLessEqual(currps, rps)
                cur = int(math.ceil(item[0]))
                logging.debug("RPS: %s", currps)
                currps = 0

            cnt += 1
            currps += 1

        logging.debug("RPS: %s", currps)

    def test_schedule_empty(self):
        executor = PBenchExecutor()
        executor.engine = EngineEmul()
        try:
            obj = Scheduler(executor.get_load(), StringIO("4 test\ntest\n"), logging.getLogger(""))
            for item in obj.generate():
                logging.debug("Item: %s", item)
            self.fail()
        except NotImplementedError:
            pass

    def test_widget(self):
        obj = PBenchExecutor()
        obj.engine = EngineEmul()
        obj.settings = BetterDict()
        obj.engine.config.merge({
            "provisioning": "test",
            ScenarioExecutor.EXEC: [
                {
                    "throughput": 10,
                    "hold-for": 30,
                    "scenario": {
                        "default-address": "http://blazedemo.com/",
                        "requests": ["/"]
                    }
                }
            ]})
        obj.execution = obj.engine.config['execution'][0]
        obj.settings.merge({
            "path": os.path.join(os.path.dirname(__file__), '..', "phantom.sh"),
        })
        obj.prepare()
        obj.startup()
        obj.get_widget()
        self.assertTrue(isinstance(obj.widget.progress, urwid.ProgressBar))
        self.assertEqual(obj.widget.duration, 30)
        self.assertEqual(obj.widget.widgets[0].text, "Target: http://blazedemo.com:80")
        obj.check()
        obj.shutdown()

    def test_improved_request_building(self):
        obj = PBenchExecutor()
        obj.engine = EngineEmul()
        obj.settings = BetterDict()
        obj.engine.config = BetterDict()
        obj.engine.config.merge(yaml.load(open(__dir__() + "/../yaml/phantom_improved_request.yml").read()))
        obj.execution = obj.engine.config['execution'][0]
        obj.settings.merge({
            "path": os.path.join(os.path.dirname(__file__), '..', "phantom.sh"),
        })
        obj.prepare()
        with open(obj.pbench.schedule_file) as fds:
            config = fds.readlines()

        get_requests = [req_str.split(" ")[1] for req_str in config if req_str.startswith("GET")]
        self.assertEqual(len(get_requests), 2)

        for get_req in get_requests:
            self.assertEqual(dict(parse.parse_qsl(parse.urlsplit(get_req).query)),
                             {"get_param1": "value1", "get_param2": "value2"})

    def test_same_address_port(self):
        obj = PBenchExecutor()
        obj.engine = EngineEmul()
        obj.settings = BetterDict()
        obj.engine.config = BetterDict()
        obj.engine.config.merge(yaml.load(open(__dir__() + "/../yaml/phantom_request_same_address.yml").read()))
        obj.execution = obj.engine.config['execution'][0]
        obj.settings.merge({
            "path": os.path.join(os.path.dirname(__file__), '..', "phantom.sh"),
        })
        try:
            obj.prepare()
            self.fail()
        except ValueError:
            pass

    def test_install_pbench(self):
        obj = PBenchExecutor()
        obj.engine = EngineEmul()
        obj.settings = BetterDict()
        obj.engine.config = BetterDict()
        obj.settings.merge({"path": "/notexistent"})
        # obj.execution = obj.engine.config['execution'][0]
        try:
            obj.prepare()
            self.fail()
        except RuntimeError as exc:
            self.assertEquals("Please install PBench tool manually", str(exc))

    def test_pbench_file_lister(self):
        obj = PBenchExecutor()
        obj.engine = EngineEmul()
        obj.settings = BetterDict()
        obj.engine.config = BetterDict()
        obj.engine.config.merge(
            {ScenarioExecutor.EXEC: {"executor": "pbench", "scenario": {"script": "/opt/data/script.src"}}})
        obj.execution = obj.engine.config['execution']
        obj.settings.merge({
            "path": os.path.join(os.path.dirname(__file__), '..', "phantom.sh"),
        })
        resource_files = obj.resource_files()
        self.assertEqual(1, len(resource_files))
        self.assertEqual(resource_files[0], 'script.src')


class DataPointLogger(AggregatorListener):
    def aggregated_second(self, data):
        current = data[DataPoint.CURRENT]['']
        logging.info("DataPoint %s: VU:%s RPS:%s/%s RT:%s", data[DataPoint.TIMESTAMP],
                     current[KPISet.CONCURRENCY], current[KPISet.SAMPLE_COUNT], current[KPISet.FAILURES],
                     current[KPISet.AVG_RESP_TIME])
