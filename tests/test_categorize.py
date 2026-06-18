from server.categorize import Signals, Guess, guess


def _sig(org=None, emails=(), path=None, collab=False):
    return Signals(remote_org=org, email_domains=tuple(emails),
                   path_prefix=path, is_collaboration=collab)


def test_high_confidence_two_axes_agree():
    target = _sig(org="acme", emails=("acme.com",), path="/r")
    labeled = [
        (_sig(org="acme", emails=("acme.com",), path="/r"), "Work"),
        (_sig(org="acme", emails=("acme.com",), path="/r"), "Work"),
    ]
    g = guess(target, labeled)
    assert g.guess == "Work"
    assert g.confidence == "high"
    assert g.reasons


def test_medium_confidence_single_axis():
    target = _sig(org="acme")
    labeled = [
        (_sig(org="acme"), "Work"),
        (_sig(org="other"), "Personal"),
    ]
    g = guess(target, labeled)
    assert g.guess == "Work"
    assert g.confidence == "medium"


def test_conflicting_signals_yield_no_guess():
    target = _sig(org="acme", path="/shared")
    labeled = [
        (_sig(org="acme", path="/shared"), "Work"),
        (_sig(org="acme", path="/shared"), "Personal"),
    ]
    g = guess(target, labeled)
    # org and path both match repos of BOTH categories -> neither axis discriminates
    assert g.guess is None
    assert g.confidence == "low"


def test_cold_start_under_two_labels():
    g = guess(_sig(org="acme"), [(_sig(org="acme"), "Work")])
    assert g.guess is None
    assert g.confidence == "low"
