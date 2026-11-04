"""Offline contracts for the general harness: handles, direct execution, replay, tools. No browser, no paid APIs."""

from copy import deepcopy

import pytest

from jev_ultrafast import harness as h
from jev_ultrafast import model, tools
from jev_ultrafast.browser import StalePage, fingerprint


def make_page(rows=("Alpha", "Beta")):
    actions = [
        {"id": "e1", "kind": "fill", "label": "Search", "role": "textbox", "value": "", "node": 1},
        {"id": "e2", "kind": "click", "label": "Open Search", "role": "textbox", "value": "", "node": 1},
    ]
    guards = {"1": [1, "textbox", "Search", "", None, None, None, False, None, None, None, None, None, "Search form"]}
    node = 2
    for row in rows:
        actions.append({"id": f"e{len(actions) + 1}", "kind": "click", "label": "Delete", "role": "button",
                        "value": "", "node": node})
        guards[str(node)] = [node, "button", "Delete", None, None, None, None, False, None, None, None, None, None,
                             f"Row {row}"]
        node += 1
    actions += [
        {"id": f"e{len(actions) + 1}", "kind": "select", "label": "Sort → Newest", "role": "combobox",
         "value": "new", "current_value": "Oldest", "node": 50},
        {"id": f"e{len(actions) + 2}", "kind": "select", "label": "Sort → Oldest", "role": "combobox",
         "value": "old", "current_value": "Oldest", "node": 50},
        {"id": "scroll_down", "kind": "scroll", "label": "Scroll down", "delta": 560},
        {"id": "wait", "kind": "wait", "label": "Wait for the page to update"},
    ]
    guards["50"] = [50, "combobox", "Sort", "old", None, 0, None, False, None, None, None, None, None, "Sort bar"]
    state = {"url": "https://example.test/", "title": "List", "text": "List", "scroll": {"y": 0},
             "actions": actions, "guards": guards, "form": {"empty": []}}
    state["fingerprint"] = fingerprint(state)
    return state


class FakeBrowser:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.index = 0
        self.acted = []
        self.is_fresh = True
        self.closed = False

    def observe(self, screenshot=True):
        return deepcopy(self.pages[min(self.index, len(self.pages) - 1)])

    def fresh(self, page, action=None):
        return self.is_fresh

    def act(self, action, page, text=None):
        self.acted.append((action["id"], text))
        self.index += 1

    def close(self):
        self.closed = True


def test_handles_distinguish_identical_controls_by_nearby_text_and_survive_rebuild():
    first = h.handles(make_page())
    assert len(set(first.values())) == len(first)
    deletes = [v for v in first.values() if v.startswith("delete-")]
    assert len(deletes) == 2 and deletes[0].split(".")[0] != deletes[1].split(".")[0]
    # Rebuilding the page with different node ids yields the same handles.
    shifted = make_page()
    for a in shifted["actions"]:
        if "node" in a:
            a["node"] += 100
    shifted["guards"] = {str(int(k) + 100): v for k, v in shifted["guards"].items()}
    assert sorted(h.handles(shifted).values()) == sorted(first.values())


def test_identical_controls_in_identical_context_get_ordinals():
    page = make_page(rows=("Same", "Same"))
    deletes = sorted(v for v in h.handles(page).values() if v.startswith("delete-"))
    assert deletes[1] == deletes[0] + ".2"


def test_view_lists_operations_options_and_controls():
    observation = h.view(make_page())
    search = next(e for e in observation["elements"] if e["label"] == "Search")
    assert search["operations"] == ["TYPE_TEXT", "CLICK"]
    sort = next(e for e in observation["elements"] if e["label"] == "Sort")
    assert sort["operations"] == ["SELECT"] and sort["options"] == ["Newest", "Oldest"] and sort["value"] == "Oldest"
    assert {c["operation"] for c in observation["controls"]} == {"SCROLL_DOWN", "WAIT"}
    assert "[" + search["handle"] + "]" in h.render(observation)


def test_act_executes_by_handle_without_a_model_call(monkeypatch):
    monkeypatch.setattr(model, "post_json", lambda *a: pytest.fail("a direct act must not call a model"))
    browser = FakeBrowser(make_page())
    harness = h.Harness(browser=browser)
    search = next(e for e in harness.observe()["elements"] if e["label"] == "Search")
    result = harness.act(search["handle"], "type_text", text="Zurich")
    assert browser.acted == [("e1", "Zurich")]
    assert result["executed"]["operation"] == "TYPE_TEXT" and harness.trace == [result["executed"]]


