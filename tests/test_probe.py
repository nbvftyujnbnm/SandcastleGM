from sandcastlegm.probe import ProbeRunner, auto_score
from sandcastlegm.probe.scenarios import SCENARIOS, Scenario
from sandcastlegm.probe.scoring import build_judge_prompt, parse_judge

GOOD_NPC = (
    "Ash drifts through the lantern glow as a woman steps from the shadow of a "
    "rusted stall, the acrid smell of soot clinging to her coat. \"You're late,\" "
    "Nora mutters, eyes flicking to the grey crowd behind you. \"And you brought "
    "trouble.\" Her hand rests on a scarred relic. What do you say to her?"
)


def test_scenarios_unique_keys_and_nonempty():
    keys = [s.key for s in SCENARIOS]
    assert len(keys) == len(set(keys))
    assert all(s.instruction for s in SCENARIOS)


def test_auto_score_pass_on_good_npc_scene():
    scn = next(s for s in SCENARIOS if s.key == "npc_meeting")
    a = auto_score(GOOD_NPC, scn)
    assert a.has_dialogue and a.has_hook
    assert a.sensory_per_100w >= 1.0
    assert a.verdict in ("PASS", "WARN")  # dialogue + hook present
    assert a.verdict != "FAIL"


def test_auto_score_fails_when_too_short():
    a = auto_score("You arrive.", Scenario("x", "x"))
    assert a.verdict == "FAIL"
    assert "length" in a.flags


def test_auto_score_flags_dice_leak():
    text = (
        "The axe bites deep and the goblin staggers, ash swirling around its "
        "wound as it shrieks into the smoke-choked dark, reeling from your blow. "
        "You rolled 9 damage and it drops to 3 hp, clutching the rusted railing."
    )
    a = auto_score(text, Scenario("combat", "narrate a hit"))
    assert a.dice_leak is True
    assert a.verdict == "FAIL"


def test_auto_score_warns_on_missing_dialogue_for_npc():
    text = (
        "Ash drifts through the lantern glow as the fence steps from the shadows, "
        "the acrid reek of soot clinging to her coat while the grey crowd murmurs. "
        "She watches you, wary, one hand on a scarred relic. Will you approach?"
    )
    scn = next(s for s in SCENARIOS if s.key == "npc_meeting")
    a = auto_score(text, scn)
    assert a.has_dialogue is False
    assert "no-dialogue" in a.flags


def test_parse_judge_tolerates_surrounding_text():
    raw = 'Here are the scores:\n{"atmosphere": 4, "npc_craft": 5, "gm_craft": 4} done'
    parsed = parse_judge(raw)
    assert parsed == {"atmosphere": 4.0, "npc_craft": 5.0, "gm_craft": 4.0}


def test_parse_judge_invalid_returns_none():
    assert parse_judge("no json here") is None
    assert parse_judge('{"atmosphere": 4}') is None  # missing dimensions


def test_runner_aggregates_with_fakes():
    def fake_model(system, user):
        return GOOD_NPC

    def fake_judge(system, user):
        return '{"atmosphere": 4, "npc_craft": 4, "gm_craft": 5}'

    report = ProbeRunner(fake_model, fake_judge).run(model="fake/model")
    assert report.model == "fake/model"
    assert len(report.results) == len(SCENARIOS)
    counts = report.auto_counts
    assert counts["PASS"] + counts["WARN"] + counts["FAIL"] == len(SCENARIOS)
    means = report.judge_means
    assert means["overall"] == (4 + 4 + 5) / 3
    # Serialises cleanly.
    d = report.to_dict()
    assert d["model"] == "fake/model" and "results" in d


def test_runner_without_judge():
    report = ProbeRunner(lambda s, u: GOOD_NPC, None).run(model="m")
    assert report.judge_means == {}
    assert all(r.judge is None for r in report.results)


def test_build_judge_prompt_includes_response():
    scn = SCENARIOS[0]
    prompt = build_judge_prompt(scn, "some narration")
    assert "some narration" in prompt and scn.instruction in prompt
