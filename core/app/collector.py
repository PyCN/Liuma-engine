import json


class AppOperationCollector:

    def __init__(self):
        self.id = None
        self.opt_type = None
        self.opt_system = None
        self.opt_name = None
        self.opt_trans = None
        self.opt_element = None
        self.opt_data = None
        self.opt_code = None

    @staticmethod
    def __parse(ui_data: dict, name):
        if name not in ui_data:
            return None
        return ui_data.get(name)

    def collect_id(self, ui_data):
        self.id = AppOperationCollector.__parse(ui_data, "operationId")

    def collect_opt_type(self, ui_data):
        self.opt_type = AppOperationCollector.__parse(ui_data, "operationType")

    def collect_opt_system(self, ui_data):
        self.opt_system = AppOperationCollector.__parse(ui_data, "operationSystem")

    def collect_opt_name(self, ui_data):
        self.opt_name = AppOperationCollector.__parse(ui_data, "operationName")

    def collect_opt_trans(self, ui_data):
        self.opt_trans = AppOperationCollector.__parse(ui_data, "operationTrans")

    def collect_opt_code(self, ui_data):
        self.opt_code = AppOperationCollector.__parse(ui_data, "operationCode")

    def collect_opt_element(self, ui_data):
        opt_element = AppOperationCollector.__parse(ui_data, "operationElement")
        if opt_element is None or len(opt_element) == 0:
            self.opt_element = None
        else:
            elements = {}
            for name, element in opt_element.items():
                props = {}
                if element["by"].lower() == "prop":
                    for prop in json.loads(element["expression"]):
                        props[prop["propName"]] = prop["propValue"]
                else:
                    props[element["by"].lower()] = element["expression"]
                elements[name] = props
            self.opt_element = elements

    def collect_opt_data(self, ui_data):
        opt_data = AppOperationCollector.__parse(ui_data, "operationData")
        if opt_data is None or len(opt_data) == 0:
            self.opt_data = None
        else:
            self.opt_data = opt_data

    def collect(self, ui_data):
        self.collect_id(ui_data)
        self.collect_opt_type(ui_data)
        self.collect_opt_system(ui_data)
        self.collect_opt_name(ui_data)
        self.collect_opt_trans(ui_data)
        self.collect_opt_element(ui_data)
        self.collect_opt_data(ui_data)
        self.collect_opt_code(ui_data)