def test_act_refuses_unobserved_stale_and_unsupported_requests():
    browser = FakeBrowser(make_page())
    harness = h.Harness(browser=browser)
    with pytest.raises(StalePage):
        harness.act("x", "CLICK")
    observation = harness.observe()
    search = next(e for e in observation["elements"] if e["label"] == "Search")
    with pytest.raises(h.HandleError, match="does not support SELECT"):
        harness.act(search["handle"], "SELECT", option="x")
    with pytest.raises(h.HandleError, match="No element"):
        harness.act("invented-000000", "CLICK")
    with pytest.raises(ValueError, match="needs text"):
        harness.act(search["handle"], "TYPE_TEXT")
    browser.is_fresh = False
    with pytest.raises(StalePage):
        harness.act(search["handle"], "CLICK")
    assert browser.acted == []


def test_select_matches_option_label_or_value_and_scroll_controls_work():
    browser = FakeBrowser(make_page())
    harness = h.Harness(browser=browser)
    sort = next(e for e in harness.observe()["elements"] if e["label"] == "Sort")
    harness.act(sort["handle"], "SELECT", option="newest")
    assert browser.acted[-1][0] == "e5"
    harness.act(None, "SCROLL_DOWN")
    assert browser.acted[-1][0] == "scroll_down"


def test_replay_finds_elements_again_and_reports_where_it_stops():
    first = FakeBrowser(make_page())
    recorder = h.Harness(browser=first)
    search = next(e for e in recorder.observe()["elements"] if e["label"] == "Search")
    recorder.act(search["handle"], "TYPE_TEXT", text="Zurich")
    trace = list(recorder.trace)

    again = FakeBrowser(make_page())
    assert h.Harness(browser=again).replay(trace) == {"ok": True, "steps": 1}
    assert again.acted == [("e1", "Zurich")]

    gone = make_page()
    gone["actions"] = [a for a in gone["actions"] if a.get("node") != 1]
    broken = h.Harness(browser=FakeBrowser(gone)).replay(trace)
    assert broken["ok"] is False and broken["failed_at"] == 0 and "No element" in broken["error"]


def test_tools_return_errors_instead_of_raising_and_honor_the_approval_gate():
    browser = FakeBrowser(make_page())
    harness = h.Harness(browser=browser)
    assert tools.dispatch(harness, "act", {"operation": "WAIT"})["error"] == "StalePage"
    observed = tools.dispatch(harness, "observe")
    assert "table" in observed
    delete = next(e for e in observed["observation"]["elements"] if e["label"] == "Delete")
    refused = tools.dispatch(harness, "act", {"handle": delete["handle"], "operation": "CLICK"},
                             approve=lambda name, args, label: label != "Delete")
    assert refused["error"] == "refused" and browser.acted == []
    done = tools.dispatch(harness, "act", {"handle": delete["handle"], "operation": "CLICK"},
                          approve=lambda name, args, label: True)
    assert done["executed"]["operation"] == "CLICK" and browser.acted
    assert tools.dispatch(harness, "nope")["error"] == "UnknownTool"
    assert {t["name"] for t in tools.TOOLS} == {"observe", "act", "run_goal", "replay"}


def test_post_json_retries_transport_failures_then_reports_no_action(monkeypatch):
    import httpx

    calls = []

    class Client:
        def post(self, *a, **k):
            calls.append(1)
            raise httpx.ConnectError("down")

    monkeypatch.setattr(model, "CLIENT", Client())
    monkeypatch.setattr(model.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="no action executed"):
        model.post_json("https://x.test", "k", {})
    assert len(calls) == 3


def test_replay_falls_back_to_a_unique_label_but_never_to_a_duplicate():
    browser = FakeBrowser(make_page(), make_page(), make_page())
    harness = h.Harness(browser=browser)
    observation = harness.observe()
    search = next(e for e in observation["elements"] if e["label"] == "Search")
    harness.act(search["handle"], "TYPE_TEXT", text="a")
    unique_step = harness.trace[0]
    assert unique_step["unique"] is True and unique_step["label"] == "Search"
    harness.page = None
    delete = next(e for e in harness.observe()["elements"] if e["label"] == "Delete")
    harness.act(delete["handle"], "CLICK")
    duplicate_step = harness.trace[1]
    assert duplicate_step["unique"] is False

    # The nearby text changed, so the exact handles are gone.
    changed = make_page(rows=("Gamma", "Delta"))
    changed["guards"]["1"][-1] = "Different search form"
    changed["fingerprint"] = fingerprint(changed)
    replay = h.Harness(browser=FakeBrowser(changed))
    assert replay.replay([unique_step]) == {"ok": True, "steps": 1}
    broken = h.Harness(browser=FakeBrowser(changed)).replay([duplicate_step])
    assert broken["ok"] is False and "No element" in broken["error"]
