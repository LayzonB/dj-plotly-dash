import json
import operator
import pytest

import dash_html_components as html
import dash_core_components as dcc

from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate, MissingCallbackContextException
import dash.testing.wait as wait

from selenium.webdriver.common.action_chains import ActionChains

from dash.testing.plugin import *
from .. import BaseDashView


def test_cbcx001_modified_response(dash_duo):
    class DashView(BaseDashView):
        def __init__(self, **kwargs):
            super(DashView, self).__init__(**kwargs)

            self.dash.layout = html.Div([dcc.Input(id="input", value="ab"), html.Div(id="output")])

            self.dash.callback(Output("output", "children"), [Input("input", "value")])(self.update_output)

        def update_output(self, value):
            self.response.set_cookie("dash_cookie", value + " - cookie")
            return value + " - output"

    dash_duo.start_server(DashView)

    dash_duo.wait_for_text_to_equal("#output", "ab - output")
    input1 = dash_duo.find_element("#input")

    input1.send_keys("cd")

    dash_duo.wait_for_text_to_equal("#output", "abcd - output")
    cookie = dash_duo.driver.get_cookie("dash_cookie")
    # cookie gets json encoded
    assert cookie["value"] == '"abcd - cookie"'

    assert not dash_duo.get_logs()


def test_cbcx002_triggered(dash_duo):
    btns = ["btn-{}".format(x) for x in range(1, 6)]

    class DashView(BaseDashView):
        def __init__(self, **kwargs):
            super(DashView, self).__init__(**kwargs)

            self.dash.layout = html.Div(
                [html.Div([html.Button(btn, id=btn) for btn in btns]), html.Div(id="output")]
            )

            self.dash.callback(Output("output", "children"), [Input(x, "n_clicks") for x in btns])(self.on_click)

        def on_click(self, *args):
            if not self.request.triggered_inputs:
                raise PreventUpdate
            trigger = self.request.triggered_inputs[0]
            return "Just clicked {} for the {} time!".format(
                trigger["prop_id"].split(".")[0], trigger["value"]
            )

    dash_duo.start_server(DashView)

    for i in range(1, 5):
        for btn in btns:
            dash_duo.find_element("#" + btn).click()
            dash_duo.wait_for_text_to_equal(
                "#output", "Just clicked {} for the {} time!".format(btn, i)
            )


@pytest.mark.skip
def test_cbcx003_no_callback_context():
    for attr in ["inputs", "states", "triggered", "response"]:
        with pytest.raises(MissingCallbackContextException):
            getattr(callback_context, attr)


def test_cbcx004_triggered_backward_compat(dash_duo):
    class DashView(BaseDashView):
        def __init__(self, **kwargs):
            super(DashView, self).__init__(**kwargs)

            self.dash.layout = html.Div([html.Button("click!", id="btn"), html.Div(id="out")])

            self.dash.callback(Output("out", "children"), [Input("btn", "n_clicks")])(self.report_triggered)

        def report_triggered(self, n):
            triggered = self.request.triggered_inputs
            bool_val = "truthy" if triggered else "falsy"
            split_propid = json.dumps(triggered[0]["prop_id"].split("."))
            full_val = json.dumps(triggered)
            return "triggered is {}, has prop/id {}, and full value {}".format(
                bool_val, split_propid, full_val
            )

    dash_duo.start_server(DashView)

    dash_duo.wait_for_text_to_equal(
        "#out",
        'triggered is falsy, has prop/id ["", ""], and full value '
        '[{"prop_id": ".", "value": null}]',
    )

    dash_duo.find_element("#btn").click()
    dash_duo.wait_for_text_to_equal(
        "#out",
        'triggered is truthy, has prop/id ["btn", "n_clicks"], and full value '
        '[{"prop_id": "btn.n_clicks", "value": 1}]',
    )


