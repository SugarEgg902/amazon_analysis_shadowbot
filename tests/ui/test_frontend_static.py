from pathlib import Path
import subprocess


def test_index_page_hides_static_marketing_copy():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "Amazon Competitor Agent" not in html
    assert "Static Frontend" not in html
    assert "输入中文任务，后端负责抓取、分析、导出 CSV" not in html
    assert "POST 创建任务，SSE 持续推送状态" not in html
    assert "状态消息、逐项结果和最终 CSV 预览都会按顺序出现在这里。" not in html


def test_frontend_script_does_not_append_intro_message():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'title: "Ready"' not in script
    assert "提交任务后，这里会持续显示状态流、逐项完成消息和最终 CSV 预览。" not in script


def test_frontend_script_uses_session_routes_instead_of_chat_routes():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/sessions"' in script
    assert "/messages" in script
    assert "/runs/" in script
    assert "/api/chat" not in script


def test_frontend_script_handles_mixed_agent_event_types():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'type === "assistant"' in script
    assert 'type === "tool_status"' in script
    assert 'type === "artifact"' in script
    assert 'type === "done"' in script


def test_frontend_script_only_finalizes_stream_on_done_payload():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'if (payload.type === "done") {' in script
    assert 'if (payload.type === "done" || payload.type === "error") {' not in script


def test_index_page_uses_multi_turn_example_copy():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "帮我看一下 Blackview 的竞品" in html
    assert "从亚马逊获取 Blackview 5 个竞品分析" not in html


def test_index_page_busts_cached_frontend_assets():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert '/static/styles.css?v=' in html
    assert '/static/app.js?v=' in html


def test_index_page_uses_latest_asset_version_for_message_layout_fix():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert '/static/styles.css?v=20260511-preview-wrap-v2' in html
    assert '/static/app.js?v=20260511-preview-wrap-v2' in html


def test_frontend_script_uses_processing_indicator_instead_of_status_cards():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "showProcessingIndicator" in script
    assert "hideProcessingIndicator" in script
    assert 'title: "Status"' not in script


def test_frontend_styles_expand_workspace_and_conversation_area():
    css = Path("frontend/styles.css").read_text(encoding="utf-8")

    assert "width: min(1200px, calc(100% - 32px));" not in css
    assert "max-height: 70vh;" not in css
    assert "width: calc(100% - 32px);" in css
    assert "min-height: calc(100vh - 32px);" in css


def test_frontend_styles_prevent_composer_overflow():
    css = Path("frontend/styles.css").read_text(encoding="utf-8")

    assert "min-width: 0;" in css
    assert ".composer-actions" in css
    assert "flex-direction: column;" in css
    assert "align-items: stretch;" in css


def test_frontend_styles_stack_messages_from_top_without_grid_stretch():
    css = Path("frontend/styles.css").read_text(encoding="utf-8")
    message_list_block = css.split(".message-list {", 1)[1].split("}", 1)[0]
    message_card_block = css.split(".message-card {", 1)[1].split("}", 1)[0]
    processing_indicator_block = css.split(".processing-indicator {", 1)[1].split("}", 1)[0]

    assert ".message-list" in css
    assert (
        ".conversation-panel {\n"
        "  display: flex;\n"
        "  flex-direction: column;\n"
        "  min-height: calc(100vh - 32px);\n"
        "  overflow: auto;\n"
        "}"
    ) in css
    assert "display: grid;" not in message_list_block
    assert "display: flex;" in message_list_block
    assert "flex-direction: column;" in message_list_block
    assert "gap: 8px;" in message_list_block
    assert "flex: 1;" not in message_list_block
    assert "overflow: visible;" in message_list_block
    assert "padding: 12px 14px;" in message_card_block
    assert "display: flex;" in processing_indicator_block
    assert "gap: 12px;" in processing_indicator_block


def test_frontend_preview_cells_use_click_to_expand_truncation_styles():
    css = Path("frontend/styles.css").read_text(encoding="utf-8")

    assert ".preview-cell-toggle" in css
    assert "text-overflow: ellipsis;" in css
    assert 'white-space: nowrap;' in css
    assert '.preview-cell-toggle[data-expanded="true"]' in css
    assert "white-space: normal;" in css
    assert "overflow-wrap: anywhere;" in css
    assert "table-layout: fixed;" in css


def test_frontend_runtime_keeps_stream_active_until_done():
    result = subprocess.run(
        ["node", "--test", "test_frontend_runtime.js"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
