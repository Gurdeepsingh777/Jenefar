from jenefar.agents.llm_agent import BaseLLMAgent


def test_task_prompt_puts_current_request_last_and_filters_internal_old_replies():
    task = "ye ab bhi sahi se work nahi kar rahi, ise fix karo"
    prompt = BaseLLMAgent._build_task_prompt(
        task,
        history=[
            {"role": "user", "content": "Pehle network scan ki baat hui thi."},
            {
                "role": "assistant",
                "content": (
                    "Okay, let me try to figure out what the user needs here. "
                    "The user has been interacting with the assistant about unrelated tasks."
                ),
            },
            {"role": "assistant", "content": "Audio output is still unavailable."},
            {"role": "user", "content": task},
        ],
        retrieved_memory=[
            {"title": "Old task", "content": "Old network scan request and unrelated saved notes."}
        ],
        procedural_memory=[{"name": "Old procedure", "steps": ["run old command"]}],
        knowledge_graph=[{"subject": "old", "predicate": "related_to", "object": "scan"}],
    )

    assert prompt.endswith(
        "CURRENT_REQUEST>\n" + task + "\n</CURRENT_REQUEST>"
    )
    assert prompt.count(task) == 1
    assert "The user has been interacting with the assistant" not in prompt
    assert "SAVED MEMORY" not in prompt
    assert "SAVED PROCEDURES" not in prompt
    assert "MEMORY RELATIONS" not in prompt
    assert "Audio output is still unavailable." in prompt


def test_plain_request_does_not_receive_stale_chat_history_or_memory():
    prompt = BaseLLMAgent._build_task_prompt(
        "2 + 2 kitna hota hai?",
        history=[
            {"role": "user", "content": "Scan 192.168.29.0/24"},
            {"role": "assistant", "content": "The scan discovered several hosts."},
        ],
        retrieved_memory=[{"title": "Old scan", "content": "192.168.29.0/24"}],
        procedural_memory=[{"name": "Network scan", "steps": ["run nmap"]}],
        knowledge_graph=[{"subject": "router", "predicate": "has_ip", "object": "192.168.29.1"}],
    )

    assert prompt.endswith(
        "CURRENT_REQUEST>\n2 + 2 kitna hota hai?\n</CURRENT_REQUEST>"
    )
    assert "192.168.29.0/24" not in prompt
    assert "Recent context" not in prompt
    assert "SAVED MEMORY" not in prompt


def test_explicit_memory_query_receives_only_bounded_saved_context():
    task = "Pichhli conversation mein humne voice setup ke baare mein kya discuss kiya tha?"
    prompt = BaseLLMAgent._build_task_prompt(
        task,
        history=[
            {"role": "user", "content": "Voice setup kaise karna hai?"},
            {"role": "assistant", "content": "Run python run.py --setup-voice."},
            {"role": "user", "content": task},
        ],
        retrieved_memory=[
            {"title": "Voice setup", "content": "faster-whisper and local cache"}
        ],
        procedural_memory=[{"name": "Voice setup", "steps": ["install", "cache model"]}],
        knowledge_graph=[{"subject": "Whisper", "predicate": "used_for", "object": "STT"}],
    )

    assert "RECENT CONTEXT" in prompt
    assert "SAVED MEMORY" in prompt
    assert "SAVED PROCEDURES" in prompt
    assert "MEMORY RELATIONS" in prompt
    assert prompt.endswith(
        "CURRENT_REQUEST>\n" + task + "\n</CURRENT_REQUEST>"
    )
