import datetime
import sys
from time import sleep

from requests import request, Session
from copy import deepcopy
import json

from core.assertion import LMAssert
from tools.utils.sql import SQLConnect
from tools.utils.utils import extract, ExtractValueError, url_join
from urllib.parse import urlencode

REQUEST_CNAME_MAP = {
    'headers': '请求头',
    'proxies': '代理',
    'cookies': 'cookies',
    'params': '查询参数',
    'data': '请求体',
    'json': '请求体',
    'files': '上传文件'
}


class ApiTestStep:

    def __init__(self, test, session, collector, context, params):
        self.session = session
        self.collector = collector
        self.context = context
        self.params = params
        self.test = test
        self.status_code = None
        self.response_headers = None
        self.response_content = None
        self.response_content_bytes = None
        self.response_cookies = None
        self.assert_result = None
        self.print = print

    def execute(self):
        try:
            self.test.debugLog('[{}]接口执行开始'.format(self.collector.apiName))
            request_log = '【请求信息】:<br>'
            request_log += '{} {}<br>'.format(self.collector.method, url_join(self.collector.url, self.collector.path))
            for key, value in self.collector.others.items():
                if value is not None:
                    c_key = REQUEST_CNAME_MAP[key] if key in REQUEST_CNAME_MAP else key
                    if key == 'files':
                        if isinstance(value, dict):
                            request_log += '{}: {}<br>'.format(c_key, ["文件长度%s: %s" % (k, len(v)) for k,v in value.items()])
                        if isinstance(value, list):
                            request_log += '{}: {}<br>'.format(c_key, [i[1][0] for i in value])
                    elif c_key == '请求体':
                        request_log += '<span>{}: {}</span><br>'.format(c_key, dict2str(value))
                    else:
                        request_log += '{}: {}<br>'.format(c_key, dict2str(value))
            self.test.debugLog(request_log[:-4])
            if self.collector.body_type == "form-urlencoded" and 'data' in self.collector.others:
                self.collector.others['data'] = urlencode(self.collector.others['data'])
            if self.collector.body_type in ("text", "xml", "html") and 'data' in self.collector.others:
                self.collector.others['data'] = str(self.collector.others['data']).encode("utf-8")
            if 'files' in self.collector.others and self.collector.others['files'] is not None:
                self.pop_content_type()
            url = url_join(self.collector.url, self.collector.path)
            if int(self.collector.controller["sleepBeforeRun"]) > 0:
                sleep(int(self.collector.controller["sleepBeforeRun"]))
                self.test.debugLog("请求前等待%sS" % int(self.collector.controller["sleepBeforeRun"]))
            start_time = datetime.datetime.now()
            if self.collector.controller["useSession"].lower() == 'true' and self.collector.controller["saveSession"].lower() == "true":
                res = self.session.session.request(self.collector.method, url, **self.collector.others)
            elif self.collector.controller["useSession"].lower() == "true":
                session = deepcopy(self.session.session)
                res = session.request(self.collector.method, url, **self.collector.others)
            elif self.collector.controller["saveSession"].lower() == "true":
                session = Session()
                res = session.request(self.collector.method, url, **self.collector.others)
                self.session.session = session
            else:
                res = request(self.collector.method, url, **self.collector.others)
            end_time = datetime.datetime.now()
            self.test.recordTransDuring(int((end_time-start_time).microseconds/1000))
            self.save_response(res)
            response_log = '【响应信息】:<br>'
            response_log += '响应码: {}<br>'.format(self.status_code)
            response_log += '响应头: {}<br>'.format(dict2str(self.response_headers))
            if 'content-disposition' not in [key.lower() for key in self.response_headers.keys()]:
                response_text = '<b>响应体: {}</b>'.format(dict2str(self.response_content))
            else:
                response_text = '<b>响应体: 文件内容暂不展示, 长度{}</b>'.format(len(self.response_content_bytes))
            response_log += response_text
            self.test.debugLog(response_log)
            # 断言
            self.check()
            # 关联参数
            self.extract_depend_params()
        finally:
            self.test.debugLog('[{}]接口执行结束'.format(self.collector.apiName))
            if int(self.collector.controller["sleepAfterRun"]) > 0:
                sleep(int(self.collector.controller["sleepAfterRun"]))
                self.test.debugLog("请求后等待%sS" % int(self.collector.controller["sleepAfterRun"]))

    def looper_controller(self, case, api_list, step_n):
        """循环控制器"""
        if "type" in self.collector.looper and self.collector.looper["type"] == "WHILE":
            # while循环 且兼容之前只有for循环
            loop_start_time = datetime.datetime.now()
            while self.collector.looper["timeout"] == 0 or (datetime.datetime.now() - loop_start_time).seconds * 1000 \
                    < self.collector.looper["timeout"]:     # timeout为0时可能会死循环 慎重选择
                # 渲染循环控制控制器 每次循环都需要渲染
                _looper = case.render_looper(self.collector.looper)
                result, _ = LMAssert(_looper['assertion'], _looper['target'], _looper['expect']).compare()
                if not result:
                    break
                _api_list = api_list[step_n: (step_n + _looper["num"])]
                case.loop_execute(_api_list, api_list[step_n]["apiId"])
        else:
            # 渲染循环控制控制器 for只需渲染一次
            _looper = case.render_looper(self.collector.looper)
            for index in range(_looper["times"]):  # 本次循环次数
                self.context[_looper["indexName"]] = index  # 给循环索引赋值第几次循环 母循环和子循环的索引名不应一样
                _api_list = api_list[step_n: (step_n + _looper["num"])]
                case.loop_execute(_api_list, api_list[step_n]["apiId"])

    def condition_controller(self, case):
        """条件控制器"""
        _conditions = case.render_conditions(self.collector.conditions)
        for condition in _conditions:
            try:
                result, msg = LMAssert(condition['assertion'], condition['target'], condition['expect']).compare()
                if not result:
                    return msg
            except Exception as e:
                return str(e)
        else:
            return True

    def exec_script(self, code):
        """执行前后置脚本"""
        def print(*args, sep=' ', end='\n', file=None, flush=False):
            if file is None or file in (sys.stdout, sys.stderr):
                file = self.test.stdout_buffer
            self.print(*args, sep=sep, end=end, file=file, flush=flush)

        def sys_put(name, val, ps=False):
            if ps:  # 默认给关联参数赋值，只有多传入true时才会给公参赋值
                self.params[name] = val
            else:
                self.context[name] = val

        def sys_get(name):
            if name in self.context:   # 优先从公参中取值
                return self.context[name]
            elif name in self.params:
                return self.params[name]
            else:
                raise KeyError("不存在的公共参数或关联变量: {}".format(name))

        names = locals()
        names["res_code"] = self.status_code
        names["res_header"] = self.response_headers
        names["res_data"] = self.response_content
        names["res_cookies"] = self.response_cookies
        names["res_bytes"] = self.response_content_bytes
        exec(code)

    def exec_sql(self, sql, case):
        """执行前后置sql"""
        if sql == "{}":
            return
        sql = json.loads(case.render_sql(sql))
        if "host" not in sql["db"]:
            raise KeyError("获取数据库连接信息失败 请检查配置")
        conn = SQLConnect(**sql["db"])
        if sql["sqlType"] != "query":
            conn.exec(sql["sqlText"])
        else:
            results = conn.query(sql["sqlText"])
            names = sql["names"].split(",")  # name数量可以比结果数量段，但不能长，不能会indexError
            values = {}
            for r in results:
                for i, v in enumerate(r):
                    if i not in values.keys():
                        values[i] = []
                    values[i].append(v)
            for j, n in enumerate(names):
                if len(values) == 0:
                    self.context[n] = []    # 如果查询结果为空 则变量保存为空数组
                    continue
                if j not in values.keys():
                    raise IndexError("变量数错误, 请检查变量数配置是否与查询语句一致，当前查询结果: <br>{}".format(results))
                self.context[n] = values[j]  # 保存变量到变量空间

    def save_response(self, res):
        """保存响应结果"""
        self.status_code = res.status_code
        self.response_headers = dict(res.headers)
        self.response_content_bytes = res.content
        s = ''
        for key, value in res.cookies.items():
            s += '{}={};'.format(key, value)
        self.response_cookies = s[:-1]
        try:
            self.response_content = res.json()
        except Exception:
            self.response_content = res.text

    def extract_depend_params(self):
        """关联参数"""
        if self.collector.relations is not None:
            for items in self.collector.relations:
                if items['expression'].strip() == '$':
                    value = self.response_content_bytes
                elif items['expression'].strip().lower() in ['cookie', 'cookies']:
                    value = self.response_cookies
                else:
                    if items['from'] == 'resHeader':
                        data = self.response_headers
                    elif items['from'] == 'resBody':
                        data = self.response_content
                    elif items['from'] == 'reqHeader':
                        data = self.collector.others['headers']
                    elif items['from'] == 'reqQuery':
                        data = self.collector.others['params']
                    elif items['from'] == 'reqBody':
                        if self.collector.body_type == "json":
                            data = self.collector.others['json']
                        else:
                            data = self.collector.others['data']
                    else:
                        raise ExtractValueError('无法从{}位置提取依赖参数'.format(items['from']))
                    value = extract(items['method'], data, items['expression'])
                key = items['name']
                self.context[key] = value

    def check(self):
        """断言"""
        check_messages = list()
        if self.collector.assertions is not None:
            results = list()
            for items in self.collector.assertions:
                try:
                    if items['from'] == 'resCode':
                        actual = self.status_code
                    elif items['from'] == 'resHeader':
                        actual = extract(items['method'], self.response_headers, items['expression'])
                    elif items['from'] == 'resBody':
                        actual = extract(items['method'], self.response_content, items['expression'])
                    else:
                        raise ExtractValueError('无法在{}位置进行断言'.format(items['from']))
                    result, msg = LMAssert(items['assertion'], actual, items['expect']).compare()
                except ExtractValueError as e:
                    result = False
                    msg = '接口响应失败或{}'.format(str(e))
                results.append(result)
                check_messages.append(msg)
                if not result:
                    break
            final_result = all(results)
        else:
            final_result, msg = LMAssert('相等', self.status_code, str(200)).compare()
            check_messages.append(msg)
        self.assert_result = {
            'apiId': self.collector.apiId,
            'apiName': self.collector.apiName,
            'result': final_result,
            'checkMessages': check_messages
        }

    def pop_content_type(self):
        if self.collector.others['headers'] is None:
            return
        pop_key = None
        for key, value in self.collector.others['headers'].items():
            if key.lower() == 'content-type':
                pop_key = key
                break
        if pop_key is not None:
            self.collector.others['headers'].pop(pop_key)


def dict2str(data):
    if isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    elif not isinstance(data, str):
        return str(data)
    else:
        return data


class RemoveParamError(Exception):
    """参数移除错误"""


class AssertRelationError(Exception):
    """断言关系错误"""