@pytest.mark.DASH1350
def test_cbcx005_grouped_clicks(dash_duo):
    class context:
        calls = 0
        callback_contexts = []
        clicks = dict()

    class DashView(BaseDashView):
        def __init__(self, **kwargs):
            super(DashView, self).__init__(**kwargs)

            self.dash.layout = html.Div(
                [
                    html.Button("Button 0", id="btn0"),
                    html.Div(
                        [
                            html.Button("Button 1", id="btn1"),
                            html.Div(
                                [html.Div(id="div3"), html.Button("Button 2", id="btn2")],
                                id="div2",
                                style=dict(backgroundColor="yellow", padding="50px"),
                            ),
                        ],
                        id="div1",
                        style=dict(backgroundColor="blue", padding="50px"),
                    ),
                ],
                id="div0",
                style=dict(backgroundColor="red", padding="50px"),
            )

            self.dash.callback(
                Output("div3", "children"),
                [
                    Input("div1", "n_clicks"),
                    Input("div2", "n_clicks"),
                    Input("btn0", "n_clicks"),
                    Input("btn1", "n_clicks"),
                    Input("btn2", "n_clicks"),
                ],
                prevent_initial_call=True,
            )(self.update)

        def update(self, div1, div2, btn0, btn1, btn2):
            context.calls = context.calls + 1
            context.callback_contexts.append(self.request.triggered_inputs)
            context.clicks["div1"] = div1
            context.clicks["div2"] = div2
            context.clicks["btn0"] = btn0
            context.clicks["btn1"] = btn1
            context.clicks["btn2"] = btn2

    def click(target):
        ActionChains(dash_duo.driver).move_to_element_with_offset(
            target, 5, 5
        ).click().perform()

    dash_duo.start_server(DashView)

    click(dash_duo.find_element("#btn0"))
    assert context.calls == 1
    keys = list(map(operator.itemgetter("prop_id"), context.callback_contexts[-1:][0]))
    assert len(keys) == 1
    assert "btn0.n_clicks" in keys

    assert context.clicks.get("btn0") == 1
    assert context.clicks.get("btn1") is None
    assert context.clicks.get("btn2") is None
    assert context.clicks.get("div1") is None
    assert context.clicks.get("div2") is None

    click(dash_duo.find_element("#div1"))
    assert context.calls == 2
    keys = list(map(operator.itemgetter("prop_id"), context.callback_contexts[-1:][0]))
    assert len(keys) == 1
    assert "div1.n_clicks" in keys

    assert context.clicks.get("btn0") == 1
    assert context.clicks.get("btn1") is None
    assert context.clicks.get("btn2") is None
    assert context.clicks.get("div1") == 1
    assert context.clicks.get("div2") is None

    click(dash_duo.find_element("#btn1"))
    assert context.calls == 3
    keys = list(map(operator.itemgetter("prop_id"), context.callback_contexts[-1:][0]))
    assert len(keys) == 2
    assert "btn1.n_clicks" in keys
    assert "div1.n_clicks" in keys

    assert context.clicks.get("btn0") == 1
    assert context.clicks.get("btn1") == 1
    assert context.clicks.get("btn2") is None
    assert context.clicks.get("div1") == 2
    assert context.clicks.get("div2") is None

    click(dash_duo.find_element("#div2"))
    assert context.calls == 4
    keys = list(map(operator.itemgetter("prop_id"), context.callback_contexts[-1:][0]))
    assert len(keys) == 2
    assert "div1.n_clicks" in keys
    assert "div2.n_clicks" in keys

    assert context.clicks.get("btn0") == 1
    assert context.clicks.get("btn1") == 1
    assert context.clicks.get("btn2") is None
    assert context.clicks.get("div1") == 3
    assert context.clicks.get("div2") == 1

    click(dash_duo.find_element("#btn2"))
    assert context.calls == 5
    keys = list(map(operator.itemgetter("prop_id"), context.callback_contexts[-1:][0]))
    assert len(keys) == 3
    assert "btn2.n_clicks" in keys
    assert "div1.n_clicks" in keys
    assert "div2.n_clicks" in keys

    assert context.clicks.get("btn0") == 1
    assert context.clicks.get("btn1") == 1
    assert context.clicks.get("btn2") == 1
    assert context.clicks.get("div1") == 4
    assert context.clicks.get("div2") == 2


