from app.services.core3_real_data.analyst import competitor_answer


def test_feishu_failure_message_points_to_container_config_for_not_configured() -> None:
    message = competitor_answer._feishu_failure_message(
        '{"ok": false, "error": {"type": "config", "subtype": "not_configured", "message": "not configured"}}'
    )

    assert "API 容器未加载飞书 CLI 配置或密钥目录" in message
    assert "CATFORGE_FEISHU_CONFIG_DIR" in message
    assert "CATFORGE_FEISHU_DATA_DIR" in message
