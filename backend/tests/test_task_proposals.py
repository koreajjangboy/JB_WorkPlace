from jb_workplace.runner import extract_task_proposals, tasks_hint


def test_reads_last_block():
    text = (
        "끝났습니다.\n```workplace-tasks\n[]\n```\n"
        '```workplace-tasks\n[{"project": "AI era", "title": "2화 초안", "prompt": "plan.md를 읽고 2화 초안"}]\n```\n'
        "```commit\nAdd drafts\n```"
    )
    assert extract_task_proposals(text) == [
        {"project": "AI era", "title": "2화 초안", "prompt": "plan.md를 읽고 2화 초안", "task_id": None}
    ]


def test_tasks_object_and_missing_title():
    text = '```workplace-tasks\n{"tasks": [{"project": "x", "prompt": "첫 줄\\n둘째 줄"}, {"project": "y"}, 3]}\n```'
    assert extract_task_proposals(text) == [{"project": "x", "title": "첫 줄", "prompt": "첫 줄\n둘째 줄", "task_id": None}]


def test_invalid_or_absent():
    assert extract_task_proposals("no block") is None
    assert extract_task_proposals("```workplace-tasks\n[oops\n```") is None
    assert extract_task_proposals('```workplace-tasks\n"text"\n```') is None


def test_hint_lists_projects():
    hint = tasks_hint(["b", "A", "b"])
    assert hint.endswith('Registered projects: "A", "b".')