@pytest.mark.DASH1350
def test_cbcx006_initial_callback_predecessor(dash_duo):
    class context:
        calls = 0
        callback_contexts = []

    class DashView(BaseDashView):
        def __init__(self, **kwargs):
            super(DashView, self).__init__(**kwargs)

            self.dash.layout = html.Div(
                [
                    html.Div(
                        style={"display": "block"},
                        children=[
                            html.Div(
                                [
                                    html.Label("ID: input-number-1"),
                                    dcc.Input(id="input-number-1", type="number", value=0),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("ID: input-number-2"),
                                    dcc.Input(id="input-number-2", type="number", value=0),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("ID: sum-number"),
                                    dcc.Input(
                                        id="sum-number", type="number", value=0, disabled=True
                                    ),
                                ]
                            ),
                        ],
                    ),
                    html.Div(id="results"),
                ]
            )

            self.dash.callback(
                Output("sum-number", "value"),
                [Input("input-number-1", "value"), Input("input-number-2", "value")],
            )(self.update_sum_number)
            self.dash.callback(
                Output("results", "children"),
                [
                    Input("input-number-1", "value"),
                    Input("input-number-2", "value"),
                    Input("sum-number", "value"),
                ],
            )(self.update_results)

        def update_sum_number(self, n1, n2):
            context.calls = context.calls + 1
            context.callback_contexts.append(self.request.triggered_inputs)

            return n1 + n2

        def update_results(self, n1, n2, nsum):
            context.calls = context.calls + 1
            context.callback_contexts.append(self.request.triggered_inputs)

            return [
                "{} + {} = {}".format(n1, n2, nsum),
                html.Br(),
                "ctx.triggered={}".format(self.request.triggered_inputs),
            ]

    dash_duo.start_server(DashView)

    # Initial Callbacks
    wait.until(lambda: context.calls == 2, 2)
    wait.until(lambda: len(context.callback_contexts) == 2, 2)

    keys0 = list(map(operator.itemgetter("prop_id"), context.callback_contexts[0]))
    # Special case present for backward compatibility
    assert len(keys0) == 1
    assert "." in keys0

    keys1 = list(map(operator.itemgetter("prop_id"), context.callback_contexts[1]))
    assert len(keys1) == 1
    assert "sum-number.value" in keys1

    # User action & followup callbacks
    dash_duo.find_element("#input-number-1").click()
    dash_duo.find_element("#input-number-1").send_keys("1")

    wait.until(lambda: context.calls == 4, 2)
    wait.until(lambda: len(context.callback_contexts) == 4, 2)

    keys0 = list(map(operator.itemgetter("prop_id"), context.callback_contexts[2]))
    # Special case present for backward compatibility
    assert len(keys0) == 1
    assert "input-number-1.value" in keys0

    keys1 = list(map(operator.itemgetter("prop_id"), context.callback_contexts[3]))
    assert len(keys1) == 2
    assert "sum-number.value" in keys1
    assert "input-number-1.value" in keys1

    dash_duo.find_element("#input-number-2").click()
    dash_duo.find_element("#input-number-2").send_keys("1")

    wait.until(lambda: context.calls == 6, 2)
    wait.until(lambda: len(context.callback_contexts) == 6, 2)

    keys0 = list(map(operator.itemgetter("prop_id"), context.callback_contexts[4]))
    # Special case present for backward compatibility
    assert len(keys0) == 1
    assert "input-number-2.value" in keys0

    keys1 = list(map(operator.itemgetter("prop_id"), context.callback_contexts[5]))
    assert len(keys1) == 2
    assert "sum-number.value" in keys1
    assert "input-number-2.value" in keys1
