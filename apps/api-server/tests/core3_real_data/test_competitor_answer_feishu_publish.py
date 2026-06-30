import json
import subprocess
from argparse import Namespace

from app.cli import catforge_analyst
from app.services.core3_real_data.analyst import competitor_answer


def test_feishu_failure_message_points_to_container_config_for_not_configured() -> None:
    message = competitor_answer._feishu_failure_message(
        '{"ok": false, "error": {"type": "config", "subtype": "not_configured", "message": "not configured"}}'
    )

    assert "API 容器未加载飞书 CLI 配置或密钥目录" in message
    assert "CATFORGE_FEISHU_CONFIG_DIR" in message
    assert "CATFORGE_FEISHU_DATA_DIR" in message


def test_feishu_card_reply_publisher_sends_interactive_message(monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"data": {"message_id": "om_sent", "chat_id": "oc_chat"}}),
            stderr="",
        )

    monkeypatch.setenv("CATFORGE_FEISHU_CLI_BIN", "/opt/openclaw-node/bin/lark-cli")
    monkeypatch.setenv("CATFORGE_FEISHU_AS", "bot")
    monkeypatch.setattr(competitor_answer.subprocess, "run", fake_run)

    result = competitor_answer.publish_feishu_card_reply(
        card={"schema": "2.0", "body": {"elements": []}},
        reply_message_id="om_original",
        idempotency_key="card-om_original",
    )

    assert result.status == "sent"
    assert result.message_id == "om_sent"
    assert result.chat_id == "oc_chat"
    command = calls[0][0]
    assert command[:3] == ["/opt/openclaw-node/bin/lark-cli", "im", "+messages-reply"]
    assert command[command.index("--message-id") + 1] == "om_original"
    assert command[command.index("--msg-type") + 1] == "interactive"
    assert command[command.index("--as") + 1] == "bot"
    assert command[command.index("--idempotency-key") + 1] == "card-om_original"
    assert json.loads(command[command.index("--content") + 1])["schema"] == "2.0"


def test_feishu_card_reply_publisher_shortens_long_idempotency_key(monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"data": {"message_id": "om_sent"}}),
            stderr="",
        )

    monkeypatch.setenv("CATFORGE_FEISHU_CLI_BIN", "/opt/openclaw-node/bin/lark-cli")
    monkeypatch.setattr(competitor_answer.subprocess, "run", fake_run)

    result = competitor_answer.publish_feishu_card_reply(
        card={"schema": "2.0"},
        reply_message_id="om_original",
        idempotency_key="competitor-card-om_x100b6b3dc3d18100b27fc86d7b762ad",
    )

    assert result.status == "sent"
    command = calls[0]
    key = command[command.index("--idempotency-key") + 1]
    assert key.startswith("cf-card-")
    assert len(key) <= 50


def test_feishu_card_reply_failure_message_is_business_safe(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=json.dumps({"error": {"missing_scopes": ["im:message"], "console_url": "https://example.test/console"}}),
        )

    monkeypatch.setenv("CATFORGE_FEISHU_CLI_BIN", "/opt/openclaw-node/bin/lark-cli")
    monkeypatch.setattr(competitor_answer.subprocess, "run", fake_run)

    result = competitor_answer.publish_feishu_card_reply(card={"schema": "2.0"}, reply_message_id="om_original")

    assert result.status == "failed"
    assert "飞书卡片发送失败" in result.message_cn
    assert "im:message" in result.message_cn
    assert "appSecret" not in result.message_cn


def test_feishu_card_reply_field_validation_message_is_specific() -> None:
    message = competitor_answer._feishu_im_failure_message(
        '{"error": {"code": 99992402, "message": "field validation failed"}}'
    )

    assert message == "飞书卡片发送失败：飞书消息字段校验未通过。"


def test_feishu_card_delivery_text_uses_real_delivery_status() -> None:
    sent = {
        "result": {
            "competitor_answer": {
                "short_answer": "短摘要",
                "feishu_card_delivery": {"status": "sent", "message_cn": "已发送飞书竞品看板卡片。"},
            }
        }
    }
    failed = {
        "result": {
            "competitor_answer": {
                "short_answer": "短摘要",
                "feishu_card_delivery": {"status": "failed", "message_cn": "飞书卡片发送失败。"},
            }
        }
    }

    assert catforge_analyst.format_feishu_card_delivery_text(sent) == "已发送飞书竞品看板卡片。"
    assert catforge_analyst.format_feishu_card_delivery_text(failed) == "飞书卡片发送失败。"


def test_feishu_card_delivery_text_supports_claim_value_answer() -> None:
    sent = {
        "result": {
            "claim_value_answer": {
                "short_answer": "短摘要",
                "feishu_card_delivery": {"status": "sent", "message_cn": "已发送飞书用户卖点价值看板卡片。"},
            }
        }
    }

    assert catforge_analyst.format_feishu_card_delivery_text(sent) == "已发送飞书用户卖点价值看板卡片。"


def test_attach_feishu_card_delivery_supports_claim_value_answer(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_publish_feishu_card_reply(**kwargs):
        calls.append(kwargs)
        return competitor_answer.FeishuCardPublishResult(
            status="sent",
            message_cn="已发送飞书竞品看板卡片。",
            message_id="om_sent",
            chat_id="oc_chat",
        )

    monkeypatch.setattr(competitor_answer, "publish_feishu_card_reply", fake_publish_feishu_card_reply)
    result = {
        "result": {
            "claim_value_answer": {
                "feishu_card_payload": {"schema": "2.0", "body": {"elements": []}},
            }
        }
    }

    catforge_analyst.attach_feishu_card_delivery(
        result,
        Namespace(
            feishu_reply_message_id="om_original",
            feishu_reply_in_thread=False,
            feishu_card_idempotency_key="claim-value-card-om_original",
        ),
    )

    assert calls == [
        {
            "card": {"schema": "2.0", "body": {"elements": []}},
            "reply_message_id": "om_original",
            "reply_in_thread": False,
            "idempotency_key": "claim-value-card-om_original",
        }
    ]
    delivery = result["result"]["claim_value_answer"]["feishu_card_delivery"]
    assert delivery["status"] == "sent"
    assert delivery["message_cn"] == "已发送飞书用户卖点价值看板卡片。"


def test_text_output_prefers_feishu_card_delivery_status(capsys) -> None:
    result = {
        "result": {
            "competitor_answer": {
                "short_answer": "短摘要",
                "feishu_card_delivery": {"status": "sent", "message_cn": "已发送飞书竞品看板卡片。"},
            }
        }
    }

    catforge_analyst.emit_result(result, "text", feishu_card_only=False)

    assert capsys.readouterr().out.strip() == "已发送飞书竞品看板卡片。"


def test_feishu_card_only_success_outputs_delivery_status(capsys) -> None:
    result = {
        "result": {
            "claim_value_answer": {
                "short_answer": "短摘要",
                "feishu_card_delivery": {"status": "sent", "message_cn": "已发送飞书用户卖点价值看板卡片。"},
            }
        }
    }

    catforge_analyst.emit_result(result, "text", feishu_card_only=True)

    assert capsys.readouterr().out.strip() == "已发送飞书用户卖点价值看板卡片。"


def test_feishu_card_only_without_delivery_does_not_fallback_to_short_answer(capsys) -> None:
    result = {"result": {"competitor_answer": {"short_answer": "短摘要"}}}

    catforge_analyst.emit_result(result, "text", feishu_card_only=True)

    assert capsys.readouterr().out.strip() == "未发送飞书看板卡片：缺少发送结果。"
