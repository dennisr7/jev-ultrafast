import importlib.util
from argparse import Namespace
from pathlib import Path

from jev_ultrafast.browser import StalePage

spec = importlib.util.spec_from_file_location("jev_task", Path(__file__).parent.parent / "scripts" / "jev_task.py")
jev_task = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev_task)


class FakeAgent:
    """Two clicks, then DONE. `stale_acts` makes the first act(s) raise StalePage."""

    def __init__(self, stale_acts=0):
        self.stale_acts = stale_acts
        self.state = {"status": "ready", "history": [], "decision": None, "page": {"url": "u", "fingerprint": "f"}}
        self.acts = 0

    def snapshot(self):
        return {**self.state, "elements": [{"index": "1", "label": "Go"}]}

    def command(self, name, body=None):
        s = self.state
        if name == "predict":
            done = len(s["history"]) >= 2
            s["decision"] = {
                "operation": "DONE" if done else "CLICK",
                "target": None if done else "1",
                "confidence": 0.9,
                "operation_probabilities": {"CLICK": 0.1, "DONE": 0.9} if done else {"CLICK": 0.9, "DONE": 0.1},
            }
            s["status"] = "predicted"
        elif name == "act":
            assert body == {"fingerprint": "f"}
            self.acts += 1
            if self.stale_acts:
                self.stale_acts -= 1
                raise StalePage("stale")
            if s["decision"]["operation"] == "DONE":
                s["status"] = "done"
            else:
                s["history"].append({"step": len(s["history"]) + 1, "action": "Go", "kind": "click"})
                s["status"] = "ready"
        elif name == "tick":
            self.command("predict")
            self.command("act", {"fingerprint": "f"})
        return self.snapshot()


def args(**kw):
    return Namespace(**{"step": True, "max_steps": 60, "timeout": 1, **kw})


def test_step_mode_pauses_before_every_action(monkeypatch, capsys):
    answers = iter(["go", "go", "go"])
    monkeypatch.setattr(jev_task, "approval", lambda *_: next(answers))
    agent = FakeAgent()
    assert jev_task.drive(agent, args(), Path("control")) == ("done", None)
    out = capsys.readouterr().out
    assert out.count('"event": "decision"') == 3 and out.count('"event": "action"') == 2
    assert '"element": "Go"' in out


def test_stop_and_skip_never_execute(monkeypatch):
    agent = FakeAgent()
    answers = iter(["skip", "stop"])
    monkeypatch.setattr(jev_task, "approval", lambda *_: next(answers))
    assert jev_task.drive(agent, args(), Path("control")) == ("stopped", None)
    assert agent.acts == 0


def test_stale_act_repredicts_instead_of_failing(monkeypatch):
    monkeypatch.setattr(jev_task, "approval", lambda *_: "go")
    agent = FakeAgent(stale_acts=1)
    assert jev_task.drive(agent, args(), Path("control")) == ("done", None)


def test_step_limit_and_autorun(monkeypatch):
    assert jev_task.drive(FakeAgent(), args(step=False), Path("control")) == ("done", None)
    assert jev_task.drive(FakeAgent(), args(step=False, max_steps=1), Path("control")) == ("step_limit", None)


def test_approval_reads_and_clears_control_file(tmp_path, monkeypatch):
    monkeypatch.setattr(jev_task.sys.stdin, "isatty", lambda: False, raising=False)
    control = tmp_path / "control"
    control.write_text("stale")  # an old answer must not approve a new decision
    assert jev_task.approval(control, 0.3) == "stop"
    import threading

    threading.Timer(0.1, lambda: control.write_text("GO\n")).start()
    assert jev_task.approval(control, 2) == "go" and not control.exists()


def test_describe_names_the_dropdown_option():
    state = {
        "history": [],
        "page": {"url": "u"},
        "decision": {
            "operation": "SELECT",
            "target": "6:2",
            "confidence": 0.5,
            "operation_probabilities": {"SELECT": 0.5},
        },
        "elements": [{"index": "6", "label": "Stay category", "options": [{"index": "6:2", "label": "Design"}]}],
    }
    assert jev_task.describe(state)["element"] == "Stay category"
    assert jev_task.describe(state)["option"] == "Design"
